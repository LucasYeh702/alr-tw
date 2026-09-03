"""Provider-neutral contracts for Taiwan public-law materials.

This module describes the shape and provenance of administrative and
legislative material without shipping a corpus or deciding the legal effect
of any record.  A provider may return retrieval candidates, but only records
with a server-owned metadata binding can be used as verified source material.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from collections.abc import Collection
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .sources import SourceTier, TrustStatus


_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
_DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"
_OPAQUE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"


class PublicLawMaterialType(str, Enum):
    """Material families covered by the current v0.11.0 public-law contract."""

    ADMINISTRATIVE_RULE = "administrative_rule"
    ADMINISTRATIVE_REGULATION = "administrative_rule"
    ADMINISTRATIVE_INTERPRETATION = "administrative_interpretation"
    ADMINISTRATIVE_APPEAL = "administrative_appeal"
    PETITION_APPEAL = "administrative_appeal"
    HISTORICAL_STATUTE = "historical_statute"
    LAW_VERSION = "historical_statute"
    LEGISLATIVE_MATERIAL = "legislative_material"


class PublicLawSourceRole(str, Enum):
    """Role of a public-law record; this is not a legal conclusion."""

    NORMATIVE_RULE = "normative_rule"
    INTERPRETIVE_GUIDANCE = "interpretive_guidance"
    ADMINISTRATIVE_INTERPRETATION = "interpretive_guidance"
    APPEAL_DECISION = "appeal_decision"
    ADMINISTRATIVE_APPEAL_DECISION = "appeal_decision"
    LEGISLATIVE_HISTORY = "legislative_history"
    LEGISLATIVE_MATERIAL = "legislative_history"
    PROCEDURAL_RECORD = "procedural_record"
    RELATED_MATERIAL = "related_material"
    UNKNOWN = "unknown"


class PublicLawLineageRelation(str, Enum):
    """Provider-reported relationship between two source records."""

    IMPLEMENTS = "implements"
    INTERPRETS = "interprets"
    AMENDS = "amends"
    REPEALS = "repeals"
    APPLIES = "applies"
    APPEALED_BY = "appealed_by"
    REVIEWED_BY = "reviewed_by"
    DERIVED_FROM = "derived_from"
    CITES = "cites"
    RELATED = "related"
    UNKNOWN = "unknown"


class PublicLawRemedyStage(str, Enum):
    """A procedural or remedial stage attached to a source record."""

    INITIAL_ADMINISTRATIVE_ACTION = "initial_administrative_action"
    ADMINISTRATIVE_APPEAL = "administrative_appeal"
    ADMINISTRATIVE_RECONSIDERATION = "administrative_reconsideration"
    ADMINISTRATIVE_LITIGATION = "administrative_litigation"
    JUDICIAL_APPEAL = "judicial_appeal"
    CONSTITUTIONAL_REVIEW = "constitutional_review"
    LEGISLATIVE_PROCESS = "legislative_process"
    ENFORCEMENT = "enforcement"
    UNKNOWN = "unknown"


class PublicLawProcedureKind(str, Enum):
    """A procedure-related locator, not an assessed legal outcome."""

    JURISDICTION = "jurisdiction"
    AUTHORITY_BASIS = "authority_basis"
    NOTICE = "notice"
    HEARING = "hearing"
    REASON_GIVING = "reason_giving"
    RECORD_ACCESS = "record_access"
    DEADLINE = "deadline"
    SERVICE = "service"
    FILING = "filing"
    PRIOR_REMEDY = "prior_remedy"
    REVIEW_SCOPE = "review_scope"
    FORM = "form"
    OTHER = "other"


class PublicLawResultStatus(str, Enum):
    """Bounded provider outcome; no status means that a legal proposition is true."""

    FOUND = "found"
    NOT_FOUND_IN_SCOPE = "not_found_in_scope"
    PARTIAL = "partial"
    RETRY_REQUIRED = "retry_required"
    BLOCKED = "blocked"


class PublicLawProviderCapabilities(BaseModel):
    """Negotiated limits; capabilities do not attest to legal correctness."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.public-law-provider-capabilities/v1"] = (
        "alr-tw.public-law-provider-capabilities/v1"
    )
    provider_id: str = Field(pattern=_OPAQUE_PATTERN)
    material_types: list[PublicLawMaterialType] = Field(min_length=1, max_length=5)
    keyword_search: bool = True
    semantic_recall: bool = False
    exact_lookup: bool = False
    historical_versions: bool = False
    server_verification: bool = False
    external_query_transfer: bool = False
    max_results: int = Field(default=50, ge=1, le=50)

    @model_validator(mode="after")
    def validate_material_types(self) -> PublicLawProviderCapabilities:
        if len(self.material_types) != len(set(self.material_types)):
            raise ValueError("public-law provider material_types must be unique")
        return self


