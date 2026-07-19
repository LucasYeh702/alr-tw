"""Clean-room TLR HTTP adapter based only on its public OpenAPI contract."""

from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping, Protocol
from urllib.parse import urlsplit

from pydantic import SecretStr

from alr_tw.contracts.providers import (
    ProviderCandidate,
    ProviderCapabilities,
    ProviderErrorCode,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderResult,
    ProviderResultStatus,
)
from alr_tw.contracts.sources import (
    MaterialType,
    SourceRecord,
    SourceTier,
    TrustStatus,
)

from .privacy import PrivacyScreenResult, screen_external_query

MAX_RESPONSE_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class TlrHttpResponse:
    status_code: int
    payload: Any


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
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
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
            candidates, sources = self._normalize_response(response.payload, now or datetime.now(UTC))
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

    def _normalize_response(
        self,
        payload: Any,
        timestamp: datetime,
    ) -> tuple[list[ProviderCandidate], list[SourceRecord]]:
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise ValueError("TLR_SEARCH_SCHEMA_CHANGED")
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
                excerpt=snippet or None,
                score=None,
                metadata={
                    "rank": int(raw.get("rank") or rank),
                    "doc_id": doc_id,
                    "court_name": raw.get("court_name"),
                    "decision_date": raw.get("jdate"),
                    "case_category": raw.get("case_category"),
                    "result_token": result_token,
                },
            )
            normalized_text = snippet or f"TLR candidate: {citation}"
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
                ],
            )
            candidates.append(candidate)
            sources.append(source)
        return candidates, sources

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": "ALR-TW/0.6", "Accept": "application/json"}
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
