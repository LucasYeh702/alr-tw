"""Provider conformance and receipt-aware promotion contracts.

The common provider surface intentionally keeps retrieval results small: a
ProviderResult contains opaque source/evidence references rather than copying
source bodies. This module is the shared server-side gate for those
references. It does not fetch data, issue receipts, or decide legal meaning.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .provider_snapshot import (
    ProviderSnapshotReceipt,
    SnapshotConsistency,
    SnapshotConsistencyResult,
    assess_snapshot_consistency,
)
from .providers import ProviderResult, ProviderResultStatus
from .sources import EvidenceSpan, SourceRecord, TrustStatus


_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"


class ProviderRole(str, Enum):
    """The narrow trust role a provider is allowed to play."""

    OFFICIAL_VERIFIER = "official_verifier"
    CANDIDATE_ONLY = "candidate_only"
    PROVIDER_NEUTRAL = "provider_neutral"


class ProviderConformanceStatus(str, Enum):
    """Server-owned result of structural provider conformance."""

    CONFORMING = "conforming"
    QUALIFIED = "qualified"
    BLOCKED = "blocked"


class ProviderConformanceRequest(BaseModel):
    """Server-owned expectations for one provider operation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.provider-conformance-request/v1"] = (
        "alr-tw.provider-conformance-request/v1"
    )
    provider_id: str = Field(pattern=_ID_PATTERN)
    role: ProviderRole
    bounded_scope: str | None = Field(default=None, max_length=500)
    expected_material_types: list[str] = Field(default_factory=list, max_length=8)
    require_snapshot_receipt: bool = False

    @model_validator(mode="after")
    def validate_scope(self) -> ProviderConformanceRequest:
        if self.bounded_scope is not None and not self.bounded_scope.strip():
            raise ValueError("provider conformance bounded_scope must not be blank")
        if len(self.expected_material_types) != len(set(self.expected_material_types)):
            raise ValueError("provider conformance material types must be unique")
        return self