class PublicLawValidationDecision(str, Enum):
    ACCEPTED = "accepted"
    QUALIFIED = "qualified"
    BLOCKED = "blocked"


class PublicLawServerMetadata(BaseModel):
    """Opaque metadata issued by the ALR server for one provider snapshot.

    ``server_owned`` and ``issuer`` describe an invariant, but a caller cannot
    make a record trusted merely by setting those fields.  Runtime gates must
    bind this object to the server-owned metadata for the same research run;
    :func:`validate_public_law_result` performs that explicit comparison.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.public-law-server-metadata/v1"] = (
        "alr-tw.public-law-server-metadata/v1"
    )
    provider_id: str = Field(pattern=_OPAQUE_PATTERN)
    snapshot_id: str = Field(pattern=_OPAQUE_PATTERN)
    generation: str = Field(pattern=_OPAQUE_PATTERN)
    receipt_id: str = Field(pattern=_OPAQUE_PATTERN)
    issued_at: datetime
    expires_at: datetime | None = None
    content_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    issuer: Literal["alr-tw.server"] = "alr-tw.server"
    server_owned: Literal[True] = True

    @model_validator(mode="after")
    def validate_metadata(self) -> PublicLawServerMetadata:
        for value in (self.issued_at, self.expires_at):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("public-law server metadata timestamps must be timezone-aware")
        if self.expires_at is not None and self.expires_at <= self.issued_at:
            raise ValueError("public-law metadata expires_at must follow issued_at")
        lowered = " ".join(
            value.casefold()
            for value in (self.provider_id, self.snapshot_id, self.generation, self.receipt_id)
        )
        if any(marker in lowered for marker in ("sqlite", "chroma", "manifest", "catalog", "token")):
            raise ValueError("public-law server metadata identifiers must remain opaque")
        return self

    def is_current(self, *, now: datetime) -> bool:
        """Return whether this metadata can be used at a server decision point."""

        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        if self.issued_at > now:
            return False
        return self.expires_at is None or self.expires_at > now


class PublicLawLineage(BaseModel):
    """A source-to-source edge whose IDs can be checked by the server."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lineage_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    relation: PublicLawLineageRelation
    parent_source_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    child_source_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    evidence_ids: list[str] = Field(default_factory=list, max_length=32)
    citation: str | None = Field(default=None, max_length=500)
    server_owned: Literal[True] = True

    @model_validator(mode="after")
    def validate_edge(self) -> PublicLawLineage:
        if self.parent_source_id == self.child_source_id:
            raise ValueError("public-law lineage cannot point a source to itself")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("public-law lineage evidence_ids must be unique")
        return self


