"""Server-owned legal research state contracts."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .interop import (
    DiscoveryMode,
    RegisteredResearchPlan,
    ResearchResponsibility,
)
from .providers import DataMode


_PROVIDER_SCOPE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class ResearchDepth(str, Enum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


class PrivacyStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    SAFE = "safe"
    REDACTED_SAFE = "redacted_safe"
    SENSITIVE = "sensitive"
    UNCERTAIN = "uncertain"


class ResearchState(str, Enum):
    CREATED = "created"
    PLANNING = "planning"
    RESEARCHING = "researching"
    VERIFYING = "verifying"
    READY_FOR_DRAFT = "ready_for_draft"
    VALIDATING = "validating"
    VALIDATED = "validated"
    QUALIFIED = "qualified"
    BLOCKED = "blocked"
    PURGED = "purged"
    EXPIRED = "expired"


class ResearchSufficiency(str, Enum):
    """Server-owned assessment of whether a research run can support an answer."""

    SUFFICIENT = "sufficient"
    QUALIFIED = "qualified"
    INSUFFICIENT = "insufficient"
    RETRY_REQUIRED = "retry_required"


class AnswerMode(str, Enum):
    """Permitted answer posture derived from research sufficiency."""

    ORDINARY = "ordinary"
    CONDITIONAL = "conditional"
    REFUSAL_ONLY = "refusal_only"


class ResearchObligationKind(str, Enum):
    EXTERNAL_PLAN_REVIEW = "external_plan_review"
    QUERY_UNDERSTANDING = "query_understanding"
    PRIVACY_SCREEN = "privacy_screen"
    LAW_RESEARCH = "law_research"
    JUDGMENT_RECALL = "judgment_recall"
    JUDGMENT_OFFICIAL_VERIFICATION = "judgment_official_verification"
    CONSTITUTIONAL_RESEARCH = "constitutional_research"
    COUNTER_AUTHORITY = "counter_authority"
    LEGAL_TIME_CONTEXT = "legal_time_context"
    EVIDENCE_SUFFICIENCY = "evidence_sufficiency"
    FINAL_ANSWER_VALIDATION = "final_answer_validation"


class ResearchObligationStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class ResearchObligation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ResearchObligationKind
    status: ResearchObligationStatus = ResearchObligationStatus.PENDING
    required: bool = True
    reason: str = ""
    blocker_code: str | None = None
    # Additive retry metadata.  A pending obligation with these codes may be
    # retried by a caller using a new operation_id; persisted legacy payloads
    # default to an empty list.
    retryable_reason_codes: list[str] = Field(default_factory=list, max_length=32)
    # Server-owned continuation state for bounded providers.  This is written
    # only by ResearchService after validating an executor result; callers
    # never submit or override it when continuing a run.
    counter_authority_progress: dict[str, Any] | None = None
    counter_authority_diagnostic_codes: list[str] = Field(
        default_factory=list,
        max_length=64,
    )


class ResearchBlocker(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    obligation: ResearchObligationKind | None = None


class CoverageState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    law_checked: bool = False
    judgment_checked: bool = False
    constitutional_checked: bool = False
    counter_authority_checked: bool = False
    counter_authority_status: str = "not_searched"
    # ``None`` preserves v1 persisted runs; consumers fall back to the legacy
    # aggregate coverage flag until a new counter-authority execution writes
    # the split receipt explicitly.
    counter_authority_coverage_complete: bool | None = None
    counter_authority_relation_receipt_ids: list[str] = Field(default_factory=list)
    time_context_checked: bool = False
    limitations: list[str] = Field(default_factory=list)
    # Current coverage receipt fields.  These are additive so earlier payloads remain readable.
    coverage_complete: bool = False
    absence_claim_allowed: bool = False
    partial_reason_codes: list[str] = Field(default_factory=list)
    error_reason_codes: list[str] = Field(default_factory=list)
    timeout_reason_codes: list[str] = Field(default_factory=list)
    selected_provider_scope: list[str] = Field(default_factory=list)
    successful_provider_scope: list[str] = Field(default_factory=list)
    bounded_time_scope: str | None = None
    bounded_query_scope: str | None = None
    snapshot_id: str | None = None
    receipt_reference: str | None = None

    @model_validator(mode="after")
    def validate_coverage_receipt(self) -> CoverageState:
        for field_name in (
            "partial_reason_codes",
            "error_reason_codes",
            "timeout_reason_codes",
            "selected_provider_scope",
            "successful_provider_scope",
            "counter_authority_relation_receipt_ids",
        ):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} values must be unique")
        if self.absence_claim_allowed and (
            not self.coverage_complete
            or self.limitations
            or self.partial_reason_codes
            or self.error_reason_codes
            or self.timeout_reason_codes
        ):
            raise ValueError(
                "absence_claim_allowed requires complete coverage without gaps or errors"
            )
        if self.absence_claim_allowed:
            if not self.counter_authority_checked:
                raise ValueError(
                    "absence_claim_allowed requires counter-authority coverage"
                )
            if not self.bounded_query_scope or not self.bounded_query_scope.strip():
                raise ValueError(
                    "absence_claim_allowed requires bounded query scope"
                )
            for field_name in ("selected_provider_scope", "successful_provider_scope"):
                invalid_ids = [
                    value
                    for value in getattr(self, field_name)
                    if not value.strip() or _PROVIDER_SCOPE_ID_PATTERN.fullmatch(value) is None
                ]
                if invalid_ids:
                    raise ValueError(
                        "absence_claim_allowed requires valid provider scope identifiers"
                    )
            selected = set(self.selected_provider_scope)
            successful = set(self.successful_provider_scope)
            if not selected or not selected.issubset(successful):
                raise ValueError(
                    "absence_claim_allowed requires successful selected provider scope"
                )
        return self


class ResearchSufficiencyAssessment(BaseModel):
    """Deterministic, server-produced sufficiency decision and audit reasons."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "alr-tw.research-sufficiency/v1"
    research_sufficiency: ResearchSufficiency
    answer_mode: AnswerMode
    workflow_complete: bool
    reason_codes: list[str] = Field(default_factory=list)
    missing_obligations: list[ResearchObligationKind] = Field(default_factory=list)


