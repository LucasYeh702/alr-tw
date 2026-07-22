"""Official judgment search and full-text snapshots from the Judicial Yuan website."""

from __future__ import annotations

import hashlib
import html
import importlib
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping
from urllib.parse import parse_qs, unquote, urlencode, urljoin, urlsplit

from alr_tw.contracts.providers import (
    CandidateIdentity,
    ProviderCandidate,
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

from .judicial_site import (
    HttpxJudicialSiteTransport,
    JudicialSiteResponse,
    JudicialSiteTransport,
)
from .judgment_parser import (
    JudgmentRole,
    ParsedJudgment,
    extract_judgment_blocks,
    parse_judgment_blocks,
)

JUDGMENT_SEARCH_ORIGIN = "https://judgment.judicial.gov.tw"
JUDGMENT_ADVANCED_SEARCH_URL = f"{JUDGMENT_SEARCH_ORIGIN}/FJUD/Default_AD.aspx"
JUDGMENT_SEARCH_URL = f"{JUDGMENT_SEARCH_ORIGIN}/FJUD/qryresult.aspx"
JUDGMENT_DATA_URL = f"{JUDGMENT_SEARCH_ORIGIN}/FJUD/data.aspx"
MAX_RESPONSE_BYTES = 24 * 1024 * 1024
MAX_SEARCH_RESULTS = 20
_JID_FIELD = re.compile(r"^[^,\r\n]{1,80}$")
_JID_URL_PATHS = {
    "/fjud/data.aspx",
    "/fjud/printdata.aspx",
    "/fjud/hlexportpdf",
    "/fjud/hlexportpdf.aspx",
    "/exportfile/exporttopdf.aspx",
}
_EXPORT_JID_PATHS = {
    "/fjud/hlexportpdf",
    "/fjud/hlexportpdf.aspx",
    "/exportfile/exporttopdf.aspx",
}
_BLOCKED_MARKERS = (
    "Request Rejected",
    "The requested URL was rejected",
    "請求已遭拒絕",
)

_COURT_CODES = {
    "最高法院": "TPS",
    "最高行政法院": "TPA",
    "臺灣高等法院": "TPH",
    "台灣高等法院": "TPH",
    "臺灣高等法院臺中分院": "TCH",
    "台灣高等法院台中分院": "TCH",
    "臺灣高等法院臺南分院": "TNH",
    "台灣高等法院台南分院": "TNH",
    "臺灣高等法院高雄分院": "KSH",
    "台灣高等法院高雄分院": "KSH",
    "臺灣高等法院花蓮分院": "HLH",
    "台灣高等法院花蓮分院": "HLH",
    "臺灣臺北地方法院": "TPD",
    "台灣台北地方法院": "TPD",
    "臺灣士林地方法院": "SLD",
    "臺灣新北地方法院": "PCD",
    "臺灣桃園地方法院": "TYD",
    "臺灣新竹地方法院": "SCD",
    "臺灣苗栗地方法院": "MLD",
    "臺灣臺中地方法院": "TCD",
    "台灣台中地方法院": "TCD",
    "臺灣彰化地方法院": "CHD",
    "臺灣南投地方法院": "NTD",
    "臺灣雲林地方法院": "ULD",
    "臺灣嘉義地方法院": "CYD",
    "臺灣臺南地方法院": "TND",
    "台灣台南地方法院": "TND",
    "臺灣高雄地方法院": "KSD",
    "臺灣橋頭地方法院": "CTD",
    "臺灣屏東地方法院": "PTD",
    "臺灣花蓮地方法院": "HLD",
    "臺灣臺東地方法院": "TTD",
    "臺灣宜蘭地方法院": "ILD",
    "臺灣基隆地方法院": "KLD",
    "臺灣澎湖地方法院": "PHD",
    "福建金門地方法院": "KMD",
    "福建連江地方法院": "LCD",
}
_SYSTEM_CODES = {"民事": "V", "刑事": "M", "行政": "A", "懲戒": "P"}


@dataclass(frozen=True)
class FormalCitation:
    court_name: str
    court_code: str | None
    year: str
    case: str
    number: str
    system: str | None = None


@dataclass(frozen=True)
class JudgmentSearchHit:
    jid: str
    title: str
    official_url: str
    excerpt: str = ""


class OfficialJudgmentProvider:
    provider_id = "official_judicial_yuan_judgments"

    def __init__(
        self,
        transport: JudicialSiteTransport | None = None,
        *,
        timeout: float = 20.0,
        snapshot_ttl: timedelta = timedelta(hours=24),
    ) -> None:
        self.transport = transport or HttpxJudicialSiteTransport()
        self.timeout = timeout
        self.snapshot_ttl = snapshot_ttl

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            exact_lookup=True,
            keyword_search=True,
            semantic_recall=False,
            official_verification=True,
            historical_versions=False,
            current_status_check=True,
            external_query_transfer=False,
        )

    async def health_check(self) -> ProviderHealth:
        async with self._operation():
            return await self._health_check()

    async def _health_check(self) -> ProviderHealth:
        response, error = await self._get(JUDGMENT_ADVANCED_SEARCH_URL)
        if response is None:
            code = self._error_code_for_transport(error)
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderHealthStatus.UNAVAILABLE,
                error_code=code.value,
                message=error,
            )
        document, decode_error = self._decode(response)
        if document is None or 'name="judtype"' not in document:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderHealthStatus.DEGRADED,
                error_code=ProviderErrorCode.OFFICIAL_PARSE_ERROR.value,
                message=decode_error or "SEARCH_FORM_NOT_RECOGNIZED",
            )
        return ProviderHealth(provider_id=self.provider_id, status=ProviderHealthStatus.HEALTHY)

    async def exact_lookup(
        self,
        identifier: str,
        *,
        now: datetime | None = None,
    ) -> tuple[ProviderResult, SourceRecord | None, list[EvidenceSpan]]:
        async with self._operation():
            return await self._exact_lookup(identifier, now=now)

    async def _exact_lookup(
        self,
        identifier: str,
        *,
        now: datetime | None = None,
    ) -> tuple[ProviderResult, SourceRecord | None, list[EvidenceSpan]]:
        lookup_jid = self.jid_from_identifier(identifier)
        if lookup_jid is None:
            lookup_jid = self.partial_jid_from_identifier(identifier)
        if lookup_jid is None:
            citation = self.normalize_formal_citation(identifier)
            if citation is None:
                return self._error(ProviderErrorCode.INVALID_IDENTIFIER, "INVALID_IDENTIFIER"), None, []
            resolved = await self._resolve_formal_citation(citation)
            if isinstance(resolved, ProviderResult):
                return resolved, None, []
            lookup_jid = resolved

        official_url = self.official_document_url(lookup_jid)
        response, transport_error = await self._get(official_url)
        if response is None:
            if transport_error == "HTTP_404":
                return self._not_found(lookup_jid), None, []
            return (
                self._error(self._error_code_for_transport(transport_error), transport_error),
                None,
                [],
            )
        document, decode_error = self._decode(response)
        if document is None:
            return self._error(ProviderErrorCode.OFFICIAL_PARSE_ERROR, decode_error), None, []
        if self._looks_not_found(document):
            return self._not_found(lookup_jid), None, []
        try:
            parsed = self.parse_detail_page(
                document,
                expected_jid=lookup_jid,
                official_url=official_url,
            )
        except ValueError as exc:
            error_codes = {
                "JID_MISMATCH": ProviderErrorCode.OFFICIAL_IDENTIFIER_MISMATCH,
                "JUDGMENT_CONTENT_MISSING": ProviderErrorCode.JUDGMENT_CONTENT_MISSING,
                "JUDGMENT_TEXT_EMPTY": ProviderErrorCode.JUDGMENT_TEXT_EMPTY,
            }
            code = error_codes.get(str(exc), ProviderErrorCode.OFFICIAL_PARSE_ERROR)
            return self._error(code, str(exc)), None, []

        timestamp = now or datetime.now(UTC)
        source, evidence = self._build_snapshot(parsed, timestamp)
        return (
            ProviderResult(
                status=ProviderResultStatus.FOUND,
                provider_id=self.provider_id,
                source_ids=[source.source_id],
                evidence_ids=[item.evidence_id for item in evidence],
                coverage_complete=True,
                metadata={
                    "jid": parsed["jid"],
                    "retrieval": "official_website_html",
                    "parse_status": source.metadata.get("parse_status"),
                    "parser_version": source.metadata.get("parser_version"),
                    "eligible_evidence_count": sum(
                        item.eligible_for_claim_support for item in evidence
                    ),
                    "warnings": list(source.warnings),
                },
            ),
            source,
            evidence,
        )

    async def search(
        self,
        query: str = "",
        *,
        limit: int = 10,
        court: str | None = None,
        case_type: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        case_word: str | None = None,
        case_number: str | None = None,
        main_text: str | None = None,
    ) -> ProviderResult:
        async with self._operation():
            return await self._search(
                query,
                limit=limit,
                court=court,
                case_type=case_type,
                year_from=year_from,
                year_to=year_to,
                case_word=case_word,
                case_number=case_number,
                main_text=main_text,
            )

    async def _search(
        self,
        query: str = "",
        *,
        limit: int = 10,
        court: str | None = None,
        case_type: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        case_word: str | None = None,
        case_number: str | None = None,
        main_text: str | None = None,
    ) -> ProviderResult:
        normalized = self._validate_search_input(
            query=query,
            limit=limit,
            court=court,
            case_type=case_type,
            year_from=year_from,
            year_to=year_to,
            case_word=case_word,
            case_number=case_number,
            main_text=main_text,
        )
        if isinstance(normalized, ProviderResult):
            return normalized
        safe_limit, court_code, system_code = normalized

        if case_word and case_number and not query and not main_text:
            params = {
                "judtype": "JUDBOOK",
                "jud_case": case_word.replace("臺", "台").strip(),
                "jud_no": case_number.strip(),
            }
            if court_code:
                params["jud_court"] = court_code
            if system_code:
                params["jud_sys"] = system_code
            if year_from and (year_to is None or year_from == year_to):
                params["jud_year"] = str(year_from)
            result_page, error = await self._fetch_text(f"{JUDGMENT_SEARCH_URL}?{urlencode(params)}")
        else:
            result_page, error = await self._advanced_search(
                query=query,
                court_code=court_code,
                system_code=system_code,
                year_from=year_from,
                year_to=year_to,
                case_word=case_word,
                case_number=case_number,
                main_text=main_text,
            )
        if result_page is None:
            return self._error(self._error_code_for_transport(error), error)

        try:
            hits = self.parse_search_hits(result_page, limit=safe_limit)
        except ValueError as exc:
            return self._error(ProviderErrorCode.OFFICIAL_PARSE_ERROR, str(exc))
        list_href, total_count = self.parse_result_list_reference(result_page)
        if not hits:
            if list_href is None:
                if self._looks_not_found(result_page):
                    return self._search_not_found()
                return self._error(
                    ProviderErrorCode.OFFICIAL_PARSE_ERROR,
                    "RESULT_LIST_REFERENCE_MISSING",
                )
            list_page, error = await self._fetch_text(
                urljoin(f"{JUDGMENT_SEARCH_ORIGIN}/FJUD/", list_href)
            )
            if list_page is None:
                return self._error(self._error_code_for_transport(error), error)
            try:
                hits = self.parse_search_hits(list_page, limit=safe_limit)
            except ValueError as exc:
                return self._error(ProviderErrorCode.OFFICIAL_PARSE_ERROR, str(exc))
        if not hits:
            return self._search_not_found()
        candidates = [
            self._candidate_from_hit(hit, query, rank=rank)
            for rank, hit in enumerate(hits, start=1)
        ]
        return ProviderResult(
            status=ProviderResultStatus.FOUND,
            provider_id=self.provider_id,
            candidates=candidates,
            coverage_complete=total_count is not None and total_count <= len(hits),
            metadata={
                "total_count": total_count,
                "returned_count": len(hits),
                "retrieval": "official_website_search",
            },
        )

    @asynccontextmanager
    async def _operation(self) -> AsyncIterator[None]:
        await self.transport.open()
        try:
            yield
        finally:
            await self.transport.close()

    async def _advanced_search(
        self,
        *,
        query: str,
        court_code: str | None,
        system_code: str | None,
        year_from: int | None,
        year_to: int | None,
        case_word: str | None,
        case_number: str | None,
        main_text: str | None,
    ) -> tuple[str | None, str]:
        initial, error = await self._fetch_text(JUDGMENT_ADVANCED_SEARCH_URL)
        if initial is None:
            return None, error
        try:
            form = self.parse_search_form(initial)
        except ValueError as exc:
            return None, str(exc)
        form.update(
            {
                "judtype": "JUDBOOK",
                "whosub": "0",
                "jud_kw": query.strip(),
                "jud_title": "",
                "jud_jmain": (main_text or "").strip(),
                "jud_year": "",
                "jud_case": (case_word or "").replace("臺", "台").strip(),
                "jud_no": (case_number or "").strip(),
                "jud_no_end": (case_number or "").strip(),
                "dy1": str(year_from or ""),
                "dy2": str(year_to or ""),
                "ctl00$cp_content$btnQry": "送出查詢",
            }
        )
        if court_code:
            form["jud_court"] = court_code
        if system_code:
            form["jud_sys"] = system_code
        response, error = await self._post(JUDGMENT_ADVANCED_SEARCH_URL, form)
        if response is None:
            return None, error
        return self._decode(response)

    def _validate_search_input(
        self,
        *,
        query: str,
        limit: int,
        court: str | None,
        case_type: str | None,
        year_from: int | None,
        year_to: int | None,
        case_word: str | None,
        case_number: str | None,
        main_text: str | None,
    ) -> tuple[int, str | None, str | None] | ProviderResult:
        if not (query.strip() or case_number or main_text):
            return self._error(ProviderErrorCode.INVALID_IDENTIFIER, "SEARCH_TERM_REQUIRED")
        if len(query) > 128 or len(main_text or "") > 32:
            return self._error(ProviderErrorCode.INVALID_IDENTIFIER, "SEARCH_TERM_TOO_LONG")
        if len(case_word or "") > 16 or len(case_number or "") > 30:
            return self._error(ProviderErrorCode.INVALID_IDENTIFIER, "CASE_IDENTIFIER_TOO_LONG")
        if (case_word is None) != (case_number is None):
            return self._error(ProviderErrorCode.INVALID_IDENTIFIER, "CASE_WORD_AND_NUMBER_REQUIRED")
        if year_from is not None and not 1 <= year_from <= 999:
            return self._error(ProviderErrorCode.INVALID_IDENTIFIER, "YEAR_OUT_OF_RANGE")
        if year_to is not None and not 1 <= year_to <= 999:
            return self._error(ProviderErrorCode.INVALID_IDENTIFIER, "YEAR_OUT_OF_RANGE")
        if year_from and year_to and year_to < year_from:
            return self._error(ProviderErrorCode.INVALID_IDENTIFIER, "YEAR_RANGE_REVERSED")
        court_code: str | None = None
        if court:
            court_code = _COURT_CODES.get(court, court if re.fullmatch(r"[A-Z]{3}", court) else None)
            if court_code is None:
                return self._error(ProviderErrorCode.INVALID_IDENTIFIER, "COURT_UNSUPPORTED")
        system_code: str | None = None
        if case_type:
            system_code = _SYSTEM_CODES.get(
                case_type,
                case_type if case_type in _SYSTEM_CODES.values() else None,
            )
            if system_code is None:
                return self._error(ProviderErrorCode.INVALID_IDENTIFIER, "CASE_TYPE_UNSUPPORTED")
        return max(1, min(limit, MAX_SEARCH_RESULTS)), court_code, system_code

    async def _resolve_formal_citation(self, citation: FormalCitation) -> str | ProviderResult:
        params = {
            "judtype": "JUDBOOK",
            "jud_year": citation.year,
            "jud_case": citation.case.replace("臺", "台"),
            "jud_no": citation.number,
        }
        if citation.court_code:
            params["jud_court"] = citation.court_code
        if citation.system:
            params["jud_sys"] = citation.system
        result_page, error = await self._fetch_text(
            f"{JUDGMENT_SEARCH_URL}?{urlencode(params)}"
        )
        if result_page is None:
            return self._error(self._error_code_for_transport(error), error)
        list_href, _ = self.parse_result_list_reference(result_page)
        if list_href is None:
            return ProviderResult(
                status=ProviderResultStatus.NOT_FOUND,
                provider_id=self.provider_id,
                error_code=ProviderErrorCode.OFFICIAL_SOURCE_NOT_FOUND,
                message="FORMAL_CITATION_NOT_FOUND",
                coverage_complete=True,
                metadata={"formal_citation": citation.__dict__},
            )
        list_page, error = await self._fetch_text(
            urljoin(f"{JUDGMENT_SEARCH_ORIGIN}/FJUD/", list_href)
        )
        if list_page is None:
            return self._error(self._error_code_for_transport(error), error)
        try:
            hits = self.parse_search_hits(list_page)
        except ValueError as exc:
            return self._error(ProviderErrorCode.OFFICIAL_PARSE_ERROR, str(exc))
        unique = sorted(
            {
                hit.jid
                for hit in hits
                if self._hit_matches_formal_citation(hit, citation)
            }
        )
        if len(unique) == 1:
            return unique[0]
        if len(unique) > 1:
            return self._error(
                ProviderErrorCode.AMBIGUOUS_FORMAL_CITATION,
                "AMBIGUOUS_FORMAL_CITATION",
            ).model_copy(update={"metadata": {"candidate_jids": unique}})
        return ProviderResult(
            status=ProviderResultStatus.NOT_FOUND,
            provider_id=self.provider_id,
            error_code=ProviderErrorCode.OFFICIAL_SOURCE_NOT_FOUND,
            message="FORMAL_CITATION_NOT_FOUND",
            coverage_complete=True,
            metadata={"formal_citation": citation.__dict__},
        )

    async def _get(self, url: str) -> tuple[JudicialSiteResponse | None, str]:
        try:
            response = await self.transport.get(
                url,
                timeout=self.timeout,
                max_bytes=MAX_RESPONSE_BYTES,
            )
        except Exception as exc:
            return None, type(exc).__name__
        if response.status_code == 404:
            return None, "HTTP_404"
        if response.status_code in {403, 429}:
            return None, f"OFFICIAL_SITE_BLOCKED_HTTP_{response.status_code}"
        if response.status_code != 200:
            return None, f"HTTP_{response.status_code}"
        if self._response_looks_blocked(response):
            return None, "OFFICIAL_SITE_WAF_BLOCKED"
        return response, ""

    async def _post(
        self,
        url: str,
        form: Mapping[str, str],
    ) -> tuple[JudicialSiteResponse | None, str]:
        try:
            response = await self.transport.post_form(
                url,
                form,
                timeout=self.timeout,
                max_bytes=MAX_RESPONSE_BYTES,
            )
        except Exception as exc:
            return None, type(exc).__name__
        if response.status_code in {403, 429}:
            return None, f"OFFICIAL_SITE_BLOCKED_HTTP_{response.status_code}"
        if response.status_code != 200:
            return None, f"HTTP_{response.status_code}"
        if self._response_looks_blocked(response):
            return None, "OFFICIAL_SITE_WAF_BLOCKED"
        return response, ""

    async def _fetch_text(self, url: str) -> tuple[str | None, str]:
        response, error = await self._get(url)
        if response is None:
            return None, error
        return self._decode(response)

    @staticmethod
    def _decode(response: JudicialSiteResponse) -> tuple[str | None, str]:
        try:
            return response.content.decode("utf-8"), ""
        except UnicodeDecodeError:
            return None, "INVALID_UTF8"

    @staticmethod
    def _response_looks_blocked(response: JudicialSiteResponse) -> bool:
        prefix = response.content[:64_000].decode("utf-8", errors="ignore")
        return any(marker in prefix for marker in _BLOCKED_MARKERS)

    @staticmethod
    def _error_code_for_transport(message: str) -> ProviderErrorCode:
        if message == "HTTP_404":
            return ProviderErrorCode.OFFICIAL_SOURCE_NOT_FOUND
        if "BLOCKED" in message:
            return ProviderErrorCode.OFFICIAL_SOURCE_BLOCKED
        if message in {"INVALID_UTF8", "SEARCH_FORM_INVALID", "SEARCH_FORM_TOKEN_MISSING"}:
            return ProviderErrorCode.OFFICIAL_PARSE_ERROR
        return ProviderErrorCode.OFFICIAL_SOURCE_UNAVAILABLE

    @staticmethod
    def _soup(document: str) -> Any:
        try:
            bs4: Any = importlib.import_module("bs4")
        except ImportError as exc:  # pragma: no cover - live extra only
            raise RuntimeError("LIVE_EXTRA_REQUIRED") from exc
        return bs4.BeautifulSoup(document, "html.parser")

    @staticmethod
    def parse_search_form(document: str) -> dict[str, str]:
        soup = OfficialJudgmentProvider._soup(document)
        form_node = soup.select_one('form#form1[action*="Default_AD.aspx"]')
        if form_node is None:
            raise ValueError("SEARCH_FORM_INVALID")
        hidden = {
            str(node.get("name")): str(node.get("value") or "")
            for node in form_node.select('input[type="hidden"][name]')
        }
        if "__VIEWSTATE" not in hidden or "__EVENTVALIDATION" not in hidden:
            raise ValueError("SEARCH_FORM_TOKEN_MISSING")
        return hidden

    @staticmethod
    def parse_result_list_reference(document: str) -> tuple[str | None, int | None]:
        soup = OfficialJudgmentProvider._soup(document)
        reference = None
        href = ""
        for node in [*soup.select("iframe[src]"), *soup.select("a[href]")]:
            attribute = "src" if node.name == "iframe" else "href"
            candidate = html.unescape(str(node.get(attribute) or "")).strip()
            parsed = urlsplit(candidate)
            if (
                parsed.hostname in {None, "judgment.judicial.gov.tw"}
                and parsed.path.rsplit("/", 1)[-1].lower() == "qryresultlst.aspx"
            ):
                reference = node
                href = candidate
                break
        if reference is None:
            return None, 0 if OfficialJudgmentProvider._looks_not_found(document) else None
        if not href:
            return None, None
        badge = reference.select_one(".badge") if reference.name == "a" else None
        if badge is None:
            badge = soup.select_one("a[href] .badge")
        count_text = badge.get_text(strip=True).replace(",", "") if badge else ""
        total = int(count_text) if count_text.isdigit() else None
        return href, total

    @staticmethod
    def parse_search_hits(
        document: str,
        *,
        limit: int | None = None,
    ) -> list[JudgmentSearchHit]:
        soup = OfficialJudgmentProvider._soup(document)
        hits: list[JudgmentSearchHit] = []
        seen: set[str] = set()
        result_anchors = []
        for anchor in soup.select("a[href]"):
            href = html.unescape(str(anchor.get("href") or ""))
            absolute = urljoin(f"{JUDGMENT_SEARCH_ORIGIN}/FJUD/", href)
            if not urlsplit(absolute).path.lower().endswith("/data.aspx"):
                continue
            result_anchors.append(anchor)
            jid = OfficialJudgmentProvider.jid_from_identifier(absolute)
            if jid is None or jid in seen:
                continue
            title = OfficialJudgmentProvider._normalize_inline(anchor.get_text(" ", strip=True))
            if not title:
                continue
            excerpt = ""
            row = anchor.find_parent("tr")
            next_row = row.find_next_sibling("tr") if row is not None else None
            if next_row is not None:
                excerpt_node = next_row.select_one(".tdCut")
                if excerpt_node is not None:
                    excerpt = OfficialJudgmentProvider._normalize_inline(
                        excerpt_node.get_text(" ", strip=True)
                    )
            hits.append(
                JudgmentSearchHit(
                    jid=jid,
                    title=title,
                    official_url=OfficialJudgmentProvider.official_document_url(jid),
                    excerpt=excerpt,
                )
            )
            seen.add(jid)
            if limit is not None and len(hits) >= limit:
                break
        if result_anchors and not hits:
            raise ValueError("SEARCH_RESULT_SCHEMA_CHANGED")
        return hits

    @staticmethod
    def parse_detail_page(
        document: str,
        *,
        expected_jid: str,
        official_url: str,
    ) -> dict[str, Any]:
        soup = OfficialJudgmentProvider._soup(document)
        canonical_jid = OfficialJudgmentProvider._canonical_jid_from_detail(soup)
        if canonical_jid is None:
            raise ValueError("JUDGMENT_CANONICAL_ID_MISSING")
        expected_canonical = OfficialJudgmentProvider.normalize_jid(expected_jid)
        expected_partial = OfficialJudgmentProvider.normalize_partial_jid(expected_jid)
        if expected_canonical is not None and canonical_jid != expected_canonical:
            raise ValueError("JID_MISMATCH")
        if expected_canonical is None and (
            expected_partial is None or not canonical_jid.startswith(f"{expected_partial},")
        ):
            raise ValueError("JID_MISMATCH")

        metadata: dict[str, str] = {}
        for row in soup.select("#jud .row"):
            label = row.select_one(".col-th")
            value = row.select_one(".col-td")
            if label is None or value is None:
                continue
            key = OfficialJudgmentProvider._normalize_inline(label.get_text(" ", strip=True)).rstrip(
                "：:"
            )
            if key:
                metadata[key] = OfficialJudgmentProvider._normalize_inline(
                    value.get_text(" ", strip=True)
                )

        content_candidates = [
            soup.select_one("#jud .jud_content .htmlcontent"),
            soup.select_one("#jud .jud_content .text-pre"),
        ]
        if not any(item is not None for item in content_candidates):
            raise ValueError("JUDGMENT_CONTENT_MISSING")
        blocks: list[str] = []
        for content in content_candidates:
            if content is None:
                continue
            blocks = extract_judgment_blocks(content)
            if blocks:
                break
        parsed_judgment = parse_judgment_blocks(blocks, canonical_jid=canonical_jid)

        parts = canonical_jid.split(",")
        title = metadata.get("裁判字號") or soup.title.get_text(" ", strip=True)
        title = OfficialJudgmentProvider._normalize_inline(title)
        return {
            "jid": canonical_jid,
            "year": parts[1],
            "case": parts[2],
            "number": parts[3],
            "date": metadata.get("裁判日期", parts[4]),
            "title": title,
            "case_cause": metadata.get("裁判案由", ""),
            "text": parsed_judgment.full_text,
            "disposition": "\n".join(
                item.exact_text
                for item in parsed_judgment.sections
                if item.role is JudgmentRole.DISPOSITION
            ),
            "reasoning": "\n".join(
                item.exact_text
                for item in parsed_judgment.sections
                if item.role in {JudgmentRole.COURT_HOLDING, JudgmentRole.COURT_REASONING}
            ),
            "parsed_judgment": parsed_judgment,
            "official_url": official_url,
        }

    @staticmethod
    def _canonical_jid_from_detail(soup: Any) -> str | None:
        legacy = soup.select_one('#hlPrint[href*="printData.aspx"][href*="id="]')
        if legacy is not None:
            canonical = OfficialJudgmentProvider.jid_from_identifier(
                str(legacy.get("href"))
            )
            if canonical is not None:
                return canonical

        legacy_pdf = soup.select_one('#hlExportPDF[href*="id="]')
        if legacy_pdf is not None:
            canonical = OfficialJudgmentProvider.jid_from_identifier(
                str(legacy_pdf.get("href"))
            )
            if canonical is not None:
                return canonical

        pdf = soup.select_one('#hlExportPDF[href*="jrecno="][href*="tablename="]')
        if pdf is None:
            return None
        query = parse_qs(urlsplit(str(pdf.get("href"))).query)
        table_name = next(iter(query.get("tablename", [])), "").strip().upper()
        record_number = next(iter(query.get("jrecno", [])), "").strip()
        if not table_name or not record_number:
            return None
        return OfficialJudgmentProvider.normalize_jid(f"{table_name},{record_number}")

    @staticmethod
    def split_sections(text: str) -> tuple[str, str]:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        holding = re.search(r"(?:^|\n)\s*主[\s　]*文\s*(?:\n|$)", normalized)
        reasoning = re.search(r"(?:^|\n)\s*理[\s　]*由\s*(?:\n|$)", normalized)
        if holding is None or reasoning is None or reasoning.start() <= holding.end():
            return "", ""
        return (
            normalized[holding.end() : reasoning.start()].strip(),
            normalized[reasoning.end() :].strip(),
        )

    def _build_snapshot(
        self,
        parsed: Mapping[str, Any],
        timestamp: datetime,
    ) -> tuple[SourceRecord, list[EvidenceSpan]]:
        text = str(parsed["text"])
        jid = str(parsed["jid"])
        digest = hashlib.sha256(f"{jid}\n{timestamp.isoformat()}\n{text}".encode()).hexdigest()
        source_id = f"src_judgment_{digest[:24]}"
        content_hash = EvidenceSpan.hash_text(text)
        parsed_judgment = parsed.get("parsed_judgment")
        if not isinstance(parsed_judgment, ParsedJudgment):
            raise ValueError("JUDGMENT_PARSE_RESULT_INVALID")
        eligible_span_count = sum(
            item.eligible_for_claim_support for item in parsed_judgment.sections
        )
        source = SourceRecord(
            source_id=source_id,
            source_key=f"judgment:{jid}",
            source_version_id=f"{jid}:{digest[:16]}",
            material_type=MaterialType.JUDGMENT,
            provider_id=self.provider_id,
            source_tier=SourceTier.OFFICIAL,
            trust_status=(
                TrustStatus.EVIDENCE_ELIGIBLE
                if eligible_span_count
                else TrustStatus.OFFICIAL_VERIFIED
            ),
            official_identifier=jid,
            official_url=str(parsed["official_url"]),
            citation=str(parsed["title"]),
            title=str(parsed["title"]),
            fetched_at=timestamp,
            verified_at=timestamp,
            expires_at=timestamp + self.snapshot_ttl,
            content_hash=content_hash,
            normalized_content_hash=content_hash,
            normalized_text=text,
            metadata={
                "decision_date": parsed["date"],
                "case_cause": parsed["case_cause"],
                "retrieval": "official_website_html",
                "parse_status": parsed_judgment.parse_status.value,
                "parser_version": parsed_judgment.parser_version,
                "eligible_span_count": eligible_span_count,
                "unclassified_text_present": parsed_judgment.unparsed_remainder is not None,
            },
            warnings=list(parsed_judgment.warnings),
        )
        role_map = {
            JudgmentRole.DISPOSITION: EvidenceSectionType.DISPOSITION,
            JudgmentRole.COURT_HOLDING: EvidenceSectionType.COURT_HOLDING,
            JudgmentRole.COURT_REASONING: EvidenceSectionType.COURT_REASONING,
            JudgmentRole.PARTY_ARGUMENT: EvidenceSectionType.PARTY_ARGUMENT,
            JudgmentRole.FACTS: EvidenceSectionType.FACTS,
            JudgmentRole.PROCEDURE: EvidenceSectionType.PROCEDURE,
            JudgmentRole.MIXED: EvidenceSectionType.MIXED,
            JudgmentRole.UNKNOWN: EvidenceSectionType.UNKNOWN,
        }
        section_priority = {
            JudgmentRole.DISPOSITION: 0,
            JudgmentRole.COURT_HOLDING: 1,
            JudgmentRole.COURT_REASONING: 1,
            JudgmentRole.PARTY_ARGUMENT: 2,
            JudgmentRole.FACTS: 3,
            JudgmentRole.PROCEDURE: 3,
            JudgmentRole.MIXED: 4,
            JudgmentRole.UNKNOWN: 4,
        }
        ordered_sections = sorted(
            parsed_judgment.sections,
            key=lambda item: (section_priority[item.role], item.section_id),
        )
        evidence = [
            EvidenceSpan.from_exact_text(
                evidence_id=f"ev_{source_id}_{item.section_id}",
                source_id=source_id,
                section_id=item.section_id,
                section_type=role_map[item.role],
                exact_text=item.exact_text,
                eligible_for_claim_support=item.eligible_for_claim_support,
            )
            for item in ordered_sections
        ]
        return source, evidence

    @staticmethod
    def segment_reasoning_roles(
        reasoning: str,
    ) -> list[tuple[EvidenceSectionType, str]]:
        parsed = parse_judgment_blocks(
            ["理由", *[item for item in re.split(r"\n+", reasoning) if item.strip()]],
            canonical_jid="COMPAT,0,SEGMENT,0,00000000,0",
        )
        role_map = {
            JudgmentRole.COURT_HOLDING: EvidenceSectionType.COURT_HOLDING,
            JudgmentRole.COURT_REASONING: EvidenceSectionType.COURT_REASONING,
            JudgmentRole.PARTY_ARGUMENT: EvidenceSectionType.PARTY_ARGUMENT,
            JudgmentRole.FACTS: EvidenceSectionType.FACTS,
            JudgmentRole.PROCEDURE: EvidenceSectionType.PROCEDURE,
            JudgmentRole.MIXED: EvidenceSectionType.MIXED,
            JudgmentRole.UNKNOWN: EvidenceSectionType.UNKNOWN,
            JudgmentRole.DISPOSITION: EvidenceSectionType.DISPOSITION,
        }
        return [(role_map[item.role], item.exact_text) for item in parsed.sections]

    @staticmethod
    def normalize_jid(value: str) -> str | None:
        compact = value.strip()
        parts = [part.strip() for part in compact.split(",")]
        if len(parts) != 6 or any(not _JID_FIELD.fullmatch(part) for part in parts):
            return None
        parts[0] = parts[0].upper()
        if not re.fullmatch(r"[A-Z0-9]{3,12}", parts[0]):
            return None
        if not parts[1].isdigit() or not parts[3].isdigit():
            return None
        if not re.fullmatch(r"\d{8}", parts[4]) or not parts[5].isdigit():
            return None
        return ",".join(parts)

    @staticmethod
    def normalize_partial_jid(value: str) -> str | None:
        compact = value.strip()
        parts = [part.strip() for part in compact.split(",")]
        if len(parts) != 5 or any(not _JID_FIELD.fullmatch(part) for part in parts):
            return None
        parts[0] = parts[0].upper()
        if not re.fullmatch(r"[A-Z0-9]{3,12}", parts[0]):
            return None
        if not parts[1].isdigit() or not parts[3].isdigit():
            return None
        if not re.fullmatch(r"\d{8}", parts[4]):
            return None
        return ",".join(parts)

    @staticmethod
    def jid_from_identifier(value: str) -> str | None:
        direct = OfficialJudgmentProvider.normalize_jid(value)
        if direct is not None:
            return direct
        candidate = html.unescape(value.strip())
        if candidate.startswith("/") or not urlsplit(candidate).scheme:
            candidate = urljoin(f"{JUDGMENT_SEARCH_ORIGIN}/FJUD/", candidate)
        parsed = urlsplit(candidate)
        path = parsed.path.lower()
        if (
            parsed.scheme != "https"
            or parsed.hostname != "judgment.judicial.gov.tw"
            or path not in _JID_URL_PATHS
        ):
            return None
        query = {key.lower(): values for key, values in parse_qs(parsed.query).items()}
        if path in _EXPORT_JID_PATHS and not any(
            value.upper() == "JD" for value in query.get("type", [])
        ):
            return None
        for encoded in query.get("id", []):
            normalized = OfficialJudgmentProvider.normalize_jid(unquote(encoded))
            if normalized is not None:
                return normalized
        return None

    @staticmethod
    def partial_jid_from_identifier(value: str) -> str | None:
        direct = OfficialJudgmentProvider.normalize_partial_jid(value)
        if direct is not None:
            return direct
        candidate = html.unescape(value.strip())
        if candidate.startswith("/") or not urlsplit(candidate).scheme:
            candidate = urljoin(f"{JUDGMENT_SEARCH_ORIGIN}/FJUD/", candidate)
        parsed = urlsplit(candidate)
        path = parsed.path.lower()
        if (
            parsed.scheme != "https"
            or parsed.hostname != "judgment.judicial.gov.tw"
            or path not in _JID_URL_PATHS
        ):
            return None
        query = {key.lower(): values for key, values in parse_qs(parsed.query).items()}
        if path in _EXPORT_JID_PATHS and not any(
            value.upper() == "JD" for value in query.get("type", [])
        ):
            return None
        for encoded in query.get("id", []):
            normalized = OfficialJudgmentProvider.normalize_partial_jid(unquote(encoded))
            if normalized is not None:
                return normalized
        return None

    @staticmethod
    def normalize_formal_citation(value: str) -> FormalCitation | None:
        compact = re.sub(r"\s+", "", value.strip())
        match = re.fullmatch(
            r"(?P<court>.+?法院)(?P<year>\d{1,3})年度(?P<case>[^,，\r\n]{1,20})字"
            r"第(?P<number>\d{1,12})號(?:(?P<system>民事|刑事|行政|懲戒)(?:判決|裁定)?)?",
            compact,
        )
        if match is None:
            return None
        court_name = match.group("court")
        system_name = match.group("system")
        return FormalCitation(
            court_name=court_name,
            court_code=_COURT_CODES.get(court_name),
            year=match.group("year"),
            case=match.group("case"),
            number=match.group("number"),
            system=_SYSTEM_CODES.get(system_name) if system_name else None,
        )

    @staticmethod
    def official_document_url(jid: str) -> str:
        normalized = (
            OfficialJudgmentProvider.normalize_jid(jid)
            or OfficialJudgmentProvider.normalize_partial_jid(jid)
        )
        if normalized is None:
            raise ValueError("INVALID_JID")
        return f"{JUDGMENT_DATA_URL}?{urlencode({'ty': 'JD', 'id': normalized})}"

    @staticmethod
    def _hit_matches_formal_citation(
        hit: JudgmentSearchHit,
        citation: FormalCitation,
    ) -> bool:
        parts = hit.jid.split(",")
        if parts[1] != citation.year or parts[3] != citation.number:
            return False
        if parts[2].replace("臺", "台") != citation.case.replace("臺", "台"):
            return False
        if citation.system and not parts[0].endswith(citation.system):
            return False
        if citation.court_code and not parts[0].startswith(citation.court_code):
            return False
        if citation.court_code is None:
            expected = citation.court_name.replace("臺", "台")
            if expected not in hit.title.replace("臺", "台"):
                return False
        return True

    def _candidate_from_hit(
        self,
        hit: JudgmentSearchHit,
        query: str,
        *,
        rank: int = 1,
    ) -> ProviderCandidate:
        digest = hashlib.sha256(f"{hit.jid}\n{query}".encode()).hexdigest()
        return ProviderCandidate(
            candidate_id=f"candidate_official_judgment_{digest[:24]}",
            provider_id=self.provider_id,
            title=hit.title,
            official_identifier=hit.jid,
            official_url=hit.official_url,
            excerpt=hit.excerpt or None,
            identity=CandidateIdentity(
                canonical_jid=hit.jid,
                provider_document_id=hit.jid,
                formal_citation=hit.title,
                official_url=hit.official_url,
            ),
            candidate_rank=rank,
            metadata={"candidate_tier": "official_search_result"},
        )

    @staticmethod
    def _normalize_inline(value: str) -> str:
        return re.sub(r"[\s\u00a0\u3000]+", " ", html.unescape(value)).strip()

    @staticmethod
    def _looks_not_found(document: str) -> bool:
        compact = re.sub(r"\s+", "", document)
        return any(
            marker in compact
            for marker in ("查無資料", "查無符合條件", "無符合條件之裁判", "沒有符合")
        )

    def _not_found(self, jid: str) -> ProviderResult:
        return ProviderResult(
            status=ProviderResultStatus.NOT_FOUND,
            provider_id=self.provider_id,
            error_code=ProviderErrorCode.OFFICIAL_SOURCE_NOT_FOUND,
            message="OFFICIAL_REMOVED_OR_NOT_PUBLIC",
            coverage_complete=True,
            metadata={"removal_required": True, "jid": jid},
        )

    def _search_not_found(self) -> ProviderResult:
        return ProviderResult(
            status=ProviderResultStatus.NOT_FOUND,
            provider_id=self.provider_id,
            error_code=ProviderErrorCode.OFFICIAL_SOURCE_NOT_FOUND,
            message="OFFICIAL_SEARCH_NO_RESULTS",
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