class PublicLawProcedureRequirement(BaseModel):
    """A procedure locator, deliberately without met/not-met semantics."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requirement_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    kind: PublicLawProcedureKind
    description: str = Field(min_length=1, max_length=2000)
    source_ids: list[str] = Field(default_factory=list, max_length=32)
    evidence_ids: list[str] = Field(default_factory=list, max_length=64)
    remedy_stage: PublicLawRemedyStage | None = None
    deadline: date | None = None

    @model_validator(mode="after")
    def validate_references(self) -> PublicLawProcedureRequirement:
        for name in ("source_ids", "evidence_ids"):
            values = getattr(self, name)
            if len(values) != len(set(values)):
                raise ValueError(f"public-law {name} must be unique")
        return self


class PublicLawSourceRecord(BaseModel):
    """A provider-neutral public-law source snapshot.

    A record may describe a candidate or a verified source according to its
    trust status.  It never asserts that an interpretation is legally correct;
    lineage and procedure fields are bounded provenance only.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.public-law-source/v1"] = "alr-tw.public-law-source/v1"
    source_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    source_key: str = Field(min_length=1, max_length=300)
    source_version_id: str = Field(min_length=1, max_length=300)
    material_type: PublicLawMaterialType
    source_role: PublicLawSourceRole
    provider_id: str = Field(pattern=_OPAQUE_PATTERN)
    source_tier: SourceTier
    trust_status: TrustStatus
    official_identifier: str | None = Field(default=None, max_length=500)
    official_url: str | None = Field(default=None, max_length=2000)
    citation: str = Field(min_length=1, max_length=1000)
    title: str | None = Field(default=None, max_length=500)
    issued_at: datetime | None = None
    effective_from: date | None = None
    effective_until: date | None = None
    fetched_at: datetime
    verified_at: datetime | None = None
    expires_at: datetime
    content_hash: str = Field(pattern=_DIGEST_PATTERN)
    normalized_content_hash: str = Field(pattern=_DIGEST_PATTERN)
    normalized_text: str = Field(min_length=1)
    server_metadata: PublicLawServerMetadata
    lineage: list[PublicLawLineage] = Field(default_factory=list, max_length=64)
    procedural_requirements: list[PublicLawProcedureRequirement] = Field(
        default_factory=list,
        max_length=64,
    )
    remedy_stages: list[PublicLawRemedyStage] = Field(default_factory=list, max_length=16)
    metadata: dict[str, str | int | bool | None] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_source(self) -> PublicLawSourceRecord:
        timestamps = [self.fetched_at, self.expires_at]
        if self.verified_at is not None:
            timestamps.append(self.verified_at)
        if any(value.tzinfo is None or value.utcoffset() is None for value in timestamps):
            if self.fetched_at.tzinfo is None or self.fetched_at.utcoffset() is None:
                raise ValueError("public-law source fetched_at must be timezone-aware")
            if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
                raise ValueError("public-law source expires_at must be timezone-aware")
            if self.verified_at is not None and (
                self.verified_at.tzinfo is None or self.verified_at.utcoffset() is None
            ):
                raise ValueError("public-law source verified_at must be timezone-aware")
        if self.expires_at <= self.fetched_at:
            raise ValueError("public-law source expires_at must follow fetched_at")
        if (
            self.effective_from is not None
            and self.effective_until is not None
            and self.effective_until < self.effective_from
        ):
            raise ValueError("public-law source effective_until must follow effective_from")
        if self.trust_status in {
            TrustStatus.OFFICIAL_VERIFIED,
            TrustStatus.EVIDENCE_ELIGIBLE,
        }:
            if self.verified_at is None or not (self.official_identifier or self.official_url):
                raise ValueError("verified public-law sources require verified identity")
        if self.official_url is not None and not self.official_url.startswith("https://"):
            raise ValueError("public-law official_url must use https")
        if self.source_tier is SourceTier.EXTERNAL_SEMANTIC_RECALL and self.trust_status not in {
            TrustStatus.EXTERNAL_CANDIDATE,
            TrustStatus.STALE,
            TrustStatus.VERIFICATION_FAILED,
        }:
            raise ValueError("external public-law recall cannot be evidence eligible")
        expected_roles = {
            PublicLawMaterialType.ADMINISTRATIVE_RULE: PublicLawSourceRole.NORMATIVE_RULE,
            PublicLawMaterialType.ADMINISTRATIVE_INTERPRETATION: (
                PublicLawSourceRole.INTERPRETIVE_GUIDANCE
            ),
            PublicLawMaterialType.ADMINISTRATIVE_APPEAL: PublicLawSourceRole.APPEAL_DECISION,
            PublicLawMaterialType.HISTORICAL_STATUTE: PublicLawSourceRole.NORMATIVE_RULE,
            PublicLawMaterialType.LEGISLATIVE_MATERIAL: PublicLawSourceRole.LEGISLATIVE_HISTORY,
        }
        expected_role = expected_roles[self.material_type]
        if self.source_role not in {
            expected_role,
            PublicLawSourceRole.PROCEDURAL_RECORD,
            PublicLawSourceRole.RELATED_MATERIAL,
            PublicLawSourceRole.UNKNOWN,
        }:
            raise ValueError("public-law source role does not match material type")
        if len(self.lineage) != len({item.lineage_id for item in self.lineage}):
            raise ValueError("public-law lineage_id values must be unique")
        if len(self.procedural_requirements) != len(
            {item.requirement_id for item in self.procedural_requirements}
        ):
            raise ValueError("public-law requirement_id values must be unique")
        if len(self.remedy_stages) != len(set(self.remedy_stages)):
            raise ValueError("public-law remedy_stages must be unique")
        if self.server_metadata.provider_id != self.provider_id:
            raise ValueError("public-law source metadata provider mismatch")
        return self


