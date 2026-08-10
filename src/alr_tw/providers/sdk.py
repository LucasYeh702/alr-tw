"""Provider SDK skeleton for user-supplied public-law adapters.

The SDK deliberately contains no endpoint, corpus, index, credential, or
production deployment setting.  A deployer supplies a backend and a server
metadata issuer; the wrapper applies bounded, fail-closed normalization around
their response.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from alr_tw.contracts.public_law import (
    PublicLawBoundedResult,
    PublicLawCandidate,
    PublicLawMaterialType,
    PublicLawProviderCapabilities,
    PublicLawProviderResult,
    PublicLawResultStatus,
    PublicLawSearchRequest,
    PublicLawServerMetadata,
    PublicLawSourceRecord,
)
from alr_tw.contracts.sources import TrustStatus


class PublicLawBackendStatus(str, Enum):
    """Backend status before the server-owned adapter envelope is applied."""

    FOUND = "found"
    NOT_FOUND = "not_found"
    PARTIAL = "partial"
    ERROR = "error"


class PublicLawBackendResult(BaseModel):
    """Untrusted backend response accepted only through the adapter boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_id: str = Field(min_length=1, max_length=128)
    query_id: str = Field(min_length=1, max_length=128)
    status: str
    candidates: list[PublicLawCandidate] = Field(default_factory=list, max_length=50)
    sources: list[PublicLawSourceRecord] = Field(default_factory=list, max_length=50)
    coverage_complete: bool = False
    truncated: bool = False
    reason_codes: list[str] = Field(default_factory=list, max_length=32)
    metadata: dict[str, str | int | bool | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_backend(self) -> PublicLawBackendResult:
        if self.status not in {
            PublicLawBackendStatus.FOUND,
            PublicLawBackendStatus.NOT_FOUND,
            PublicLawBackendStatus.PARTIAL,
            PublicLawBackendStatus.ERROR,
        }:
            raise ValueError("PUBLIC_LAW_BACKEND_STATUS_UNSUPPORTED")
        if len({item.candidate_id for item in self.candidates}) != len(self.candidates):
            raise ValueError("PUBLIC_LAW_BACKEND_CANDIDATE_DUPLICATE")
        if self.truncated and self.coverage_complete:
            raise ValueError("PUBLIC_LAW_BACKEND_TRUNCATION_CONFLICT")
        return self


@runtime_checkable
class PublicLawBackend(Protocol):
    """Minimal provider port implemented by a deployer's data connector."""

    def search(self, request: PublicLawSearchRequest) -> PublicLawBackendResult: ...


PublicLawMetadataIssuer = Callable[
    [str, PublicLawSearchRequest],
    PublicLawServerMetadata,
]
PublicLawSourcePromoter = Callable[
    [PublicLawSourceRecord, PublicLawSearchRequest, PublicLawServerMetadata],
    PublicLawSourceRecord | None,
]


@runtime_checkable
class PublicLawProviderAdapter(Protocol):
    """Adapter interface exposed to the ALR research runtime."""

    @property
    def provider_id(self) -> str: ...

    def capabilities(self) -> PublicLawProviderCapabilities: ...

    def search(self, request: PublicLawSearchRequest) -> PublicLawBoundedResult: ...


class GenericPublicLawProviderAdapter:
    """Bounded adapter template for administrative/legislative providers.

    The backend is never allowed to mint server metadata.  The metadata issuer
    is injected by the deployer-owned server gate; without it every result is
    blocked and no scoped absence claim can be emitted.  Backend records that
    do not pass the explicit source-promotion gate and bind to the newly issued
    metadata are dropped from the promoted source list and the result is
    downgraded to ``partial``.
    """

    def __init__(
        self,
        *,
        provider_id: str,
        backend: PublicLawBackend,
        material_types: tuple[PublicLawMaterialType, ...],
        metadata_issuer: PublicLawMetadataIssuer | None = None,
        source_promoter: PublicLawSourcePromoter | None = None,
        max_results: int = 50,
        exact_lookup: bool = False,
        historical_versions: bool = False,
        server_verification: bool = False,
    ) -> None:
        self._provider_id = provider_id
        self._backend = backend
        self._material_types = tuple(dict.fromkeys(material_types))
        self._metadata_issuer = metadata_issuer
        self._source_promoter = source_promoter
        self._max_results = max(1, min(max_results, 50))
        self._exact_lookup = exact_lookup
        self._historical_versions = historical_versions
        self._server_verification = server_verification

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def capabilities(self) -> PublicLawProviderCapabilities:
        return PublicLawProviderCapabilities(
            provider_id=self._provider_id,
            material_types=list(self._material_types),
            exact_lookup=self._exact_lookup,
            historical_versions=self._historical_versions,
            server_verification=self._server_verification,
            max_results=self._max_results,
        )

    def search(self, request: PublicLawSearchRequest) -> PublicLawBoundedResult:
        if request.query_id == "":  # defensive branch for non-Pydantic callers
            return self._blocked(request, "PUBLIC_LAW_QUERY_ID_MISSING")
        unsupported = set(request.material_types) - set(self._material_types)
        if unsupported:
            return self._blocked(request, "PUBLIC_LAW_MATERIAL_TYPE_UNSUPPORTED")
        metadata = self._issue_metadata(request)
        if metadata is None:
            return self._blocked(request, "PUBLIC_LAW_SERVER_METADATA_ISSUER_REQUIRED")
        if metadata.provider_id != self._provider_id:
            return self._blocked(request, "PUBLIC_LAW_SERVER_METADATA_PROVIDER_MISMATCH")
        try:
            raw = self._backend.search(request)
            backend = (
                raw
                if isinstance(raw, PublicLawBackendResult)
                else PublicLawBackendResult.model_validate(raw)
            )
        except (Exception, ValidationError) as exc:
            # The backend is an external boundary.  Preserve a retry signal,
            # never reinterpret an exception as a clean scoped miss.
            return PublicLawProviderResult(
                provider_id=self._provider_id,
                query_id=request.query_id,
                status=PublicLawResultStatus.RETRY_REQUIRED,
                bounded_scope=request.bounded_scope,
                server_metadata=metadata,
                reason_codes=[f"PUBLIC_LAW_PROVIDER_ERROR:{type(exc).__name__}"],
            )
        if backend.provider_id != self._provider_id:
            return self._blocked(request, "PUBLIC_LAW_BACKEND_PROVIDER_MISMATCH", metadata)
        if backend.query_id != request.query_id:
            return self._blocked(request, "PUBLIC_LAW_BACKEND_QUERY_MISMATCH", metadata)

        limit = min(request.max_results, self._max_results)
        candidates = backend.candidates[:limit]
        local_reasons = list(backend.reason_codes)
        truncated = backend.truncated or len(backend.candidates) > limit
        if len(backend.candidates) > limit:
            local_reasons.append("PUBLIC_LAW_RESULT_LIMIT_TRUNCATED")
        if any(candidate.provider_id != self._provider_id for candidate in candidates):
            return self._blocked(request, "PUBLIC_LAW_CANDIDATE_PROVIDER_MISMATCH", metadata)

        sources: list[PublicLawSourceRecord] = []
        source_binding_failed = False
        promoter = self._source_promoter
        if backend.sources and promoter is None:
            # Matching metadata is only a locator; it is not proof that the
            # backend source was fetched and promoted by this server.
            source_binding_failed = True
            local_reasons.append("PUBLIC_LAW_SOURCE_PROMOTION_REQUIRES_SERVER_GATE")
        elif backend.sources:
            assert promoter is not None
            for source in backend.sources:
                if source.provider_id != self._provider_id:
                    source_binding_failed = True
                    local_reasons.append("PUBLIC_LAW_SOURCE_PROVIDER_MISMATCH")
                    continue
                if source.server_metadata != metadata:
                    source_binding_failed = True
                    local_reasons.append("PUBLIC_LAW_SOURCE_METADATA_MISMATCH")
                    continue
                try:
                    promoted_raw = promoter(source, request, metadata)
                    promoted = (
                        promoted_raw
                        if isinstance(promoted_raw, PublicLawSourceRecord)
                        else PublicLawSourceRecord.model_validate(promoted_raw)
                        if promoted_raw is not None
                        else None
                    )
                except Exception as exc:
                    promoted = None
                    local_reasons.append(
                        f"PUBLIC_LAW_SOURCE_PROMOTION_ERROR:{type(exc).__name__}"
                    )
                if promoted is None:
                    source_binding_failed = True
                    local_reasons.append("PUBLIC_LAW_SOURCE_PROMOTION_REJECTED")
                    continue
                if not self._source_binding_matches(source, promoted, metadata):
                    source_binding_failed = True
                    local_reasons.append("PUBLIC_LAW_SOURCE_PROMOTION_BINDING_MISMATCH")
                    continue
                sources.append(promoted)
            if len(sources) != len(backend.sources):
                source_binding_failed = True

        status = PublicLawResultStatus.PARTIAL
        coverage_complete = False
        absence_claim_allowed = False
        if backend.status == PublicLawBackendStatus.ERROR:
            status = PublicLawResultStatus.RETRY_REQUIRED
            local_reasons.append("PUBLIC_LAW_PROVIDER_ERROR")
        elif backend.status == PublicLawBackendStatus.NOT_FOUND:
            if (
                backend.coverage_complete
                and not truncated
                and not candidates
                and not sources
                and not local_reasons
            ):
                status = PublicLawResultStatus.NOT_FOUND_IN_SCOPE
                coverage_complete = True
                absence_claim_allowed = True
            else:
                local_reasons.append("PUBLIC_LAW_SCOPE_NOT_COMPLETE")
        elif backend.status == PublicLawBackendStatus.FOUND:
            coverage_complete = (
                backend.coverage_complete and not truncated and not source_binding_failed
            )
            status = PublicLawResultStatus.FOUND if coverage_complete else PublicLawResultStatus.PARTIAL
        elif backend.status == PublicLawBackendStatus.PARTIAL:
            local_reasons.append("PUBLIC_LAW_COVERAGE_PARTIAL")
        if truncated:
            status = PublicLawResultStatus.PARTIAL
            coverage_complete = False
            absence_claim_allowed = False
            local_reasons.append("PUBLIC_LAW_RESULT_TRUNCATED")

        return PublicLawProviderResult(
            provider_id=self._provider_id,
            query_id=request.query_id,
            status=status,
            bounded_scope=request.bounded_scope,
            candidates=candidates,
            sources=sources,
            server_metadata=metadata,
            coverage_complete=coverage_complete,
            truncated=truncated,
            absence_claim_allowed=absence_claim_allowed,
            reason_codes=list(dict.fromkeys(local_reasons)),
            metadata=backend.metadata,
        )

    def _source_binding_matches(
        self,
        original: PublicLawSourceRecord,
        promoted: PublicLawSourceRecord,
        metadata: PublicLawServerMetadata,
    ) -> bool:
        """Require source identity, content hashes, provider, and receipt to persist."""

        return (
            promoted.provider_id == self._provider_id
            and promoted.server_metadata == metadata
            and promoted.trust_status
            in {TrustStatus.OFFICIAL_VERIFIED, TrustStatus.EVIDENCE_ELIGIBLE}
            and promoted.source_id == original.source_id
            and promoted.source_key == original.source_key
            and promoted.source_version_id == original.source_version_id
            and promoted.content_hash == original.content_hash
            and promoted.normalized_content_hash == original.normalized_content_hash
            and promoted.official_identifier == original.official_identifier
            and promoted.official_url == original.official_url
        )

    def _issue_metadata(self, request: PublicLawSearchRequest) -> PublicLawServerMetadata | None:
        if self._metadata_issuer is None:
            return None
        try:
            metadata = self._metadata_issuer(self._provider_id, request)
            return (
                metadata
                if isinstance(metadata, PublicLawServerMetadata)
                else PublicLawServerMetadata.model_validate(metadata)
            )
        except Exception:
            return None

    def _blocked(
        self,
        request: PublicLawSearchRequest,
        reason: str,
        metadata: PublicLawServerMetadata | None = None,
    ) -> PublicLawProviderResult:
        return PublicLawProviderResult(
            provider_id=self._provider_id,
            query_id=request.query_id,
            status=PublicLawResultStatus.BLOCKED,
            bounded_scope=request.bounded_scope,
            server_metadata=metadata,
            reason_codes=[reason],
        )


# Names used in integration examples; all point at the same bounded template.
BoundedPublicLawProviderAdapter = GenericPublicLawProviderAdapter
PublicLawAdapter = GenericPublicLawProviderAdapter


__all__ = [
    "BoundedPublicLawProviderAdapter",
    "GenericPublicLawProviderAdapter",
    "PublicLawAdapter",
    "PublicLawBackend",
    "PublicLawBackendResult",
    "PublicLawBackendStatus",
    "PublicLawMetadataIssuer",
    "PublicLawProviderAdapter",
    "PublicLawSourcePromoter",
]
