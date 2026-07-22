"""Provider capability and data-mode contracts."""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class DataMode(str, Enum):
    SYNTHETIC = "synthetic"
    OFFICIAL_ONLY = "official_only"
    HYBRID_VERIFIED = "hybrid_verified"


class ProviderCapabilities(BaseModel):
    """Machine-readable limits for a source provider.

    Callers must use these flags to report incomplete coverage instead of
    inferring that an unsupported operation returned no legal material.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    exact_lookup: bool
    keyword_search: bool
    semantic_recall: bool
    official_verification: bool
    historical_versions: bool
    current_status_check: bool
    external_query_transfer: bool


class ProviderHealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class ProviderHealth(BaseModel):
    """Health result that does not conflate unavailability with no results."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_id: str = Field(min_length=1)
    status: ProviderHealthStatus
    error_code: str | None = None
    message: str = ""


class ProviderResultStatus(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    PARTIAL = "partial"
    ERROR = "error"


class ProviderErrorCode(str, Enum):
    INVALID_IDENTIFIER = "INVALID_IDENTIFIER"
    AMBIGUOUS_FORMAL_CITATION = "AMBIGUOUS_FORMAL_CITATION"
    TLR_UNAVAILABLE = "TLR_UNAVAILABLE"
    OFFICIAL_SOURCE_NOT_FOUND = "OFFICIAL_SOURCE_NOT_FOUND"
    OFFICIAL_NOT_FOUND = "OFFICIAL_NOT_FOUND"
    OFFICIAL_SOURCE_UNAVAILABLE = "OFFICIAL_SOURCE_UNAVAILABLE"
    OFFICIAL_SOURCE_BLOCKED = "OFFICIAL_SOURCE_BLOCKED"
    OFFICIAL_SESSION_REQUIRED = "OFFICIAL_SESSION_REQUIRED"
    OFFICIAL_PARSE_FAILED = "OFFICIAL_PARSE_FAILED"
    OFFICIAL_PARSE_ERROR = "OFFICIAL_PARSE_ERROR"
    OFFICIAL_SCHEMA_CHANGED = "OFFICIAL_SCHEMA_CHANGED"
    OFFICIAL_CONTENT_CONFLICT = "OFFICIAL_CONTENT_CONFLICT"
    OFFICIAL_IDENTIFIER_MISMATCH = "OFFICIAL_IDENTIFIER_MISMATCH"
    EXTERNAL_PROVIDER_UNAVAILABLE = "EXTERNAL_PROVIDER_UNAVAILABLE"
    EXTERNAL_PROVIDER_SCHEMA_CHANGED = "EXTERNAL_PROVIDER_SCHEMA_CHANGED"
    PRIVACY_EXTERNAL_QUERY_BLOCKED = "PRIVACY_EXTERNAL_QUERY_BLOCKED"
    SOURCE_STALE = "SOURCE_STALE"
    SOURCE_REVALIDATION_FAILED = "SOURCE_REVALIDATION_FAILED"
    SOURCE_NOT_EVIDENCE_ELIGIBLE = "SOURCE_NOT_EVIDENCE_ELIGIBLE"
    JUDGMENT_CONTENT_MISSING = "JUDGMENT_CONTENT_MISSING"
    JUDGMENT_TEXT_EMPTY = "JUDGMENT_TEXT_EMPTY"
    CANDIDATE_OFFICIAL_ID_MISMATCH = "CANDIDATE_OFFICIAL_ID_MISMATCH"


class CandidateIdentity(BaseModel):
    """Typed identity hints carried by an untrusted retrieval candidate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    canonical_jid: str | None = None
    provider_document_id: str | None = None
    formal_citation: str | None = None
    official_url: str | None = None


class ProviderCandidate(BaseModel):
    """Untrusted retrieval candidate; never sufficient for final support."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    title: str | None = None
    official_identifier: str | None = None
    official_url: str | None = None
    excerpt: str | None = None
    score: float | None = None
    identity: CandidateIdentity | None = None
    candidate_rank: int | None = Field(default=None, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderResult(BaseModel):
    """Provider-neutral result which keeps failure distinct from no match."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ProviderResultStatus
    provider_id: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    candidates: list[ProviderCandidate] = Field(default_factory=list)
    error_code: ProviderErrorCode | None = None
    message: str = ""
    coverage_complete: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class LegalSourceProvider(Protocol):
    """Common provider surface; material-specific operations use narrower ports."""

    @property
    def provider_id(self) -> str: ...

    def capabilities(self) -> ProviderCapabilities: ...

    async def health_check(self) -> ProviderHealth: ...


class BrowserSessionProvider(Protocol):
    """Optional user-provided session port; no browser implementation is bundled."""

    async def acquire_session(self, origin: str) -> Any: ...