class PublicLawCandidate(BaseModel):
    """Untrusted provider hit; it has no source or evidence identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    provider_id: str = Field(pattern=_OPAQUE_PATTERN)
    material_type: PublicLawMaterialType
    source_role: PublicLawSourceRole = PublicLawSourceRole.UNKNOWN
    title: str | None = Field(default=None, max_length=500)
    excerpt: str | None = Field(default=None, max_length=4000)
    official_identifier: str | None = Field(default=None, max_length=500)
    official_url: str | None = Field(default=None, max_length=2000)
    score: float | None = None
    candidate_rank: int | None = Field(default=None, ge=1)
    metadata: dict[str, str | int | bool | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_candidate(self) -> PublicLawCandidate:
        if self.official_url is not None and not self.official_url.startswith("https://"):
            raise ValueError("public-law candidate official_url must use https")
        return self


class PublicLawSearchRequest(BaseModel):
    """Bounded, serializable request sent through a public-law adapter."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.public-law-search-request/v1"] = (
        "alr-tw.public-law-search-request/v1"
    )
    query_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    query: str = Field(min_length=1, max_length=2000)
    material_types: list[PublicLawMaterialType] = Field(min_length=1, max_length=5)
    remedy_stages: list[PublicLawRemedyStage] = Field(default_factory=list, max_length=8)
    bounded_scope: str = Field(min_length=1, max_length=500)
    max_results: int = Field(default=10, ge=1, le=50)
    as_of_date: date | None = None

    @model_validator(mode="after")
    def validate_scope_lists(self) -> PublicLawSearchRequest:
        if len(self.material_types) != len(set(self.material_types)):
            raise ValueError("public-law material_types must be unique")
        if len(self.remedy_stages) != len(set(self.remedy_stages)):
            raise ValueError("public-law remedy_stages must be unique")
        if not self.bounded_scope.strip():
            raise ValueError("public-law bounded_scope must not be blank")
        if not self.query.strip():
            raise ValueError("public-law query must not be blank")
        return self