def _is_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


class ResearchRun(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "alr-tw.research-run/v1"
    run_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    requested_mode: DataMode
    effective_mode: DataMode
    research_depth: ResearchDepth = ResearchDepth.STANDARD
    include_counter_authority: bool = True
    ephemeral: bool = False
    as_of_date: date | None = None
    privacy_status: PrivacyStatus
    state: ResearchState
    obligations: list[ResearchObligation]
    coverage: CoverageState
    blockers: list[ResearchBlocker] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    semantic_recall_degraded: bool = False
    judgment_recall_incomplete: bool = False
    responsibility: ResearchResponsibility = Field(default_factory=ResearchResponsibility)
    registered_plan: RegisteredResearchPlan | None = None
    # Current fields.  They are server-owned output; callers must not use them to
    # bypass evaluate_research_sufficiency().
    workflow_complete: bool = False
    research_sufficiency: ResearchSufficiency = ResearchSufficiency.INSUFFICIENT
    answer_mode: AnswerMode = AnswerMode.REFUSAL_ONLY

    @model_validator(mode="after")
    def validate_timestamps_and_modes(self) -> ResearchRun:
        if any(not _is_aware(value) for value in (self.created_at, self.updated_at, self.expires_at)):
            raise ValueError("research timestamps must be timezone-aware")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be later than created_at")
        if self.effective_mode == DataMode.HYBRID_VERIFIED and (
            self.requested_mode != DataMode.HYBRID_VERIFIED
        ):
            raise ValueError("effective mode cannot silently enable external semantic recall")
        if (
            self.responsibility.discovery_mode is DiscoveryMode.SERVER_MANAGED
            and self.registered_plan is not None
        ):
            raise ValueError("registered plans require client-assisted discovery")
        # v0.7 payloads had no workflow_complete field.  A persisted run that
        # already reached the draft/validation stages is structurally complete;
        # hydrate that fact without trusting any caller-supplied sufficiency.
        if self.state in {
            ResearchState.READY_FOR_DRAFT,
            ResearchState.VALIDATING,
            ResearchState.VALIDATED,
            ResearchState.QUALIFIED,
        }:
            object.__setattr__(self, "workflow_complete", True)
        return self


def evaluate_research_sufficiency(run: ResearchRun) -> ResearchSufficiencyAssessment:
    """Evaluate sufficiency using only server-owned run state.

    Completion of obligations is intentionally distinct from sufficiency.  A
    run with an unavailable provider, unresolved required evidence, or a
    bounded/partial coverage gap can therefore never become ordinary merely
    because its workflow reached ``READY_FOR_DRAFT``.
    """

    non_final = [
        item
        for item in run.obligations
        if item.kind is not ResearchObligationKind.FINAL_ANSWER_VALIDATION
    ]
    pending = [
        item
        for item in non_final
        if item.required and item.status is not ResearchObligationStatus.COMPLETED
    ]
    blocked = [
        item
        for item in pending
        if item.status is ResearchObligationStatus.BLOCKED
    ]
    workflow_complete = not pending
    reasons: list[str] = []
    missing_obligations = [item.kind for item in pending]
    if pending:
        reasons.append("RESEARCH_REQUIRED_OBLIGATION_PENDING")
    if blocked:
        reasons.append("RESEARCH_REQUIRED_OBLIGATION_BLOCKED")

    retryable_blocked = [
        item
        for item in blocked
        if _is_retryable_reason(item.blocker_code or "")
        or _is_retryable_reason(item.reason)
    ]
    nonretryable_blocked = [
        item for item in blocked if item not in retryable_blocked
    ]
    reasons.extend(
        f"NON_RETRYABLE_BLOCKED:{item.kind.value}" for item in nonretryable_blocked
    )

    transient_codes = [
        *run.coverage.timeout_reason_codes,
        *[
            code
            for code in run.coverage.error_reason_codes
            if _is_retryable_reason(code)
        ],
    ]
    if transient_codes or retryable_blocked:
        if retryable_blocked:
            reasons.extend(
                f"RETRY_REQUIRED:{item.kind.value}" for item in retryable_blocked
            )
        reasons.extend(f"RETRY_REQUIRED:{code}" for code in transient_codes)
        return ResearchSufficiencyAssessment(
            research_sufficiency=ResearchSufficiency.RETRY_REQUIRED,
            answer_mode=AnswerMode.REFUSAL_ONLY,
            workflow_complete=workflow_complete,
            reason_codes=sorted(set(reasons)),
            missing_obligations=missing_obligations,
        )

    if run.coverage.error_reason_codes:
        reasons.extend(f"COVERAGE_ERROR:{code}" for code in run.coverage.error_reason_codes)

    # Synthetic mode is an offline contract fixture.  Even if an internal
    # test or adapter supplies evidence-shaped IDs, those records cannot be
    # treated as live legal authority or support a presentable answer.
    synthetic_mode = run.effective_mode is DataMode.SYNTHETIC
    if synthetic_mode:
        reasons.append("SYNTHETIC_MODE_NO_LIVE_EVIDENCE")

    # Evidence is server-owned and is refreshed by ResearchService from the
    # managed store.  An empty list cannot support a legal answer.
    if not run.evidence_ids:
        reasons.append("NO_SERVER_VERIFIED_EVIDENCE")

    required_kinds = {item.kind for item in non_final if item.required}
    required_coverage = {
        ResearchObligationKind.LAW_RESEARCH: run.coverage.law_checked,
        ResearchObligationKind.JUDGMENT_RECALL: run.coverage.judgment_checked,
        ResearchObligationKind.JUDGMENT_OFFICIAL_VERIFICATION: run.coverage.judgment_checked,
        ResearchObligationKind.CONSTITUTIONAL_RESEARCH: run.coverage.constitutional_checked,
        ResearchObligationKind.COUNTER_AUTHORITY: run.coverage.counter_authority_checked,
        ResearchObligationKind.LEGAL_TIME_CONTEXT: run.coverage.time_context_checked,
    }
    missing_coverage = sorted(
        [
            kind
            for kind, checked in required_coverage.items()
            if kind in required_kinds and not checked
        ],
        key=lambda kind: kind.value,
    )
    soft_missing_coverage = [
        kind for kind in missing_coverage if kind is ResearchObligationKind.COUNTER_AUTHORITY
    ]
    hard_missing_coverage = [
        kind for kind in missing_coverage if kind is not ResearchObligationKind.COUNTER_AUTHORITY
    ]
    hard_incomplete_reasons: list[str] = []
    if (
        ResearchObligationKind.JUDGMENT_OFFICIAL_VERIFICATION in required_kinds
        and run.judgment_recall_incomplete
    ):
        hard_incomplete_reasons.append(
            "REQUIRED_COVERAGE_INCOMPLETE:judgment_official_verification"
        )
    if ResearchObligationKind.LEGAL_TIME_CONTEXT in required_kinds and any(
        "HISTORICAL_LAW_VERSION_UNSUPPORTED" in code
        for code in (
            *run.coverage.limitations,
            *run.coverage.partial_reason_codes,
            *run.coverage.error_reason_codes,
        )
    ):
        hard_incomplete_reasons.append("REQUIRED_COVERAGE_INCOMPLETE:legal_time_context")
    reasons.extend(
        f"SOFT_COVERAGE_MISSING:{kind.value}" for kind in soft_missing_coverage
    )
    reasons.extend(
        f"REQUIRED_COVERAGE_MISSING:{kind.value}" for kind in hard_missing_coverage
    )
    reasons.extend(hard_incomplete_reasons)

    hard_errors = bool(run.coverage.error_reason_codes)
    has_gaps = bool(
        run.coverage.partial_reason_codes
        or run.coverage.timeout_reason_codes
        or run.coverage.limitations
        or run.semantic_recall_degraded
        or run.judgment_recall_incomplete
        or not run.coverage.coverage_complete
        or soft_missing_coverage
        or hard_missing_coverage
        or hard_incomplete_reasons
    )
    if not workflow_complete:
        return ResearchSufficiencyAssessment(
            research_sufficiency=ResearchSufficiency.INSUFFICIENT,
            answer_mode=AnswerMode.REFUSAL_ONLY,
            workflow_complete=False,
            reason_codes=sorted(set(reasons)),
            missing_obligations=missing_obligations,
        )
    if (
        synthetic_mode
        or not run.evidence_ids
        or hard_errors
        or hard_missing_coverage
        or hard_incomplete_reasons
    ):
        return ResearchSufficiencyAssessment(
            research_sufficiency=ResearchSufficiency.INSUFFICIENT,
            answer_mode=AnswerMode.REFUSAL_ONLY,
            workflow_complete=True,
            reason_codes=sorted(set(reasons)),
            missing_obligations=[],
        )
    if has_gaps:
        reasons.append("RESEARCH_COVERAGE_QUALIFIED")
        return ResearchSufficiencyAssessment(
            research_sufficiency=ResearchSufficiency.QUALIFIED,
            answer_mode=AnswerMode.CONDITIONAL,
            workflow_complete=True,
            reason_codes=sorted(set(reasons)),
            missing_obligations=[],
        )
    return ResearchSufficiencyAssessment(
        research_sufficiency=ResearchSufficiency.SUFFICIENT,
        answer_mode=AnswerMode.ORDINARY,
        workflow_complete=True,
        reason_codes=sorted(set(reasons)),
        missing_obligations=[],
    )


def _is_retryable_reason(code: str) -> bool:
    normalized = code.upper()
    return any(
        marker in normalized
        for marker in (
            "UNAVAILABLE",
            "TIMEOUT",
            "TEMPORARY",
            "RATE_LIMIT",
            "RETRY",
        )
    )
