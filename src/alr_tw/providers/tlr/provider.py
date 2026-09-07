"""TLR HTTP adapter for candidate recall and bounded candidate-text access."""

from __future__ import annotations

import hashlib
import importlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Mapping, Protocol
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from alr_tw._version import __version__
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
from alr_tw.contracts.public_law import (
    PublicLawCandidate,
    PublicLawMaterialType,
    PublicLawProviderCapabilities,
    PublicLawProviderResult,
    PublicLawResultStatus,
    PublicLawSearchRequest,
    PublicLawSourceRole,
)
from alr_tw.contracts.sources import (
    MaterialType,
    SourceRecord,
    SourceTier,
    TrustStatus,
)
from alr_tw.providers.official.http import system_truststore_context
from alr_tw.providers.official.judgments import OfficialJudgmentProvider

from .privacy import PrivacyScreenResult, screen_external_query

MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_FULLTEXT_PAGES = 8
MAX_TLR_RESULTS = 10
MAX_CANDIDATE_EXCERPT_CHARS = 4000

TlrAdministrativeSourceKind = Literal[
    "administrative_interpretation",
    "tax_interpretation",
]

_FULLTEXT_CITATION_HEADER = re.compile(
    r"\A(?:引用連結:[^\r\n]*(?:\r?\n))?"
    r"引用字號:[^\r\n]*(?:\r?\n){2}"
)


@dataclass(frozen=True)
class TlrHttpResponse:
    status_code: int
    payload: Any


class TlrCaseHistoryEntry(BaseModel):
    """One untrusted database-recorded upper/lower instance returned by TLR."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.tlr-case-history-entry/v1"] = (
        "alr-tw.tlr-case-history-entry/v1"
    )
    trust_status: Literal["external_candidate_metadata"] = "external_candidate_metadata"
    evidence_eligible: Literal[False] = False
    direction: Literal["upper", "lower"]
    provider_document_id: str = Field(min_length=1, max_length=500)
    canonical_jid: str | None = Field(default=None, max_length=500)
    citation_text: str = Field(min_length=1, max_length=1000)
    doc_type: str | None = Field(default=None, max_length=200)
    decision_date: str | None = Field(default=None, max_length=64)
    main_flag: str | None = Field(default=None, max_length=500)
    vacated_marker: bool = False


class TlrCaseHistoryRecord(BaseModel):
    """Bounded TLR history metadata; never official evidence or finality proof."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.tlr-case-history/v1"] = "alr-tw.tlr-case-history/v1"
    provider_id: Literal["tlr_semantic_recall"] = "tlr_semantic_recall"
    trust_status: Literal["external_candidate_metadata"] = "external_candidate_metadata"
    root_provider_document_id: str = Field(min_length=1, max_length=500)
    root_canonical_jid: str | None = Field(default=None, max_length=500)
    root_citation_text: str = Field(min_length=1, max_length=1000)
    history_present: bool
    entries: list[TlrCaseHistoryEntry] = Field(default_factory=list, max_length=128)
    provider_note: str | None = Field(default=None, max_length=4000)
    coverage_complete: Literal[False] = False
    establishes_finality: Literal[False] = False
    semantic_opinion_comparison_performed: Literal[False] = False


class TlrFulltextPage(BaseModel):
    """One bounded page of untrusted TLR judgment text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.tlr-fulltext-page/v1"] = (
        "alr-tw.tlr-fulltext-page/v1"
    )
    excerpt_offset: int = Field(ge=0)
    returned_chars: int = Field(ge=0)
    fulltext_total_chars: int = Field(ge=0)
    fulltext_truncated: bool
    next_excerpt_offset: int | None = Field(default=None, ge=0)


class TlrCandidateFulltextRecord(BaseModel):
    """Paged TLR text retained only as an external candidate locator."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.tlr-candidate-fulltext/v1"] = (
        "alr-tw.tlr-candidate-fulltext/v1"
    )
    provider_id: Literal["tlr_semantic_recall"] = "tlr_semantic_recall"
    trust_status: Literal["external_candidate_content"] = "external_candidate_content"
    evidence_eligible: Literal[False] = False
    official_verification_required: Literal[True] = True
    provider_document_id: str = Field(min_length=1, max_length=500)
    canonical_jid: str | None = Field(default=None, max_length=500)
    citation_text: str = Field(min_length=1, max_length=1000)
    text: str
    initial_excerpt_offset: int = Field(ge=0)
    returned_chars: int = Field(ge=0)
    fulltext_total_chars: int = Field(ge=0)
    fulltext_truncated: bool
    next_excerpt_offset: int | None = Field(default=None, ge=0)
    page_count: int = Field(ge=1, le=MAX_FULLTEXT_PAGES)
    pages: list[TlrFulltextPage] = Field(min_length=1, max_length=MAX_FULLTEXT_PAGES)
    provider_content_complete: bool
    coverage_complete: Literal[False] = False


class TlrTransport(Protocol):
    async def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout: float,
        max_bytes: int,
    ) -> TlrHttpResponse: ...

    async def post_json(
        self,
        url: str,
        body: Mapping[str, Any],
        *,
        headers: Mapping[str, str],
        timeout: float,
        max_bytes: int,
    ) -> TlrHttpResponse: ...