class PublicLawProviderResult(BaseModel):
    """Server-bound result for one bounded provider request.

    ``candidates`` remain retrieval-only.  ``sources`` may be promoted only
    when their server metadata exactly matches the result metadata and their
    trust status passes the source contract.  A scoped miss is intentionally
    narrower than a claim that no contrary material exists globally.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.public-law-provider-result/v1"] = (
        "alr-tw.public-law-provider-result/v1"
    )
    provider_id: str = Field(pattern=_OPAQUE_PATTERN)
    query_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    status: PublicLawResultStatus
    bounded_scope: str = Field(min_length=1, max_length=500)
    candidates: list[PublicLawCandidate] = Field(default_factory=list, max_length=50)
    sources: list[PublicLawSourceRecord] = Field(default_factory=list, max_length=50)
    server_metadata: PublicLawServerMetadata | None = None
    coverage_complete: bool = False
    truncated: bool = False
    absence_claim_allowed: bool = False
    reason_codes: list[str] = Field(default_factory=list, max_length=32)
    metadata: dict[str, str | int | bool | None] = Field(default_factory=dict)
    semantic_conclusion_performed: Literal[False] = False

    @model_validator(mode="after")
    def validate_result(self) -> PublicLawProviderResult:
        if len({item.candidate_id for item in self.candidates}) != len(self.candidates):
            raise ValueError("public-law candidate_id values must be unique")
        if any(item.provider_id != self.provider_id for item in self.candidates):
            raise ValueError("public-law candidate provider mismatch")
        source_ids = [item.source_id for item in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("public-law source_id values must be unique")
        if any(item.provider_id != self.provider_id for item in self.sources):
            raise ValueError("public-law source provider mismatch")
        if self.truncated and self.coverage_complete:
            raise ValueError("truncated public-law results cannot be complete")
        if self.truncated and self.status is not PublicLawResultStatus.PARTIAL:
            raise ValueError("truncated public-law results must be partial")
        if self.absence_claim_allowed:
            if self.status is not PublicLawResultStatus.NOT_FOUND_IN_SCOPE:
                raise ValueError("absence claim requires a scoped not-found result")
            if not self.coverage_complete or self.truncated or self.candidates or self.sources:
                raise ValueError("absence claim requires a clean empty bounded result")
            if self.server_metadata is None:
                raise ValueError("absence claim requires server-owned metadata")
        if self.status is PublicLawResultStatus.NOT_FOUND_IN_SCOPE and (
            self.candidates or self.sources or not self.coverage_complete
        ):
            raise ValueError("scoped not-found must be a complete empty result")
        if self.status is PublicLawResultStatus.FOUND and not (self.candidates or self.sources):
            raise ValueError("found public-law result requires candidates or sources")
        if self.status in {
            PublicLawResultStatus.PARTIAL,
            PublicLawResultStatus.RETRY_REQUIRED,
            PublicLawResultStatus.BLOCKED,
        } and self.coverage_complete:
            raise ValueError("incomplete public-law statuses cannot claim complete coverage")
        if self.sources:
            if self.server_metadata is None:
                raise ValueError("public-law sources require server-owned metadata")
            if any(item.server_metadata != self.server_metadata for item in self.sources):
                raise ValueError("public-law source metadata must bind to result metadata")
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("public-law reason_codes must be unique")
        if self.status is PublicLawResultStatus.NOT_FOUND_IN_SCOPE and not self.server_metadata:
            raise ValueError("scoped not-found requires server-owned metadata")
        return self


class PublicLawValidationResult(BaseModel):
    """Structural/trust decision; it performs no semantic legal analysis."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.public-law-validation/v1"] = (
        "alr-tw.public-law-validation/v1"
    )
    provider_id: str
    query_id: str
    decision: PublicLawValidationDecision
    eligible_source_ids: list[str] = Field(default_factory=list, max_length=50)
    candidate_only: Literal[True] = True
    semantic_conclusion_performed: Literal[False] = False
    absence_claim_allowed: Literal[False] | bool = False
    reason_codes: list[str] = Field(default_factory=list, max_length=32)


