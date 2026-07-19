"""Server-owned legal research state contracts."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .providers import DataMode


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


class ResearchObligationKind(str, Enum):
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
    time_context_checked: bool = False
    limitations: list[str] = Field(default_factory=list)


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
        return self