class HttpxTlrTransport:
    async def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout: float,
        max_bytes: int,
    ) -> TlrHttpResponse:
        return await self._request("GET", url, None, headers, timeout, max_bytes)

    async def post_json(
        self,
        url: str,
        body: Mapping[str, Any],
        *,
        headers: Mapping[str, str],
        timeout: float,
        max_bytes: int,
    ) -> TlrHttpResponse:
        return await self._request("POST", url, body, headers, timeout, max_bytes)

    @staticmethod
    async def _request(
        method: str,
        url: str,
        body: Mapping[str, Any] | None,
        headers: Mapping[str, str],
        timeout: float,
        max_bytes: int,
    ) -> TlrHttpResponse:
        try:
            httpx: Any = importlib.import_module("httpx")
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("TLR_EXTRA_REQUIRED") from exc
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            verify=system_truststore_context(),
        ) as client:
            async with client.stream(
                method,
                url,
                json=body,
                headers=dict(headers),
            ) as response:
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise RuntimeError("RESPONSE_TOO_LARGE")
                    chunks.append(chunk)
                content = b"".join(chunks)
        try:
            payload = json.loads(content)
        except (UnicodeDecodeError, ValueError) as exc:
            raise RuntimeError("TLR_RESPONSE_NOT_JSON") from exc
        return TlrHttpResponse(response.status_code, payload)