def validate_public_law_result(
    result: PublicLawProviderResult | Mapping[str, Any],
    *,
    server_metadata: PublicLawServerMetadata | None,
    server_source_ids: Collection[str] | None = None,
    now: datetime | None = None,
) -> PublicLawValidationResult:
    """Apply fail-closed server binding checks to an adapter result.

    The caller-supplied result is never authoritative by itself.  A server
    gate must pass the metadata it issued for the same run/provider snapshot;
    a missing or mismatching binding blocks source promotion and scoped
    absence claims.
    """

    try:
        parsed = (
            result
            if isinstance(result, PublicLawProviderResult)
            else PublicLawProviderResult.model_validate(result)
        )
    except ValidationError as exc:
        return PublicLawValidationResult(
            provider_id="unknown",
            query_id="unknown",
            decision=PublicLawValidationDecision.BLOCKED,
            reason_codes=["PUBLIC_LAW_RESULT_SCHEMA_INVALID", type(exc).__name__],
        )
    if server_metadata is None:
        return PublicLawValidationResult(
            provider_id=parsed.provider_id,
            query_id=parsed.query_id,
            decision=PublicLawValidationDecision.BLOCKED,
            reason_codes=["PUBLIC_LAW_SERVER_METADATA_BINDING_REQUIRED"],
        )
    if parsed.server_metadata != server_metadata:
        return PublicLawValidationResult(
            provider_id=parsed.provider_id,
            query_id=parsed.query_id,
            decision=PublicLawValidationDecision.BLOCKED,
            reason_codes=["PUBLIC_LAW_SERVER_METADATA_MISMATCH"],
        )
    timestamp = now or datetime.now(server_metadata.issued_at.tzinfo)
    if not server_metadata.is_current(now=timestamp):
        return PublicLawValidationResult(
            provider_id=parsed.provider_id,
            query_id=parsed.query_id,
            decision=PublicLawValidationDecision.BLOCKED,
            reason_codes=["PUBLIC_LAW_SERVER_METADATA_NOT_CURRENT"],
        )
    if parsed.status in {
        PublicLawResultStatus.RETRY_REQUIRED,
        PublicLawResultStatus.BLOCKED,
    }:
        return PublicLawValidationResult(
            provider_id=parsed.provider_id,
            query_id=parsed.query_id,
            decision=PublicLawValidationDecision.BLOCKED,
            reason_codes=parsed.reason_codes or ["PUBLIC_LAW_PROVIDER_NOT_AVAILABLE"],
        )
    eligible_ids = [
        source.source_id
        for source in parsed.sources
        if source.trust_status
        in {TrustStatus.OFFICIAL_VERIFIED, TrustStatus.EVIDENCE_ELIGIBLE}
    ]
    if eligible_ids:
        owned_ids = set(server_source_ids or ())
        if not owned_ids:
            return PublicLawValidationResult(
                provider_id=parsed.provider_id,
                query_id=parsed.query_id,
                decision=PublicLawValidationDecision.BLOCKED,
                reason_codes=["PUBLIC_LAW_SERVER_SOURCE_BINDING_REQUIRED"],
            )
        missing = sorted(set(eligible_ids) - owned_ids)
        if missing:
            return PublicLawValidationResult(
                provider_id=parsed.provider_id,
                query_id=parsed.query_id,
                decision=PublicLawValidationDecision.BLOCKED,
                reason_codes=["PUBLIC_LAW_SOURCE_NOT_SERVER_OWNED"],
            )
    if parsed.status is PublicLawResultStatus.PARTIAL or not parsed.coverage_complete:
        return PublicLawValidationResult(
            provider_id=parsed.provider_id,
            query_id=parsed.query_id,
            decision=PublicLawValidationDecision.QUALIFIED,
            eligible_source_ids=[],
            reason_codes=parsed.reason_codes or ["PUBLIC_LAW_COVERAGE_PARTIAL"],
        )
    if parsed.status is PublicLawResultStatus.NOT_FOUND_IN_SCOPE:
        return PublicLawValidationResult(
            provider_id=parsed.provider_id,
            query_id=parsed.query_id,
            decision=PublicLawValidationDecision.ACCEPTED,
            absence_claim_allowed=True,
            reason_codes=["PUBLIC_LAW_NOT_FOUND_IN_BOUNDED_SCOPE"],
        )
    return PublicLawValidationResult(
        provider_id=parsed.provider_id,
        query_id=parsed.query_id,
        decision=PublicLawValidationDecision.ACCEPTED,
        eligible_source_ids=eligible_ids,
        reason_codes=([] if eligible_ids else ["PUBLIC_LAW_CANDIDATES_ONLY"]),
    )


# Short aliases keep adapter code readable while retaining one canonical model.
AdministrativeRuleSource = PublicLawSourceRecord
AdministrativeInterpretationSource = PublicLawSourceRecord
AdministrativeAppealSource = PublicLawSourceRecord
LegislativeMaterialSource = PublicLawSourceRecord
PublicLawSource = PublicLawSourceRecord
SourceLineage = PublicLawLineage
ProcedureRequirement = PublicLawProcedureRequirement
RemedyStage = PublicLawRemedyStage
PublicLawBoundedResult = PublicLawProviderResult
BoundedPublicLawResult = PublicLawProviderResult


__all__ = [
    "AdministrativeAppealSource",
    "AdministrativeInterpretationSource",
    "AdministrativeRuleSource",
    "BoundedPublicLawResult",
    "LegislativeMaterialSource",
    "PublicLawBoundedResult",
    "PublicLawCandidate",
    "PublicLawLineage",
    "PublicLawLineageRelation",
    "PublicLawMaterialType",
    "PublicLawProcedureKind",
    "PublicLawProcedureRequirement",
    "PublicLawProviderResult",
    "PublicLawProviderCapabilities",
    "PublicLawRemedyStage",
    "PublicLawResultStatus",
    "PublicLawSearchRequest",
    "PublicLawServerMetadata",
    "PublicLawSource",
    "PublicLawSourceRecord",
    "PublicLawSourceRole",
    "ProcedureRequirement",
    "RemedyStage",
    "SourceLineage",
    "PublicLawValidationDecision",
    "PublicLawValidationResult",
    "validate_public_law_result",
]
