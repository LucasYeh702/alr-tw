"""Official Constitutional Court provider with opinion-type separation."""

from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urljoin

from alr_tw.contracts.providers import (
    ProviderCapabilities,
    ProviderErrorCode,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderResult,
    ProviderResultStatus,
)
from alr_tw.contracts.sources import (
    EvidenceSectionType,
    EvidenceSpan,
    MaterialType,
    SourceRecord,
    SourceTier,
    TrustStatus,
)

from .http import HttpTransport, HttpxAllowlistedTransport

CONSTITUTIONAL_ORIGIN = "https://cons.judicial.gov.tw"
CONSTITUTIONAL_HOST = "cons.judicial.gov.tw"
JUDGMENT_LIST_URL = f"{CONSTITUTIONAL_ORIGIN}/judcurrentNew1.aspx?fid=38"
SUBSTANTIVE_RULING_LIST_URL = f"{CONSTITUTIONAL_ORIGIN}/judcurrentNew2.aspx?fid=39"
INTERPRETATION_LIST_URL = f"{CONSTITUTIONAL_ORIGIN}/judcurrent.aspx?fid=2195"
MAX_HTML_BYTES = 12 * 1024 * 1024


class OfficialConstitutionalProvider:
    provider_id = "official_constitutional_court"

    def __init__(
        self,
        transport: HttpTransport | None = None,
        *,
        timeout: float = 15.0,
        snapshot_ttl: timedelta = timedelta(hours=24),
    ):
        self.transport = transport or HttpxAllowlistedTransport({CONSTITUTIONAL_HOST})
        self.timeout = timeout
        self.snapshot_ttl = snapshot_ttl
        self._index: dict[str, str] = {}
        self._titles: dict[str, str] = {}

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            exact_lookup=True,
            keyword_search=True,
            semantic_recall=False,
            official_verification=True,
            historical_versions=False,
            current_status_check=False,
            external_query_transfer=False,
        )

    async def health_check(self) -> ProviderHealth:
        response = await self._fetch(JUDGMENT_LIST_URL)
        if response[0] is None:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderHealthStatus.UNAVAILABLE,
                error_code=ProviderErrorCode.OFFICIAL_SOURCE_UNAVAILABLE.value,
                message=response[1],
            )
        return ProviderHealth(provider_id=self.provider_id, status=ProviderHealthStatus.HEALTHY)

    async def exact_lookup(
        self,
        identifier: str,
        *,
        now: datetime | None = None,
    ) -> tuple[ProviderResult, SourceRecord | None, list[EvidenceSpan]]:
        normalized = self.normalize_identifier(identifier)
        if normalized is None:
            return self._error(ProviderErrorCode.INVALID_IDENTIFIER, "INVALID_IDENTIFIER"), None, []
        if normalized not in self._index:
            indexed = await self._load_index()
            if indexed.status == ProviderResultStatus.ERROR:
                return indexed, None, []
        detail_url = self._index.get(normalized)
        if detail_url is None:
            return self._not_found(), None, []
        payload, error = await self._fetch(detail_url)
        if payload is None:
            return self._error(ProviderErrorCode.OFFICIAL_SOURCE_UNAVAILABLE, error), None, []
        try:
            parsed = self.parse_detail(payload, expected_identifier=normalized)
        except (ValueError, json.JSONDecodeError) as exc:
            code = (
                ProviderErrorCode.OFFICIAL_IDENTIFIER_MISMATCH
                if str(exc) == "IDENTIFIER_MISMATCH"
                else ProviderErrorCode.OFFICIAL_PARSE_ERROR
            )
            return self._error(code, str(exc)), None, []
        timestamp = now or datetime.now(UTC)
        source, evidence = self._build_snapshot(normalized, detail_url, parsed, timestamp)
        return (
            ProviderResult(
                status=ProviderResultStatus.FOUND,
                provider_id=self.provider_id,
                source_ids=[source.source_id],
                evidence_ids=[item.evidence_id for item in evidence],
                coverage_complete=True,
                metadata={"opinion_count": max(0, len(evidence) - 2)},
            ),
            source,
            evidence,
        )

    async def search(self, query: str, *, limit: int = 10) -> ProviderResult:
        needle = query.strip()
        if not needle:
            raise ValueError("query is required")
        loaded = await self._load_index()
        if loaded.status == ProviderResultStatus.ERROR:
            return loaded
        matches = [
            {
                "identifier": identifier,
                "title": self._titles.get(identifier, identifier),
                "official_url": url,
            }
            for identifier, url in self._index.items()
            if needle in identifier or needle in self._titles.get(identifier, "")
        ][: max(1, min(limit, 50))]
        return ProviderResult(
            status=ProviderResultStatus.FOUND if matches else ProviderResultStatus.NOT_FOUND,
            provider_id=self.provider_id,
            error_code=None if matches else ProviderErrorCode.OFFICIAL_SOURCE_NOT_FOUND,
            coverage_complete=True,
            metadata={"matches": matches},
        )

    async def _load_index(self) -> ProviderResult:
        if self._index:
            return ProviderResult(
                status=ProviderResultStatus.FOUND,
                provider_id=self.provider_id,
                coverage_complete=True,
                metadata={"cache": "memory"},
            )
        failures: list[str] = []
        for base_url, max_pages in (
            (JUDGMENT_LIST_URL, 10),
            (SUBSTANTIVE_RULING_LIST_URL, 2),
            (INTERPRETATION_LIST_URL, 1),
        ):
            page = 1
            while page <= max_pages:
                suffix = "" if page == 1 else f"&page={page}&tab=1"
                payload, error = await self._fetch(f"{base_url}{suffix}")
                if payload is None:
                    failures.append(error)
                    break
                entries, last_page = self.parse_index(payload)
                for identifier, title, href in entries:
                    self._index[identifier] = urljoin(CONSTITUTIONAL_ORIGIN, href)
                    self._titles[identifier] = title
                if page >= last_page:
                    break
                page += 1
        if not self._index:
            code = (
                ProviderErrorCode.OFFICIAL_SOURCE_UNAVAILABLE
                if failures
                else ProviderErrorCode.OFFICIAL_PARSE_ERROR
            )
            return self._error(code, failures[0] if failures else "INDEX_EMPTY")
        return ProviderResult(
            status=ProviderResultStatus.FOUND,
            provider_id=self.provider_id,
            coverage_complete=not failures,
            metadata={"record_count": len(self._index), "index_failures": failures},
        )

    async def _fetch(self, url: str) -> tuple[str | None, str]:
        try:
            response = await self.transport.get(
                url,
                timeout=self.timeout,
                max_bytes=MAX_HTML_BYTES,
            )
        except Exception as exc:
            return None, type(exc).__name__
        if response.status_code == 404:
            return None, "HTTP_404"
        if response.status_code != 200:
            return None, f"HTTP_{response.status_code}"
        try:
            return response.content.decode("utf-8"), ""
        except UnicodeDecodeError:
            return None, "INVALID_UTF8"

    @classmethod
    def parse_index(cls, document: str) -> tuple[list[tuple[str, str, str]], int]:
        entries: list[tuple[str, str, str]] = []
        for match in re.finditer(
            r"<a\s+(?P<attrs>[^>]+)>(?P<body>.*?)</a>",
            document,
            re.IGNORECASE | re.DOTALL,
        ):
            attrs = match.group("attrs")
            href_match = re.search(r'href="(?P<value>/docdata\.aspx\?[^\"]+)"', attrs, re.I)
            title_match = re.search(r'title="(?P<value>[^\"]+)"', attrs, re.I)
            if href_match is None:
                continue
            title = (
                html.unescape(title_match.group("value")).strip()
                if title_match is not None
                else cls._plain_text(match.group("body"))
            )
            identifier = cls.normalize_identifier(title)
            if identifier is not None:
                entries.append(
                    (identifier, title, html.unescape(href_match.group("value")))
                )
        pages = [int(value) for value in re.findall(r"[?&]page=(\d+)", document)]
        return entries, max(pages, default=1)

    @classmethod
    def parse_detail(cls, document: str, *, expected_identifier: str) -> dict[str, Any]:
        sections: dict[str, str] = {}
        markers = list(
            re.finditer(
                r'<li\s+class="title"[^>]*>(?P<title>.*?)</li>',
                document,
                re.DOTALL | re.IGNORECASE,
            )
        )
        for index, marker in enumerate(markers):
            title = cls._plain_text(marker.group("title"))
            end = markers[index + 1].start() if index + 1 < len(markers) else len(document)
            segment = document[marker.end() : end]
            text_match = re.search(
                r'<li\s+class="text"[^>]*>(?P<body>.*)',
                segment,
                re.DOTALL | re.IGNORECASE,
            )
            if text_match:
                body = text_match.group("body")
                list_end = re.search(r"</ul>\s*</li>", body, re.IGNORECASE)
                simple_end = re.search(r"</li>", body, re.IGNORECASE)
                if list_end and (simple_end is None or list_end.end() >= simple_end.end()):
                    body = body[: list_end.start()]
                elif simple_end:
                    body = body[: simple_end.start()]
                text = cls._plain_text(body)
                if text:
                    sections[title] = text
        identifier_text = (
            sections.get("判決字號")
            or sections.get("裁定字號")
            or sections.get("解釋字號")
            or ""
        )
        if expected_identifier not in identifier_text and expected_identifier not in document:
            raise ValueError("IDENTIFIER_MISMATCH")
        holding = sections.get("主文") or sections.get("解釋文") or ""
        reasoning = sections.get("理由") or sections.get("理由書") or ""
        if not holding or not reasoning:
            raise ValueError("REQUIRED_SECTIONS_MISSING")
        opinions = cls._parse_embedded_opinions(document)
        return {
            "holding": holding,
            "reasoning": reasoning,
            "decision_date": (
                sections.get("判決日期")
                or sections.get("裁定日期")
                or sections.get("解釋公布院令")
            ),
            "case_title": sections.get("案由") or sections.get("解釋爭點"),
            "opinions": opinions,
        }

    @staticmethod
    def _parse_embedded_opinions(document: str) -> list[dict[str, str]]:
        match = re.search(
            r'<textarea[^>]+id="jsonLabel"[^>]*>(?P<body>.*?)</textarea>',
            document,
            re.DOTALL | re.IGNORECASE,
        )
        if not match:
            return []
        payload = json.loads(html.unescape(match.group("body")).strip())
        opinions: list[dict[str, str]] = []
        for attachment in payload.get("atts", []):
            if not isinstance(attachment, dict):
                continue
            title = str(attachment.get("doc_att_title") or "")
            text = str(attachment.get("doc_att_txt") or "").strip()
            if text and "意見書" in title:
                opinions.append({"title": title, "text": text})
        return opinions

    def _build_snapshot(
        self,
        identifier: str,
        official_url: str,
        parsed: dict[str, Any],
        timestamp: datetime,
    ) -> tuple[SourceRecord, list[EvidenceSpan]]:
        combined = "\n\n".join([parsed["holding"], parsed["reasoning"]])
        digest = hashlib.sha256(
            f"{identifier}\n{official_url}\n{timestamp.isoformat()}\n{combined}".encode()
        ).hexdigest()
        source_id = f"src_const_{digest[:24]}"
        content_hash = EvidenceSpan.hash_text(combined)
        source = SourceRecord(
            source_id=source_id,
            source_key=f"constitutional:{identifier}",
            source_version_id=f"{identifier}:{digest[:16]}",
            material_type=MaterialType.CONSTITUTIONAL,
            provider_id=self.provider_id,
            source_tier=SourceTier.OFFICIAL,
            trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
            official_identifier=identifier,
            official_url=official_url,
            citation=identifier,
            title=parsed.get("case_title") or identifier,
            fetched_at=timestamp,
            verified_at=timestamp,
            expires_at=timestamp + self.snapshot_ttl,
            content_hash=content_hash,
            normalized_content_hash=content_hash,
            normalized_text=combined,
            metadata={
                "decision_date": parsed.get("decision_date"),
                "opinion_titles": [item["title"] for item in parsed["opinions"]],
            },
        )
        evidence = [
            self._evidence(source_id, "holding", EvidenceSectionType.HOLDING, parsed["holding"]),
            self._evidence(
                source_id,
                "reasoning",
                EvidenceSectionType.COURT_REASONING,
                parsed["reasoning"],
            ),
        ]
        for index, opinion in enumerate(parsed["opinions"]):
            section_type = (
                EvidenceSectionType.DISSENTING_OPINION
                if "不同意" in opinion["title"]
                else EvidenceSectionType.CONCURRING_OPINION
            )
            evidence.append(
                self._evidence(source_id, f"opinion-{index + 1}", section_type, opinion["text"])
            )
        return source, evidence

    @staticmethod
    def _evidence(
        source_id: str,
        section_id: str,
        section_type: EvidenceSectionType,
        text: str,
    ) -> EvidenceSpan:
        return EvidenceSpan.from_exact_text(
            evidence_id=f"ev_{source_id}_{section_id}",
            source_id=source_id,
            section_id=section_id,
            section_type=section_type,
            exact_text=text,
            eligible_for_claim_support=True,
        )

    @staticmethod
    def normalize_identifier(value: str) -> str | None:
        compact = re.sub(r"[\s　]", "", html.unescape(value))
        compact = compact.replace("年度", "年")
        match = re.search(
            r"(\d{1,3})年(憲判字|憲裁字|憲暫裁字|審裁字)第(\d+)號",
            compact,
        )
        if match:
            return f"{int(match.group(1))}年{match.group(2)}第{int(match.group(3))}號"
        interpretation = re.search(r"釋字第(\d+)號", compact)
        if interpretation:
            return f"釋字第{int(interpretation.group(1))}號"
        return None

    @staticmethod
    def _plain_text(fragment: str) -> str:
        with_breaks = re.sub(r"<(?:br|/p|/li|/pre)>\s*", "\n", fragment, flags=re.I)
        stripped = re.sub(r"<[^>]+>", "", with_breaks)
        lines = [re.sub(r"\s+", " ", line).strip() for line in html.unescape(stripped).splitlines()]
        return "\n".join(line for line in lines if line)

    def _not_found(self) -> ProviderResult:
        return ProviderResult(
            status=ProviderResultStatus.NOT_FOUND,
            provider_id=self.provider_id,
            error_code=ProviderErrorCode.OFFICIAL_SOURCE_NOT_FOUND,
            message="CONSTITUTIONAL_DECISION_NOT_FOUND",
            coverage_complete=True,
        )

    def _error(self, code: ProviderErrorCode, message: str) -> ProviderResult:
        return ProviderResult(
            status=ProviderResultStatus.ERROR,
            provider_id=self.provider_id,
            error_code=code,
            message=message,
            coverage_complete=False,
        )