class TlrSemanticRecallProvider:
    provider_id = "tlr_semantic_recall"

    def __init__(
        self,
        base_url: str = "https://tlr.dr-lawbot.com",
        credential: SecretStr | str | None = None,
        transport: TlrTransport | None = None,
        *,
        timeout: float = 12.0,
        max_retries: int = 1,
        candidate_ttl: timedelta = timedelta(hours=24),
    ):
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("TLR_BASE_URL_INVALID")
        self.base_url = base_url.rstrip("/")
        self._api_key = (
            credential
            if isinstance(credential, SecretStr)
            else SecretStr(credential)
            if credential
            else None
        )
        self.transport = transport or HttpxTlrTransport()
        self.timeout = timeout
        self.max_retries = max(0, min(max_retries, 2))
        self.candidate_ttl = candidate_ttl

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            exact_lookup=False,
            keyword_search=False,
            semantic_recall=True,
            official_verification=False,
            historical_versions=False,
            current_status_check=False,
            external_query_transfer=True,
        )

    def public_law_capabilities(self) -> PublicLawProviderCapabilities:
        """Advertise only the candidate-only public-law surface."""

        return PublicLawProviderCapabilities(
            provider_id=self.provider_id,
            material_types=[PublicLawMaterialType.ADMINISTRATIVE_INTERPRETATION],
            keyword_search=False,
            semantic_recall=True,
            exact_lookup=False,
            historical_versions=False,
            server_verification=False,
            external_query_transfer=True,
            max_results=MAX_TLR_RESULTS,
        )

    async def health_check(self) -> ProviderHealth:
        try:
            response = await self.transport.get_json(
                f"{self.base_url}/openapi.json",
                headers=self._headers(),
                timeout=self.timeout,
                max_bytes=MAX_RESPONSE_BYTES,
            )
        except Exception as exc:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderHealthStatus.UNAVAILABLE,
                error_code=ProviderErrorCode.TLR_UNAVAILABLE.value,
                message=type(exc).__name__,
            )
        status = (
            ProviderHealthStatus.HEALTHY
            if response.status_code == 200 and isinstance(response.payload, dict)
            else ProviderHealthStatus.UNAVAILABLE
        )
        return ProviderHealth(
            provider_id=self.provider_id,
            status=status,
            error_code=(
                None
                if status == ProviderHealthStatus.HEALTHY
                else ProviderErrorCode.TLR_UNAVAILABLE.value
            ),
            message="" if status == ProviderHealthStatus.HEALTHY else f"HTTP_{response.status_code}",
        )

    async def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        now: datetime | None = None,
    ) -> tuple[ProviderResult, list[SourceRecord], PrivacyScreenResult]:
        privacy = screen_external_query(query)
        if not privacy.allowed or privacy.query_to_send is None:
            return (
                ProviderResult(
                    status=ProviderResultStatus.ERROR,
                    provider_id=self.provider_id,
                    error_code=ProviderErrorCode.PRIVACY_EXTERNAL_QUERY_BLOCKED,
                    message=privacy.status.value,
                    coverage_complete=False,
                ),
                [],
                privacy,
            )
        limit = max(1, min(top_k, 10))
        response: TlrHttpResponse | None = None
        try:
            for attempt in range(self.max_retries + 1):
                response = await self.transport.post_json(
                    f"{self.base_url}/v1/search",
                    {"query": privacy.query_to_send, "max_results": limit},
                    headers=self._headers(),
                    timeout=self.timeout,
                    max_bytes=MAX_RESPONSE_BYTES,
                )
                if response.status_code not in {429, 500, 502, 503, 504} or attempt >= self.max_retries:
                    break
        except Exception as exc:
            return self._unavailable(type(exc).__name__), [], privacy
        assert response is not None
        if response.status_code != 200:
            return self._unavailable(f"HTTP_{response.status_code}"), [], privacy
        try:
            candidates, sources = self._normalize_response(
                response.payload,
                now or datetime.now(UTC),
                limit=limit,
            )
        except ValueError as exc:
            return (
                ProviderResult(
                    status=ProviderResultStatus.ERROR,
                    provider_id=self.provider_id,
                    error_code=ProviderErrorCode.EXTERNAL_PROVIDER_SCHEMA_CHANGED,
                    message=str(exc),
                    coverage_complete=False,
                ),
                [],
                privacy,
            )
        return (
            ProviderResult(
                status=(ProviderResultStatus.FOUND if candidates else ProviderResultStatus.NOT_FOUND),
                provider_id=self.provider_id,
                source_ids=[source.source_id for source in sources],
                candidates=candidates,
                coverage_complete=True,
                metadata={"query_redacted": privacy.status.value == "redacted_safe"},
            ),
            sources,
            privacy,
        )

    async def search_administrative_interpretations(
        self,
        request: PublicLawSearchRequest,
        *,
        authority: str | None = None,
        source_kind: TlrAdministrativeSourceKind = "administrative_interpretation",
    ) -> tuple[PublicLawProviderResult, PrivacyScreenResult]:
        """Recall TLR administrative-interpretation candidates without sources.

        The result intentionally has no server metadata or promoted source.  A
        separate ALR-TW official public-law adapter must verify the identifier,
        current status, and text before evidence can be created.
        """

        privacy = screen_external_query(request.query)
        if set(request.material_types) != {
            PublicLawMaterialType.ADMINISTRATIVE_INTERPRETATION
        }:
            return (
                self._public_law_result(
                    request,
                    status=PublicLawResultStatus.BLOCKED,
                    reason_codes=["PUBLIC_LAW_MATERIAL_TYPE_UNSUPPORTED"],
                ),
                privacy,
            )
        if source_kind not in {
            "administrative_interpretation",
            "tax_interpretation",
        }:
            return (
                self._public_law_result(
                    request,
                    status=PublicLawResultStatus.BLOCKED,
                    reason_codes=["TLR_PUBLIC_LAW_SOURCE_KIND_UNSUPPORTED"],
                ),
                privacy,
            )
        if authority is not None and not isinstance(authority, str):
            return (
                self._public_law_result(
                    request,
                    status=PublicLawResultStatus.BLOCKED,
                    reason_codes=["TLR_PUBLIC_LAW_AUTHORITY_INVALID"],
                ),
                privacy,
            )
        authority_filter = authority.strip() if authority is not None else None
        if authority_filter == "":
            authority_filter = None
        if authority_filter is not None and len(authority_filter) > 120:
            return (
                self._public_law_result(
                    request,
                    status=PublicLawResultStatus.BLOCKED,
                    reason_codes=["TLR_PUBLIC_LAW_AUTHORITY_INVALID"],
                ),
                privacy,
            )
        if authority_filter is not None:
            authority_privacy = screen_external_query(authority_filter)
            if authority_privacy.status.value != "safe":
                return (
                    self._public_law_result(
                        request,
                        status=PublicLawResultStatus.BLOCKED,
                        reason_codes=[ProviderErrorCode.PRIVACY_EXTERNAL_QUERY_BLOCKED.value],
                        metadata={"privacy_status": authority_privacy.status.value},
                    ),
                    authority_privacy,
                )

        if not privacy.allowed or privacy.query_to_send is None:
            return (
                self._public_law_result(
                    request,
                    status=PublicLawResultStatus.BLOCKED,
                    reason_codes=[ProviderErrorCode.PRIVACY_EXTERNAL_QUERY_BLOCKED.value],
                    metadata={"privacy_status": privacy.status.value},
                ),
                privacy,
            )

        limit = min(request.max_results, MAX_TLR_RESULTS)
        body: dict[str, Any] = {
            "query": privacy.query_to_send,
            "source_kind": source_kind,
            "max_results": limit,
        }
        if authority_filter is not None:
            body["authority"] = authority_filter
        response: TlrHttpResponse | None = None
        try:
            for attempt in range(self.max_retries + 1):
                response = await self.transport.post_json(
                    f"{self.base_url}/v1/legal_references/search",
                    body,
                    headers=self._headers(),
                    timeout=self.timeout,
                    max_bytes=MAX_RESPONSE_BYTES,
                )
                if (
                    response.status_code not in {429, 500, 502, 503, 504}
                    or attempt >= self.max_retries
                ):
                    break
        except Exception as exc:
            return (
                self._public_law_result(
                    request,
                    status=PublicLawResultStatus.RETRY_REQUIRED,
                    reason_codes=[ProviderErrorCode.TLR_UNAVAILABLE.value],
                    metadata={"provider_error": type(exc).__name__},
                ),
                privacy,
            )
        assert response is not None
        if response.status_code != 200:
            return (
                self._public_law_result(
                    request,
                    status=PublicLawResultStatus.RETRY_REQUIRED,
                    reason_codes=[ProviderErrorCode.TLR_UNAVAILABLE.value],
                    metadata={"provider_status_code": response.status_code},
                ),
                privacy,
            )
        try:
            candidates, provider_metadata, normalization_reasons = (
                self._normalize_public_law_candidates(
                    response.payload,
                    source_kind=source_kind,
                    limit=limit,
                )
            )
        except ValueError as exc:
            return (
                self._public_law_result(
                    request,
                    status=PublicLawResultStatus.RETRY_REQUIRED,
                    reason_codes=["TLR_PUBLIC_LAW_SCHEMA_CHANGED"],
                    metadata={"provider_error": str(exc)},
                ),
                privacy,
            )

        truncated = request.max_results > MAX_TLR_RESULTS
        reason_codes = ["PUBLIC_LAW_CANDIDATES_ONLY", "PUBLIC_LAW_COVERAGE_PARTIAL"]
        reason_codes.extend(normalization_reasons)
        if truncated:
            reason_codes.append("PUBLIC_LAW_RESULT_LIMIT_TRUNCATED")
        if not candidates:
            reason_codes.append("TLR_PUBLIC_LAW_NOT_FOUND_IS_BOUNDED_ONLY")
        return (
            self._public_law_result(
                request,
                status=PublicLawResultStatus.PARTIAL,
                candidates=candidates,
                truncated=truncated,
                reason_codes=list(dict.fromkeys(reason_codes)),
                metadata={
                    **provider_metadata,
                    "query_redacted": privacy.status.value == "redacted_safe",
                    "authority_filter": authority_filter,
                    "source_kind_filter": source_kind,
                    "official_verification_required": True,
                },
            ),
            privacy,
        )

    async def read_candidate_fulltext(
        self,
        doc_id: str,
        result_token: str,
        *,
        excerpt_offset: int = 0,
        max_pages: int = 6,
    ) -> tuple[ProviderResult, TlrCandidateFulltextRecord | None]:
        """Read bounded TLR pages without creating a source or evidence span."""

        normalized_doc_id = doc_id.strip()
        normalized_token = result_token.strip()
        if (
            not normalized_doc_id
            or not normalized_token
            or len(normalized_doc_id) > 500
            or len(normalized_token) > 4096
        ):
            return self._invalid_fulltext_handle(), None
        if (
            isinstance(excerpt_offset, bool)
            or not isinstance(excerpt_offset, int)
            or excerpt_offset < 0
            or excerpt_offset > 10_000_000
        ):
            return self._invalid_fulltext_window("TLR_FULLTEXT_OFFSET_INVALID"), None
        if (
            isinstance(max_pages, bool)
            or not isinstance(max_pages, int)
            or not 1 <= max_pages <= MAX_FULLTEXT_PAGES
        ):
            return self._invalid_fulltext_window("TLR_FULLTEXT_PAGE_LIMIT_INVALID"), None

        current_offset = excerpt_offset
        expected_citation: str | None = None
        expected_total: int | None = None
        page_metadata: list[TlrFulltextPage] = []
        text_parts: list[str] = []
        for _ in range(max_pages):
            body: dict[str, Any] = {
                "doc_id": normalized_doc_id,
                "result_token": normalized_token,
            }
            if current_offset:
                body["excerpt_offset"] = current_offset
            try:
                response = await self.transport.post_json(
                    f"{self.base_url}/v1/fulltext",
                    body,
                    headers=self._headers(),
                    timeout=self.timeout,
                    max_bytes=MAX_RESPONSE_BYTES,
                )
            except Exception as exc:
                return self._unavailable(type(exc).__name__), None

            error = self._fulltext_response_error(response)
            if error is not None:
                return error, None
            try:
                citation, text, page = self._normalize_fulltext_page(
                    response.payload,
                    requested_doc_id=normalized_doc_id,
                    requested_offset=current_offset,
                    expected_citation=expected_citation,
                    expected_total=expected_total,
                )
            except ValueError as exc:
                return (
                    ProviderResult(
                        status=ProviderResultStatus.ERROR,
                        provider_id=self.provider_id,
                        error_code=ProviderErrorCode.EXTERNAL_PROVIDER_SCHEMA_CHANGED,
                        message=str(exc),
                        coverage_complete=False,
                    ),
                    None,
                )
            expected_citation = citation
            expected_total = page.fulltext_total_chars
            page_metadata.append(page)
            text_parts.append(text)
            if not page.fulltext_truncated:
                break
            assert page.next_excerpt_offset is not None
            current_offset = page.next_excerpt_offset

        assert expected_citation is not None and expected_total is not None
        last_page = page_metadata[-1]
        returned_chars = sum(page.returned_chars for page in page_metadata)
        provider_content_complete = (
            excerpt_offset == 0
            and not last_page.fulltext_truncated
            and returned_chars == expected_total
        )
        record = TlrCandidateFulltextRecord(
            provider_document_id=normalized_doc_id,
            canonical_jid=OfficialJudgmentProvider.normalize_jid(normalized_doc_id),
            citation_text=expected_citation,
            text="".join(text_parts),
            initial_excerpt_offset=excerpt_offset,
            returned_chars=returned_chars,
            fulltext_total_chars=expected_total,
            fulltext_truncated=last_page.fulltext_truncated,
            next_excerpt_offset=last_page.next_excerpt_offset,
            page_count=len(page_metadata),
            pages=page_metadata,
            provider_content_complete=provider_content_complete,
        )
        return (
            ProviderResult(
                status=(
                    ProviderResultStatus.FOUND
                    if provider_content_complete
                    else ProviderResultStatus.PARTIAL
                ),
                provider_id=self.provider_id,
                coverage_complete=False,
                metadata={
                    "candidate_fulltext_only": True,
                    "evidence_eligible": False,
                    "official_verification_required": True,
                    "page_count": record.page_count,
                    "returned_chars": record.returned_chars,
                    "fulltext_total_chars": record.fulltext_total_chars,
                    "fulltext_truncated": record.fulltext_truncated,
                    "next_excerpt_offset": record.next_excerpt_offset,
                    "provider_content_complete": record.provider_content_complete,
                },
            ),
            record,
        )

    async def case_history(
        self,
        doc_id: str,
        result_token: str,
    ) -> tuple[ProviderResult, TlrCaseHistoryRecord | None]:
        """Read only TLR's history metadata and discard its non-official full text.

        The endpoint is named ``fulltext`` upstream, but this adapter deliberately
        projects only identity and ``case_history`` fields.  Court reasoning still
        has to be fetched through the configured official judgment provider.
        """

        normalized_doc_id = doc_id.strip()
        normalized_token = result_token.strip()
        if not normalized_doc_id or not normalized_token:
            return (
                ProviderResult(
                    status=ProviderResultStatus.ERROR,
                    provider_id=self.provider_id,
                    error_code=ProviderErrorCode.INVALID_IDENTIFIER,
                    message="TLR_FULLTEXT_HANDLE_REQUIRED",
                    coverage_complete=False,
                ),
                None,
            )
        if len(normalized_doc_id) > 500 or len(normalized_token) > 4096:
            return (
                ProviderResult(
                    status=ProviderResultStatus.ERROR,
                    provider_id=self.provider_id,
                    error_code=ProviderErrorCode.INVALID_IDENTIFIER,
                    message="TLR_FULLTEXT_HANDLE_TOO_LONG",
                    coverage_complete=False,
                ),
                None,
            )
        try:
            response = await self.transport.post_json(
                f"{self.base_url}/v1/fulltext",
                {"doc_id": normalized_doc_id, "result_token": normalized_token},
                headers=self._headers(),
                timeout=self.timeout,
                max_bytes=MAX_RESPONSE_BYTES,
            )
        except Exception as exc:
            return self._unavailable(type(exc).__name__), None

        error = self._fulltext_response_error(response)
        if error is not None:
            return error, None
        try:
            record = self._normalize_case_history(response.payload, normalized_doc_id)
        except ValueError as exc:
            return (
                ProviderResult(
                    status=ProviderResultStatus.ERROR,
                    provider_id=self.provider_id,
                    error_code=ProviderErrorCode.EXTERNAL_PROVIDER_SCHEMA_CHANGED,
                    message=str(exc),
                    coverage_complete=False,
                ),
                None,
            )
        return (
            ProviderResult(
                status=(
                    ProviderResultStatus.FOUND
                    if record.history_present
                    else ProviderResultStatus.PARTIAL
                ),
                provider_id=self.provider_id,
                coverage_complete=False,
                metadata={
                    "case_history_present": record.history_present,
                    "case_history_entry_count": len(record.entries),
                    "database_recorded_only": True,
                    "establishes_finality": False,
                },
            ),
            record,
        )

    def _normalize_response(
        self,
        payload: Any,
        timestamp: datetime,
        *,
        limit: int,
    ) -> tuple[list[ProviderCandidate], list[SourceRecord]]:
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise ValueError("TLR_SEARCH_SCHEMA_CHANGED")
        if len(payload["results"]) > limit:
            raise ValueError("TLR_SEARCH_RESULT_LIMIT_EXCEEDED")
        candidates: list[ProviderCandidate] = []
        sources: list[SourceRecord] = []
        for rank, raw in enumerate(payload["results"], start=1):
            if not isinstance(raw, dict):
                raise ValueError("TLR_RESULT_INVALID")
            required = {"doc_id", "citation_text"}
            if not required <= set(raw):
                raise ValueError("TLR_RESULT_SCHEMA_CHANGED")
            doc_id = str(raw["doc_id"]).strip()
            citation = str(raw["citation_text"]).strip()
            if not doc_id or not citation:
                raise ValueError("TLR_RESULT_IDENTITY_EMPTY")
            snippet = str(raw.get("snippet") or "").strip()
            raw_hit_excerpt = str(raw.get("hit_excerpt") or "").strip()
            hit_excerpt = raw_hit_excerpt[:MAX_CANDIDATE_EXCERPT_CHARS]
            candidate_excerpt = hit_excerpt or snippet[:MAX_CANDIDATE_EXCERPT_CHARS]
            citation_url = str(raw.get("citation_url") or "").strip() or None
            result_token = str(raw.get("result_token") or "").strip() or None
            identity = hashlib.sha256(f"{doc_id}\n{citation}".encode()).hexdigest()
            snapshot_identity = hashlib.sha256(
                f"{identity}\n{timestamp.isoformat()}".encode()
            ).hexdigest()
            source_id = f"src_tlr_{snapshot_identity[:24]}"
            candidate = ProviderCandidate(
                candidate_id=f"tlr_{identity[:20]}",
                provider_id=self.provider_id,
                title=citation,
                official_identifier=citation,
                official_url=citation_url,
                excerpt=candidate_excerpt or None,
                score=None,
                identity=CandidateIdentity(
                    canonical_jid=(
                        OfficialJudgmentProvider.normalize_jid(doc_id)
                        or OfficialJudgmentProvider.jid_from_identifier(citation_url or "")
                    ),
                    provider_document_id=doc_id,
                    formal_citation=citation,
                    official_url=citation_url,
                ),
                candidate_rank=int(raw.get("rank") or rank),
                metadata={
                    "rank": int(raw.get("rank") or rank),
                    "doc_id": doc_id,
                    "court_name": raw.get("court_name"),
                    "decision_date": raw.get("jdate"),
                    "case_category": raw.get("case_category"),
                    "result_token": result_token,
                    "structural_snippet": snippet or None,
                    "hit_excerpt": hit_excerpt or None,
                    "hit_excerpt_total_chars": len(raw_hit_excerpt),
                    "hit_excerpt_truncated": len(raw_hit_excerpt) > len(hit_excerpt),
                },
            )
            normalized_text = candidate_excerpt or f"TLR candidate: {citation}"
            content_hash = EvidenceSpanHash.hash_text(normalized_text)
            source = SourceRecord(
                source_id=source_id,
                source_key=f"tlr:{doc_id}",
                source_version_id=f"tlr:{doc_id}:{identity[:16]}",
                material_type=MaterialType.JUDGMENT,
                provider_id=self.provider_id,
                source_tier=SourceTier.EXTERNAL_SEMANTIC_RECALL,
                trust_status=TrustStatus.EXTERNAL_CANDIDATE,
                official_identifier=citation,
                official_url=citation_url,
                citation=citation,
                title=citation,
                fetched_at=timestamp,
                verified_at=None,
                expires_at=timestamp + self.candidate_ttl,
                content_hash=content_hash,
                normalized_content_hash=content_hash,
                normalized_text=normalized_text,
                metadata=candidate.metadata,
                warnings=[
                    "TLR_CANDIDATE_ONLY",
                    "TLR_SNIPPET_IS_NOT_COURT_REASONING_EVIDENCE",
                    "TLR_HIT_EXCERPT_IS_NOT_EVIDENCE",
                ],
            )
            candidates.append(candidate)
            sources.append(source)
        return candidates, sources

    def _normalize_public_law_candidates(
        self,
        payload: Any,
        *,
        source_kind: TlrAdministrativeSourceKind,
        limit: int,
    ) -> tuple[
        list[PublicLawCandidate],
        dict[str, str | int | bool | None],
        list[str],
    ]:
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise ValueError("TLR_PUBLIC_LAW_SEARCH_SCHEMA_CHANGED")
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("TLR_PUBLIC_LAW_RESULT_LIMIT_INVALID")
        if len(payload["results"]) > limit:
            raise ValueError("TLR_PUBLIC_LAW_RESULT_LIMIT_EXCEEDED")

        rejected = payload.get("rejected", {})
        if not isinstance(rejected, dict):
            raise ValueError("TLR_PUBLIC_LAW_REJECTED_SCHEMA_CHANGED")
        rejected_count = 0
        for count in rejected.values():
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError("TLR_PUBLIC_LAW_REJECTED_COUNT_INVALID")
            rejected_count += count

        candidates: list[PublicLawCandidate] = []
        seen_ids: set[str] = set()
        for rank, raw in enumerate(payload["results"], start=1):
            if not isinstance(raw, dict):
                raise ValueError("TLR_PUBLIC_LAW_RESULT_INVALID")
            returned_kind = str(raw.get("source_kind") or "").strip()
            citation = str(raw.get("citation") or "").strip()
            if returned_kind != source_kind or not citation:
                raise ValueError("TLR_PUBLIC_LAW_RESULT_IDENTITY_INVALID")
            serial_no = str(raw.get("serial_no") or "").strip() or None
            canonical_id = str(raw.get("canonical_id") or "").strip() or None
            official_identifier = serial_no or canonical_id
            if official_identifier is not None and len(official_identifier) > 500:
                raise ValueError("TLR_PUBLIC_LAW_IDENTIFIER_TOO_LONG")
            raw_title = str(raw.get("title") or citation).strip()
            if not raw_title:
                raise ValueError("TLR_PUBLIC_LAW_TITLE_EMPTY")
            title = raw_title[:500]
            raw_excerpt = str(raw.get("excerpt") or "").strip()
            excerpt = raw_excerpt[:MAX_CANDIDATE_EXCERPT_CHARS]
            score_value = raw.get("score")
            if score_value is not None and (
                isinstance(score_value, bool) or not isinstance(score_value, (int, float))
            ):
                raise ValueError("TLR_PUBLIC_LAW_SCORE_INVALID")
            fulltext_chars = raw.get("fulltext_chars")
            if fulltext_chars is not None and (
                isinstance(fulltext_chars, bool)
                or not isinstance(fulltext_chars, int)
                or fulltext_chars < 0
            ):
                raise ValueError("TLR_PUBLIC_LAW_FULLTEXT_LENGTH_INVALID")
            identity = hashlib.sha256(
                "\n".join(
                    value
                    for value in (
                        source_kind,
                        official_identifier,
                        citation,
                        str(raw.get("authority") or "").strip(),
                    )
                    if value
                ).encode()
            ).hexdigest()
            candidate_id = f"tlr_public_law_{identity[:24]}"
            if candidate_id in seen_ids:
                continue
            seen_ids.add(candidate_id)
            candidates.append(
                PublicLawCandidate(
                    candidate_id=candidate_id,
                    provider_id=self.provider_id,
                    material_type=PublicLawMaterialType.ADMINISTRATIVE_INTERPRETATION,
                    source_role=PublicLawSourceRole.INTERPRETIVE_GUIDANCE,
                    title=title,
                    excerpt=excerpt or None,
                    official_identifier=official_identifier,
                    official_url=None,
                    score=float(score_value) if score_value is not None else None,
                    candidate_rank=rank,
                    metadata={
                        "citation": citation,
                        "serial_no": serial_no,
                        "canonical_id": canonical_id,
                        "authority": str(raw.get("authority") or "").strip() or None,
                        "issue_date": str(raw.get("issue_date") or "").strip() or None,
                        "source_kind": returned_kind,
                        "provider_status": str(raw.get("status") or "").strip() or None,
                        "fulltext_total_chars": fulltext_chars,
                        "hit_excerpt_chars": len(raw_excerpt),
                        "hit_excerpt_truncated": bool(
                            fulltext_chars is not None and fulltext_chars > len(raw_excerpt)
                        ),
                        "adapter_excerpt_truncated": len(raw_excerpt) > len(excerpt),
                        "title_truncated": len(raw_title) > len(title),
                        "evidence_eligible": False,
                        "official_verification_required": True,
                    },
                )
            )

        candidate_count = payload.get("candidate_count")
        if candidate_count is None:
            candidate_count = len(payload["results"])
        elif (
            isinstance(candidate_count, bool)
            or not isinstance(candidate_count, int)
            or candidate_count < 0
        ):
            raise ValueError("TLR_PUBLIC_LAW_CANDIDATE_COUNT_INVALID")
        notes = payload.get("notes", [])
        if not isinstance(notes, list) or any(not isinstance(note, str) for note in notes):
            raise ValueError("TLR_PUBLIC_LAW_NOTES_SCHEMA_CHANGED")
        reasons = ["TLR_PUBLIC_LAW_STATUS_REQUIRES_OFFICIAL_VERIFICATION"]
        if rejected_count:
            reasons.append("TLR_PUBLIC_LAW_PROVIDER_REJECTED_CANDIDATES")
        return (
            candidates,
            {
                "provider_candidate_count": candidate_count,
                "provider_rejected_count": rejected_count,
                "provider_note_count": len(notes),
            },
            reasons,
        )

    @staticmethod
    def _normalize_fulltext_page(
        payload: Any,
        *,
        requested_doc_id: str,
        requested_offset: int,
        expected_citation: str | None,
        expected_total: int | None,
    ) -> tuple[str, str, TlrFulltextPage]:
        if not isinstance(payload, dict):
            raise ValueError("TLR_FULLTEXT_SCHEMA_CHANGED")
        response_doc_id = str(payload.get("doc_id") or "").strip()
        citation_text = str(payload.get("citation_text") or "").strip()
        text_excerpt = payload.get("text_excerpt")
        response_offset = payload.get("excerpt_offset")
        fulltext_total_chars = payload.get("fulltext_total_chars")
        fulltext_truncated = payload.get("fulltext_truncated")
        if response_doc_id != requested_doc_id:
            raise ValueError("TLR_FULLTEXT_IDENTITY_MISMATCH")
        if not citation_text or len(citation_text) > 1000:
            raise ValueError("TLR_FULLTEXT_CITATION_INVALID")
        if expected_citation is not None and citation_text != expected_citation:
            raise ValueError("TLR_FULLTEXT_CITATION_CHANGED_BETWEEN_PAGES")
        if not isinstance(text_excerpt, str):
            raise ValueError("TLR_FULLTEXT_TEXT_MISSING")
        if (
            isinstance(response_offset, bool)
            or not isinstance(response_offset, int)
            or response_offset != requested_offset
        ):
            raise ValueError("TLR_FULLTEXT_OFFSET_MISMATCH")
        if (
            isinstance(fulltext_total_chars, bool)
            or not isinstance(fulltext_total_chars, int)
            or fulltext_total_chars < 0
        ):
            raise ValueError("TLR_FULLTEXT_TOTAL_LENGTH_INVALID")
        if expected_total is not None and fulltext_total_chars != expected_total:
            raise ValueError("TLR_FULLTEXT_TOTAL_LENGTH_CHANGED_BETWEEN_PAGES")
        if not isinstance(fulltext_truncated, bool):
            raise ValueError("TLR_FULLTEXT_TRUNCATION_STATE_INVALID")

        header = _FULLTEXT_CITATION_HEADER.match(text_excerpt)
        text = text_excerpt[header.end() :] if header is not None else text_excerpt
        returned_chars = len(text)
        end_offset = response_offset + returned_chars
        if end_offset > fulltext_total_chars:
            raise ValueError("TLR_FULLTEXT_PAGE_EXCEEDS_TOTAL_LENGTH")
        if fulltext_truncated and (
            returned_chars == 0 or end_offset >= fulltext_total_chars
        ):
            raise ValueError("TLR_FULLTEXT_PAGINATION_STALLED")
        if not fulltext_truncated and end_offset != fulltext_total_chars:
            raise ValueError("TLR_FULLTEXT_COMPLETION_LENGTH_MISMATCH")
        next_offset = end_offset if fulltext_truncated else None
        return (
            citation_text,
            text,
            TlrFulltextPage(
                excerpt_offset=response_offset,
                returned_chars=returned_chars,
                fulltext_total_chars=fulltext_total_chars,
                fulltext_truncated=fulltext_truncated,
                next_excerpt_offset=next_offset,
            ),
        )

    def _fulltext_response_error(self, response: TlrHttpResponse) -> ProviderResult | None:
        detail = self._response_detail(response.payload)
        if response.status_code == 400 and "result_token_invalid_or_expired" in detail:
            return ProviderResult(
                status=ProviderResultStatus.ERROR,
                provider_id=self.provider_id,
                error_code=ProviderErrorCode.TLR_RESULT_TOKEN_INVALID_OR_EXPIRED,
                message="TLR_RESULT_TOKEN_INVALID_OR_EXPIRED",
                coverage_complete=False,
            )
        if response.status_code == 404:
            return ProviderResult(
                status=ProviderResultStatus.NOT_FOUND,
                provider_id=self.provider_id,
                error_code=ProviderErrorCode.TLR_DOCUMENT_NOT_FOUND,
                message="TLR_DOCUMENT_NOT_FOUND",
                coverage_complete=False,
            )
        if response.status_code != 200:
            return self._unavailable(f"HTTP_{response.status_code}")
        return None

    def _invalid_fulltext_handle(self) -> ProviderResult:
        return self._invalid_fulltext_window("TLR_FULLTEXT_HANDLE_INVALID")

    def _invalid_fulltext_window(self, message: str) -> ProviderResult:
        return ProviderResult(
            status=ProviderResultStatus.ERROR,
            provider_id=self.provider_id,
            error_code=ProviderErrorCode.INVALID_IDENTIFIER,
            message=message,
            coverage_complete=False,
        )

    def _public_law_result(
        self,
        request: PublicLawSearchRequest,
        *,
        status: PublicLawResultStatus,
        candidates: list[PublicLawCandidate] | None = None,
        truncated: bool = False,
        reason_codes: list[str] | None = None,
        metadata: dict[str, str | int | bool | None] | None = None,
    ) -> PublicLawProviderResult:
        return PublicLawProviderResult(
            provider_id=self.provider_id,
            query_id=request.query_id,
            status=status,
            bounded_scope=request.bounded_scope,
            candidates=candidates or [],
            sources=[],
            server_metadata=None,
            coverage_complete=False,
            truncated=truncated,
            absence_claim_allowed=False,
            reason_codes=reason_codes or [],
            metadata=metadata or {},
        )

    @staticmethod
    def _response_detail(payload: Any) -> str:
        if isinstance(payload, dict):
            detail = payload.get("detail")
            if isinstance(detail, dict):
                return " ".join(str(value) for value in detail.values()).casefold()
            if detail is not None:
                return str(detail).casefold()
        return ""

    @staticmethod
    def _normalize_case_history(payload: Any, requested_doc_id: str) -> TlrCaseHistoryRecord:
        if not isinstance(payload, dict):
            raise ValueError("TLR_FULLTEXT_SCHEMA_CHANGED")
        response_doc_id = str(payload.get("doc_id") or "").strip()
        citation_text = str(payload.get("citation_text") or "").strip()
        if not response_doc_id or not citation_text:
            raise ValueError("TLR_FULLTEXT_IDENTITY_MISSING")
        if response_doc_id != requested_doc_id:
            raise ValueError("TLR_FULLTEXT_IDENTITY_MISMATCH")

        raw_history = payload.get("case_history")
        if raw_history is None:
            return TlrCaseHistoryRecord(
                root_provider_document_id=response_doc_id,
                root_canonical_jid=OfficialJudgmentProvider.normalize_jid(response_doc_id),
                root_citation_text=citation_text,
                history_present=False,
                provider_note="TLR case_history field was not returned.",
            )
        if not isinstance(raw_history, dict):
            raise ValueError("TLR_CASE_HISTORY_SCHEMA_CHANGED")
        if not isinstance(raw_history.get("upper", []), list) or not isinstance(
            raw_history.get("lower", []), list
        ):
            raise ValueError("TLR_CASE_HISTORY_DIRECTION_SCHEMA_CHANGED")

        entries: list[TlrCaseHistoryEntry] = []
        seen: dict[str, str] = {}
        for direction in ("upper", "lower"):
            for raw in raw_history.get(direction, []):
                if not isinstance(raw, dict):
                    raise ValueError("TLR_CASE_HISTORY_ENTRY_INVALID")
                entry_doc_id = str(raw.get("doc_id") or "").strip()
                entry_citation = str(raw.get("citation_text") or "").strip()
                if not entry_doc_id or not entry_citation:
                    raise ValueError("TLR_CASE_HISTORY_ENTRY_IDENTITY_MISSING")
                if entry_doc_id == response_doc_id:
                    raise ValueError("TLR_CASE_HISTORY_SELF_REFERENCE")
                if entry_doc_id in seen:
                    code = (
                        "TLR_CASE_HISTORY_DIRECTION_CONFLICT"
                        if seen[entry_doc_id] != direction
                        else "TLR_CASE_HISTORY_DUPLICATE_ENTRY"
                    )
                    raise ValueError(code)
                seen[entry_doc_id] = direction
                main_flag = str(raw.get("main_flag") or "").strip() or None
                entries.append(
                    TlrCaseHistoryEntry(
                        direction=direction,
                        provider_document_id=entry_doc_id,
                        canonical_jid=OfficialJudgmentProvider.normalize_jid(entry_doc_id),
                        citation_text=entry_citation,
                        doc_type=str(raw.get("doc_type") or "").strip() or None,
                        decision_date=str(raw.get("jdate") or "").strip() or None,
                        main_flag=main_flag,
                        vacated_marker=bool(
                            main_flag
                            and any(marker in main_flag for marker in ("廢棄", "撤銷"))
                        ),
                    )
                )
                if len(entries) > 128:
                    raise ValueError("TLR_CASE_HISTORY_ENTRY_LIMIT_EXCEEDED")
        note = str(raw_history.get("note") or "").strip() or None
        return TlrCaseHistoryRecord(
            root_provider_document_id=response_doc_id,
            root_canonical_jid=OfficialJudgmentProvider.normalize_jid(response_doc_id),
            root_citation_text=citation_text,
            history_present=True,
            entries=entries,
            provider_note=note,
        )

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": f"ALR-TW/{__version__}", "Accept": "application/json"}
        if self._api_key is not None:
            headers["Authorization"] = f"Bearer {self._api_key.get_secret_value()}"
        return headers

    def _unavailable(self, message: str) -> ProviderResult:
        return ProviderResult(
            status=ProviderResultStatus.ERROR,
            provider_id=self.provider_id,
            error_code=ProviderErrorCode.TLR_UNAVAILABLE,
            message=message,
            coverage_complete=False,
        )


class EvidenceSpanHash:
    """Local hash helper avoids constructing an evidence object for candidates."""

    @staticmethod
    def hash_text(text: str) -> str:
        return f"sha256:{hashlib.sha256(text.encode()).hexdigest()}"