class ProviderConformanceResult(BaseModel):
    """A deterministic conformance decision, never a legal conclusion."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.provider-conformance/v1"] = (
        "alr-tw.provider-conformance/v1"
    )
    provider_id: str
    decision: ProviderConformanceStatus
    eligible_source_ids: list[str] = Field(default_factory=list, max_length=128)
    eligible_evidence_ids: list[str] = Field(default_factory=list, max_length=256)
    absence_claim_allowed: bool = False
    ordinary_eligible: bool = False
    snapshot_consistency: SnapshotConsistencyResult
    reason_codes: list[str] = Field(default_factory=list, max_length=64)
    candidate_count: int = Field(default=0, ge=0)
    semantic_entailment_performed: Literal[False] = False
    server_owned_decision: Literal[True] = True

    @model_validator(mode="after")
    def validate_decision(self) -> ProviderConformanceResult:
        if len(self.eligible_source_ids) != len(set(self.eligible_source_ids)):
            raise ValueError("provider conformance source IDs must be unique")
        if len(self.eligible_evidence_ids) != len(set(self.eligible_evidence_ids)):
            raise ValueError("provider conformance evidence IDs must be unique")
        if self.decision is not ProviderConformanceStatus.CONFORMING:
            if self.absence_claim_allowed or self.ordinary_eligible:
                raise ValueError("only conforming results may expose eligibility flags")
        if self.absence_claim_allowed and self.eligible_source_ids:
            raise ValueError("absence claim cannot include eligible sources")
        if self.ordinary_eligible and not (
            self.eligible_source_ids or self.absence_claim_allowed
        ):
            raise ValueError("ordinary eligibility requires eligible sources or scoped absence")
        return self


def _as_result(value: ProviderResult | Mapping[str, Any]) -> ProviderResult:
    return value if isinstance(value, ProviderResult) else ProviderResult.model_validate(value)


def _unique(values: Sequence[str]) -> bool:
    return len(values) == len(set(values))


def _flatten_strings(value: object, *, key: str = "") -> list[str]:
    """Collect metadata strings for a conservative boundary-only privacy scan."""

    if isinstance(value, str):
        return [f"{key}={value}"]
    if isinstance(value, Mapping):
        values: list[str] = []
        for child_key, child_value in value.items():
            values.extend(_flatten_strings(child_value, key=str(child_key)))
        return values
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        sequence_values: list[str] = []
        for child_value in value:
            sequence_values.extend(_flatten_strings(child_value, key=key))
        return sequence_values
    if key:
        return [f"{key}={value!s}"]
    return []


def _privacy_reason_codes(result: ProviderResult) -> list[str]:
    """Detect obvious secrets/deployment paths without inspecting legal text."""

    reasons: list[str] = []
    sensitive_keys = (
        "access_token",
        "api_key",
        "authorization",
        "bearer",
        "credential",
        "password",
        "private_key",
        "secret",
        "token",
    )
    path_markers = ("/users/", "\\users\\", "sqlite://", "postgres://", "mysql://")
    for item in _flatten_strings(result.metadata):
        lowered = item.casefold()
        key, _, value = item.partition("=")
        if any(marker in key.casefold() for marker in sensitive_keys):
            reasons.append("PROVIDER_METADATA_SENSITIVE_FIELD")
        if "bearer " in lowered or any(marker in value.casefold() for marker in path_markers):
            reasons.append("PROVIDER_METADATA_PRIVATE_DEPLOYMENT_MARKER")
    return sorted(set(reasons))


def _snapshot_result(
    receipts: Sequence[ProviderSnapshotReceipt],
    server_receipts: Sequence[ProviderSnapshotReceipt] | None,
    *,
    now: datetime,
) -> SnapshotConsistencyResult:
    return assess_snapshot_consistency(receipts, server_receipts=server_receipts, now=now)


def validate_provider_conformance(
    result: ProviderResult | Mapping[str, Any],
    *,
    request: ProviderConformanceRequest,
    server_source_ids: Collection[str] | None,
    server_evidence_ids: Collection[str] | None,
    server_sources: Mapping[str, SourceRecord] | None = None,
    server_evidence: Mapping[str, EvidenceSpan] | None = None,
    receipts: Sequence[ProviderSnapshotReceipt] = (),
    server_receipts: Sequence[ProviderSnapshotReceipt] | None = None,
    now: datetime | None = None,
) -> ProviderConformanceResult:
    """Validate one provider result against independent server-owned inputs.

    server_source_ids/server_evidence_ids and the optional object mappings are
    deliberately separate from the provider payload. A caller controlling
    both a result and its asserted trust fields cannot use this function to
    self-promote a candidate.
    """

    timestamp = now or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    try:
        parsed = _as_result(result)
    except ValidationError as exc:
        snapshot = _snapshot_result(receipts, server_receipts, now=timestamp)
        return ProviderConformanceResult(
            provider_id="unknown",
            decision=ProviderConformanceStatus.BLOCKED,
            snapshot_consistency=snapshot,
            reason_codes=["PROVIDER_RESULT_SCHEMA_INVALID", type(exc).__name__],
        )

    reasons: list[str] = _privacy_reason_codes(parsed)
    source_ids = list(parsed.source_ids)
    evidence_ids = list(parsed.evidence_ids)
    server_source_values = list(server_source_ids or ())
    server_evidence_values = list(server_evidence_ids or ())
    source_catalog = set(server_source_values)
    evidence_catalog = set(server_evidence_values)
    snapshot = _snapshot_result(receipts, server_receipts, now=timestamp)
    eligible_source_ids: list[str] = []
    eligible_evidence_ids: list[str] = []
    blockers: list[str] = list(reasons)

    if parsed.provider_id != request.provider_id:
        blockers.append("PROVIDER_ID_MISMATCH")
    if not _unique(source_ids):
        blockers.append("PROVIDER_SOURCE_ID_DUPLICATE")
    if not _unique(evidence_ids):
        blockers.append("PROVIDER_EVIDENCE_ID_DUPLICATE")
    if not _unique(server_source_values):
        blockers.append("PROVIDER_SERVER_SOURCE_BINDING_INVALID")
    if not _unique(server_evidence_values):
        blockers.append("PROVIDER_SERVER_EVIDENCE_BINDING_INVALID")
    if request.role is ProviderRole.CANDIDATE_ONLY and (source_ids or evidence_ids):
        blockers.append("PROVIDER_CANDIDATE_PROMOTION_FORBIDDEN")
    if source_ids and not source_catalog:
        blockers.append("PROVIDER_SERVER_SOURCE_BINDING_REQUIRED")
    if evidence_ids and not evidence_catalog:
        blockers.append("PROVIDER_SERVER_EVIDENCE_BINDING_REQUIRED")

    source_objects: dict[str, SourceRecord] = {}
    if source_ids:
        if server_sources is None:
            blockers.append("PROVIDER_SERVER_SOURCE_OBJECTS_REQUIRED")
        for source_id in source_ids:
            source = server_sources.get(source_id) if server_sources is not None else None
            if source_id not in source_catalog or source is None:
                blockers.append("PROVIDER_SOURCE_NOT_SERVER_BOUND")
                continue
            if source.source_id != source_id or source.provider_id != parsed.provider_id:
                blockers.append("PROVIDER_SOURCE_IDENTITY_MISMATCH")
                continue
            if source.trust_status not in {
                TrustStatus.OFFICIAL_VERIFIED,
                TrustStatus.EVIDENCE_ELIGIBLE,
            }:
                blockers.append("PROVIDER_SOURCE_NOT_EVIDENCE_ELIGIBLE")
                continue
            if source.expires_at <= timestamp:
                blockers.append("PROVIDER_SOURCE_STALE")
                continue
            if source.fetched_at > timestamp or (
                source.verified_at is not None and source.verified_at > timestamp
            ):
                blockers.append("PROVIDER_SOURCE_TIMESTAMP_FUTURE")
                continue
            material = getattr(source.material_type, "value", str(source.material_type))
            if request.expected_material_types and material not in request.expected_material_types:
                blockers.append("PROVIDER_MATERIAL_TYPE_MISMATCH")
                continue
            source_objects[source_id] = source
            eligible_source_ids.append(source_id)

    if evidence_ids:
        if server_evidence is None:
            blockers.append("PROVIDER_SERVER_EVIDENCE_OBJECTS_REQUIRED")
        for evidence_id in evidence_ids:
            evidence = server_evidence.get(evidence_id) if server_evidence is not None else None
            if evidence_id not in evidence_catalog or evidence is None:
                blockers.append("PROVIDER_EVIDENCE_NOT_SERVER_BOUND")
                continue
            if evidence.evidence_id != evidence_id:
                blockers.append("PROVIDER_EVIDENCE_IDENTITY_MISMATCH")
                continue
            if evidence.source_id not in source_objects:
                blockers.append("PROVIDER_EVIDENCE_SOURCE_NOT_ELIGIBLE")
                continue
            if not evidence.eligible_for_claim_support:
                blockers.append("PROVIDER_EVIDENCE_NOT_CLAIM_ELIGIBLE")
                continue
            eligible_evidence_ids.append(evidence_id)

    if receipts and any(item.provider_id != parsed.provider_id for item in receipts):
        blockers.append("PROVIDER_SNAPSHOT_PROVIDER_MISMATCH")
    if snapshot.status is not SnapshotConsistency.CONSISTENT and receipts:
        blockers.append("PROVIDER_SNAPSHOT_NOT_CONSISTENT")
    if request.require_snapshot_receipt and (
        not receipts or snapshot.status is not SnapshotConsistency.CONSISTENT
    ):
        blockers.append("PROVIDER_SNAPSHOT_RECEIPT_REQUIRED")

    if parsed.status is ProviderResultStatus.ERROR:
        blockers.append("PROVIDER_ERROR_RETRY_REQUIRED")
    elif parsed.coverage_complete and parsed.status is ProviderResultStatus.PARTIAL:
        blockers.append("PROVIDER_COVERAGE_STATUS_CONFLICT")
    if parsed.status is ProviderResultStatus.FOUND and not (
        source_ids or evidence_ids or parsed.candidates
    ):
        blockers.append("PROVIDER_FOUND_RESULT_EMPTY")
    if parsed.status is ProviderResultStatus.NOT_FOUND and parsed.candidates:
        blockers.append("PROVIDER_NOT_FOUND_WITH_CANDIDATES")

    if blockers:
        reason_codes = list(dict.fromkeys(reasons + blockers))
        return ProviderConformanceResult(
            provider_id=parsed.provider_id,
            decision=ProviderConformanceStatus.BLOCKED,
            snapshot_consistency=snapshot,
            reason_codes=reason_codes,
            candidate_count=len(parsed.candidates),
        )

    qualified_reasons = list(reasons)
    absence = False
    conforming = True
    if parsed.status is ProviderResultStatus.PARTIAL or not parsed.coverage_complete:
        conforming = False
        qualified_reasons.append("PROVIDER_COVERAGE_PARTIAL")
    elif parsed.status is ProviderResultStatus.NOT_FOUND:
        if request.bounded_scope and not source_ids and not evidence_ids and not parsed.candidates:
            absence = True
        else:
            conforming = False
            qualified_reasons.append("PROVIDER_BOUNDED_SCOPE_REQUIRED")
    if request.role is ProviderRole.CANDIDATE_ONLY:
        conforming = False
        qualified_reasons.append("PROVIDER_CANDIDATE_ONLY")
    if parsed.status is ProviderResultStatus.FOUND and not source_ids:
        conforming = False
        qualified_reasons.append("PROVIDER_CANDIDATES_ONLY")
    if receipts and snapshot.status is not SnapshotConsistency.CONSISTENT:
        conforming = False
        qualified_reasons.append("PROVIDER_SNAPSHOT_NOT_CERTIFIED")
    if (source_ids or evidence_ids) and not receipts:
        conforming = False
        qualified_reasons.append("PROVIDER_SNAPSHOT_RECEIPT_MISSING")
    decision = (
        ProviderConformanceStatus.CONFORMING
        if conforming
        else ProviderConformanceStatus.QUALIFIED
    )
    ordinary = decision is ProviderConformanceStatus.CONFORMING and (
        bool(eligible_source_ids) or absence
    )
    return ProviderConformanceResult(
        provider_id=parsed.provider_id,
        decision=decision,
        eligible_source_ids=(
            eligible_source_ids if decision is ProviderConformanceStatus.CONFORMING else []
        ),
        eligible_evidence_ids=(
            eligible_evidence_ids if decision is ProviderConformanceStatus.CONFORMING else []
        ),
        absence_claim_allowed=absence if decision is ProviderConformanceStatus.CONFORMING else False,
        ordinary_eligible=ordinary,
        snapshot_consistency=snapshot,
        reason_codes=list(dict.fromkeys(qualified_reasons)),
        candidate_count=len(parsed.candidates),
    )


__all__ = [
    "ProviderConformanceRequest",
    "ProviderConformanceResult",
    "ProviderConformanceStatus",
    "ProviderRole",
    "validate_provider_conformance",
]
