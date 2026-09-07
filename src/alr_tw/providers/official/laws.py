"""Official central-law provider backed by the MOJ structured dataset."""

from __future__ import annotations

import hashlib
import html
import io
import json
import re
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

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

from .http import HttpTransport, HttpxAllowlistedTransport, safe_transport_error

LAW_DATA_URL = "https://law.moj.gov.tw/api/ch/law/json"
LAW_HOST = "law.moj.gov.tw"
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 96 * 1024 * 1024
MAX_ARCHIVE_FILES = 8
MAX_WEBPAGE_BYTES = 4 * 1024 * 1024


class OfficialLawProvider:
    provider_id = "official_moj_laws"

    def __init__(
        self,
        transport: HttpTransport | None = None,
        *,
        timeout: float = 20.0,
        snapshot_ttl: timedelta = timedelta(hours=24),
        verify_webpage: bool = True,
        clock: Callable[[], datetime] | None = None,
    ):
        if snapshot_ttl <= timedelta(0):
            raise ValueError("snapshot_ttl must be positive")
        self.transport = transport or HttpxAllowlistedTransport({LAW_HOST})
        self.timeout = timeout
        self.snapshot_ttl = snapshot_ttl
        self.verify_webpage = verify_webpage
        self._laws: list[dict[str, Any]] | None = None
        self._dataset_updated_at: str | None = None
        self._clock = clock or (lambda: datetime.now(UTC))
        self._dataset_fetched_at: datetime | None = None
        self._dataset_verified_at: datetime | None = None
        self._dataset_expires_at: datetime | None = None
        self._dataset_digest: str | None = None

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
        try:
            response = await self.transport.get(
                LAW_DATA_URL,
                timeout=self.timeout,
                max_bytes=MAX_ARCHIVE_BYTES,
            )
        except Exception as exc:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderHealthStatus.UNAVAILABLE,
                error_code=ProviderErrorCode.OFFICIAL_SOURCE_UNAVAILABLE.value,
                message=safe_transport_error(exc),
            )
        if response.status_code != 200:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderHealthStatus.UNAVAILABLE,
                error_code=ProviderErrorCode.OFFICIAL_SOURCE_UNAVAILABLE.value,
                message=f"HTTP_{response.status_code}",
            )
        return ProviderHealth(provider_id=self.provider_id, status=ProviderHealthStatus.HEALTHY)

    def _now(self, override: datetime | None = None) -> datetime:
        value = override if override is not None else self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("law provider clock must be timezone-aware")
        return value.astimezone(UTC)

    def _snapshot_is_fresh(self, timestamp: datetime) -> bool:
        return (
            self._laws is not None
            and self._dataset_fetched_at is not None
            and self._dataset_verified_at is not None
            and self._dataset_expires_at is not None
            and self._dataset_fetched_at <= timestamp < self._dataset_expires_at
        )

    def _clear_snapshot(self) -> None:
        self._laws = None
        self._dataset_updated_at = None
        self._dataset_fetched_at = None
        self._dataset_verified_at = None
        self._dataset_expires_at = None
        self._dataset_digest = None

    def _snapshot_metadata(self) -> dict[str, Any]:
        return {
            "dataset_updated_at": self._dataset_updated_at,
            "dataset_fetched_at": (
                self._dataset_fetched_at.isoformat() if self._dataset_fetched_at else None
            ),
            "dataset_verified_at": (
                self._dataset_verified_at.isoformat() if self._dataset_verified_at else None
            ),
            "dataset_expires_at": (
                self._dataset_expires_at.isoformat() if self._dataset_expires_at else None
            ),
            "dataset_digest": self._dataset_digest,
        }

    async def load(
        self, *, force: bool = False, now: datetime | None = None,
    ) -> ProviderResult:
        timestamp = self._now(now)
        if not force and self._snapshot_is_fresh(timestamp):
            assert self._laws is not None
            return ProviderResult(
                status=ProviderResultStatus.FOUND,
                provider_id=self.provider_id,
                coverage_complete=True,
                metadata={
                    **self._snapshot_metadata(),
                    "law_count": len(self._laws),
                    "cache": "memory",
                },
            )
        # 到期或強制重新取得時先撤銷舊快照；失敗不可回退或更新舊資料時間。
        self._clear_snapshot()
        try:
            response = await self.transport.get(
                LAW_DATA_URL,
                timeout=self.timeout,
                max_bytes=MAX_ARCHIVE_BYTES,
            )
        except Exception as exc:
            return self._error(
                ProviderErrorCode.OFFICIAL_SOURCE_UNAVAILABLE,
                safe_transport_error(exc),
            )
        if response.status_code != 200:
            return self._error(
                ProviderErrorCode.OFFICIAL_SOURCE_UNAVAILABLE,
                f"HTTP_{response.status_code}",
            )
        try:
            laws, updated_at = self.parse_archive(response.content)
        except (ValueError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
            return self._error(ProviderErrorCode.OFFICIAL_PARSE_ERROR, str(exc))
        verified_at = self._now(now)
        expires_at = timestamp + self.snapshot_ttl
        if not timestamp <= verified_at < expires_at:
            return self._error(ProviderErrorCode.SOURCE_STALE, "LAW_SNAPSHOT_EXPIRED_DURING_LOAD")
        # 完成解析後才一起安裝快照；期限以本次實際下載的起始觀察時間為準。
        self._laws = laws
        self._dataset_updated_at = updated_at
        self._dataset_fetched_at = timestamp
        self._dataset_verified_at = verified_at
        self._dataset_expires_at = expires_at
        self._dataset_digest = "sha256:" + hashlib.sha256(response.content).hexdigest()
        return ProviderResult(
            status=ProviderResultStatus.FOUND,
            provider_id=self.provider_id,
            coverage_complete=True,
            metadata={**self._snapshot_metadata(), "law_count": len(laws), "cache": "network"},
        )

    @staticmethod
    def parse_archive(payload: bytes) -> tuple[list[dict[str, Any]], str | None]:
        if len(payload) > MAX_ARCHIVE_BYTES:
            raise ValueError("ARCHIVE_TOO_LARGE")
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_FILES:
                raise ValueError("ARCHIVE_TOO_MANY_FILES")
            if any(info.is_dir() or "/" in info.filename or "\\" in info.filename for info in infos):
                raise ValueError("ARCHIVE_PATH_FORBIDDEN")
            if sum(info.file_size for info in infos) > MAX_UNCOMPRESSED_BYTES:
                raise ValueError("ARCHIVE_UNCOMPRESSED_TOO_LARGE")
            matches = [info for info in infos if info.filename == "ChLaw.json"]
            if len(matches) != 1:
                raise ValueError("LAW_JSON_MISSING")
            document = json.loads(archive.read(matches[0]).decode("utf-8-sig"))
        if not isinstance(document, dict) or not isinstance(document.get("Laws"), list):
            raise ValueError("LAW_SCHEMA_CHANGED")
        laws = document["Laws"]
        required = {"LawName", "LawURL", "LawArticles"}
        if any(not isinstance(item, dict) or not required <= set(item) for item in laws):
            raise ValueError("LAW_SCHEMA_CHANGED")
        return laws, document.get("UpdateDate")

    async def exact_lookup(
        self,
        law_name: str,
        article_no: str,
        *,
        now: datetime | None = None,
    ) -> tuple[ProviderResult, SourceRecord | None, EvidenceSpan | None]:
        loaded = await self.load(now=now)
        if loaded.status == ProviderResultStatus.ERROR:
            return loaded, None, None
        timestamp = self._now(now)
        if not self._snapshot_is_fresh(timestamp):
            return self._error(ProviderErrorCode.SOURCE_STALE, "LAW_SNAPSHOT_EXPIRED"), None, None
        assert self._laws is not None
        assert self._dataset_fetched_at is not None
        assert self._dataset_verified_at is not None
        assert self._dataset_expires_at is not None
        normalized_name = law_name.strip()
        normalized_article = self.normalize_article_no(article_no)
        law = next((item for item in self._laws if item.get("LawName") == normalized_name), None)
        if law is None:
            return self._not_found("LAW_NOT_FOUND"), None, None
        articles = law.get("LawArticles")
        if not isinstance(articles, list):
            return self._error(ProviderErrorCode.OFFICIAL_SCHEMA_CHANGED, "LAW_ARTICLES_INVALID"), None, None
        article = next(
            (
                item
                for item in articles
                if isinstance(item, dict)
                and self.normalize_article_no(str(item.get("ArticleNo", ""))) == normalized_article
            ),
            None,
        )
        if article is None:
            return self._not_found("ARTICLE_NOT_FOUND"), None, None
        text = str(article.get("ArticleContent", "")).strip()
        if not text:
            return self._error(ProviderErrorCode.OFFICIAL_PARSE_ERROR, "ARTICLE_CONTENT_EMPTY"), None, None
        official_url = str(law["LawURL"])
        if not self._is_official_url(official_url):
            return self._error(ProviderErrorCode.OFFICIAL_SCHEMA_CHANGED, "LAW_URL_NOT_OFFICIAL"), None, None
        official_identifier = self._official_identifier(official_url, normalized_name, normalized_article)
        identity = (
            f"{official_identifier}\n{law.get('LawModifiedDate', '')}\n"
            f"{timestamp.isoformat()}\n{text}"
        )
        digest = hashlib.sha256(identity.encode()).hexdigest()
        source_id = f"src_law_{digest[:24]}"
        content_hash = EvidenceSpan.hash_text(text)
        source = SourceRecord(
            source_id=source_id,
            source_key=f"law:{official_identifier}",
            source_version_id=f"{official_identifier}:{law.get('LawModifiedDate', 'unknown')}",
            material_type=MaterialType.LAW,
            provider_id=self.provider_id,
            source_tier=SourceTier.OFFICIAL,
            trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
            official_identifier=official_identifier,
            official_url=official_url,
            citation=f"{normalized_name}第{normalized_article}條",
            title=normalized_name,
            fetched_at=self._dataset_fetched_at,
            verified_at=self._dataset_verified_at,
            expires_at=self._dataset_expires_at,
            content_hash=content_hash,
            normalized_content_hash=content_hash,
            normalized_text=text,
            metadata={
                "law_modified_date": law.get("LawModifiedDate"),
                "law_effective_date": law.get("LawEffectiveDate"),
                "law_abandon_note": law.get("LawAbandonNote"),
                **self._snapshot_metadata(),
                "lookup_checked_at": timestamp.isoformat(),
                "article_no": normalized_article,
            },
            warnings=["LAW_REPEALED"] if law.get("LawAbandonNote") else [],
        )
        evidence = EvidenceSpan.from_exact_text(
            evidence_id=f"ev_{source_id}_{hashlib.sha256(normalized_article.encode()).hexdigest()[:12]}",
            source_id=source_id,
            section_id=f"article-{normalized_article}",
            section_type=EvidenceSectionType.LAW_TEXT,
            exact_text=text,
            eligible_for_claim_support=not bool(law.get("LawAbandonNote")),
        )
        conflict = False
        if self.verify_webpage and not law.get("LawAbandonNote"):
            source, evidence, conflict = await self._verify_webpage(source, evidence, now=now)
        # 網頁複核不得替結構化快照續期；長時間查詢跨過期限也不得輸出可用證據。
        if not source.fetched_at <= self._now(now) < source.expires_at:
            return (
                self._error(ProviderErrorCode.SOURCE_STALE, "LAW_SNAPSHOT_EXPIRED_DURING_LOOKUP"),
                None,
                None,
            )
        status = ProviderResultStatus.FOUND
        result = ProviderResult(
            status=ProviderResultStatus.ERROR if conflict else status,
            provider_id=self.provider_id,
            source_ids=[source.source_id],
            evidence_ids=[evidence.evidence_id],
            error_code=ProviderErrorCode.OFFICIAL_CONTENT_CONFLICT if conflict else None,
            message="OFFICIAL_CONTENT_CONFLICT" if conflict else "",
            coverage_complete=not conflict,
            metadata={"repealed": bool(law.get("LawAbandonNote"))},
        )
        return result, source, evidence

    async def _verify_webpage(
        self,
        source: SourceRecord,
        evidence: EvidenceSpan,
        *,
        now: datetime | None = None,
    ) -> tuple[SourceRecord, EvidenceSpan, bool]:
        assert source.official_url is not None
        try:
            response = await self.transport.get(
                source.official_url,
                timeout=self.timeout,
                max_bytes=MAX_WEBPAGE_BYTES,
            )
        except Exception as exc:
            warning = f"OFFICIAL_WEB_RECHECK_UNAVAILABLE:{safe_transport_error(exc)}"
            return source.model_copy(update={"warnings": source.warnings + [warning]}), evidence, False
        if response.status_code != 200:
            warning = f"OFFICIAL_WEB_RECHECK_UNAVAILABLE:HTTP_{response.status_code}"
            return source.model_copy(update={"warnings": source.warnings + [warning]}), evidence, False
        try:
            document = response.content.decode("utf-8")
        except UnicodeDecodeError:
            return (
                source.model_copy(update={"warnings": source.warnings + ["OFFICIAL_WEB_INVALID_UTF8"]}),
                evidence,
                False,
            )
        visible = re.sub(r"<(?:script|style)[^>]*>.*?</(?:script|style)>", "", document, flags=re.I | re.S)
        visible = html.unescape(re.sub(r"<[^>]+>", "", visible))
        normalized_page = re.sub(r"\s+", "", visible)
        normalized_evidence = re.sub(r"\s+", "", evidence.exact_text)
        if normalized_evidence in normalized_page:
            # 額外複核時間與資料集取得／解析時間分離，既有期限保持不變。
            return (
                source.model_copy(update={"metadata": {
                    **source.metadata,
                    "webpage_verified_at": self._now(now).isoformat(),
                }}),
                evidence,
                False,
            )
        return (
            source.model_copy(
                update={
                    "trust_status": TrustStatus.VERIFICATION_FAILED,
                    "warnings": source.warnings + ["OFFICIAL_CONTENT_CONFLICT"],
                }
            ),
            evidence.model_copy(update={"eligible_for_claim_support": False}),
            True,
        )

    async def search(self, query: str, *, limit: int = 10) -> ProviderResult:
        loaded = await self.load()
        if loaded.status == ProviderResultStatus.ERROR:
            return loaded
        assert self._laws is not None
        needle = query.strip()
        if not needle:
            raise ValueError("query is required")
        matches: list[dict[str, Any]] = []
        for law in self._laws:
            name = str(law.get("LawName", ""))
            articles = law.get("LawArticles", [])
            content_match = any(
                needle in str(article.get("ArticleContent", ""))
                for article in articles
                if isinstance(article, dict)
            )
            if needle in name or content_match:
                matches.append(
                    {
                        "law_name": name,
                        "official_url": law.get("LawURL"),
                        "repealed": bool(law.get("LawAbandonNote")),
                    }
                )
                if len(matches) >= max(1, min(limit, 50)):
                    break
        return ProviderResult(
            status=ProviderResultStatus.FOUND if matches else ProviderResultStatus.NOT_FOUND,
            provider_id=self.provider_id,
            error_code=None if matches else ProviderErrorCode.OFFICIAL_SOURCE_NOT_FOUND,
            coverage_complete=True,
            metadata={"matches": matches},
        )

    async def resolve_citations(self, text: str, *, limit: int = 5) -> list[tuple[str, str]]:
        """Resolve law names from the official catalog, not a fixed local name list."""

        loaded = await self.load()
        if loaded.status == ProviderResultStatus.ERROR:
            return []
        assert self._laws is not None
        compact = re.sub(r"\s+", "", text)
        matches: list[tuple[str, str]] = []
        names = sorted(
            {str(item.get("LawName") or "") for item in self._laws},
            key=len,
            reverse=True,
        )
        for name in names:
            if not name:
                continue
            pattern = re.compile(
                rf"{re.escape(name)}第?(?P<article>\d+(?:(?:之|-)\d+)*)條"
            )
            for citation in pattern.finditer(compact):
                pair = (name, self.normalize_article_no(citation.group("article")))
                if pair not in matches:
                    matches.append(pair)
                if len(matches) >= max(1, min(limit, 20)):
                    return matches
        return matches

    @staticmethod
    def normalize_article_no(value: str) -> str:
        normalized = value.strip().replace("第", "").replace("條", "")
        normalized = re.sub(r"\s+", "", normalized).replace("之", "-")
        normalized = normalized.lstrip("0") or "0"
        return normalized

    @staticmethod
    def _is_official_url(url: str) -> bool:
        return url.startswith(f"https://{LAW_HOST}/")

    @staticmethod
    def _official_identifier(url: str, law_name: str, article_no: str) -> str:
        match = re.search(r"[?&]pcode=([A-Za-z0-9]+)", url)
        return f"{match.group(1)}:{article_no}" if match else f"{law_name}:{article_no}"

    def _not_found(self, message: str) -> ProviderResult:
        return ProviderResult(
            status=ProviderResultStatus.NOT_FOUND,
            provider_id=self.provider_id,
            error_code=ProviderErrorCode.OFFICIAL_SOURCE_NOT_FOUND,
            message=message,
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
