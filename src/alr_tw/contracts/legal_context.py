"""Provider-neutral temporal, authority, and legal-validity contracts."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from enum import Enum
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .sources import SourceRecord


class TemporalApplicabilityStatus(str, Enum):
    APPLICABLE = "applicable"
    NOT_YET_EFFECTIVE = "not_yet_effective"
    EXPIRED_OR_REPEALED = "expired_or_repealed"
    HISTORICAL_VERSION_UNAVAILABLE = "historical_version_unavailable"
    INDETERMINATE = "indeterminate"


class AuthorityLevel(str, Enum):
    CONSTITUTION = "constitution"
    STATUTE = "statute"
    REGULATION = "regulation"
    ADMINISTRATIVE_RULE = "administrative_rule"
    CONSTITUTIONAL_COURT = "constitutional_court"
    JUDGMENT = "judgment"
    OTHER = "other"


class AuthorityStatus(str, Enum):
    BINDING = "binding"
    PERSUASIVE = "persuasive"
    LIMITED = "limited"
    SUPERSEDED = "superseded"
    UNKNOWN = "unknown"


class LegalValidityStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    REPEALED = "repealed"
    SUSPENDED = "suspended"
    CONFLICTING = "conflicting"
    UNKNOWN = "unknown"


class LegalContextResultStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class TemporalAssessment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.temporal-assessment/v1"] = (
        "alr-tw.temporal-assessment/v1"
    )
    as_of_date: date
    status: TemporalApplicabilityStatus
    effective_from: date | None = None
    effective_until: date | None = None

    @model_validator(mode="after")
    def validate_effective_window(self) -> TemporalAssessment:
        if (
            self.effective_from is not None
            and self.effective_until is not None
            and self.effective_until < self.effective_from
        ):
            raise ValueError("effective_until must not precede effective_from")
        return self


class AuthorityAssessment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.authority-assessment/v1"] = (
        "alr-tw.authority-assessment/v1"
    )
    level: AuthorityLevel
    status: AuthorityStatus
    rationale_codes: list[str] = Field(default_factory=list, max_length=32)


class LegalValidityAssessment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.legal-validity-assessment/v1"] = (
        "alr-tw.legal-validity-assessment/v1"
    )
    status: LegalValidityStatus
    rationale_codes: list[str] = Field(default_factory=list, max_length=32)


class SourceLegalContext(BaseModel):
    """Server-produced assessment for one source at one legal time."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.source-legal-context/v1"] = (
        "alr-tw.source-legal-context/v1"
    )
    source_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    assessed_at: datetime
    temporal: TemporalAssessment
    authority: AuthorityAssessment
    validity: LegalValidityAssessment
    coverage_complete: bool
    limitations: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_assessment(self) -> SourceLegalContext:
        if self.assessed_at.tzinfo is None or self.assessed_at.utcoffset() is None:
            raise ValueError("legal-context assessed_at must be timezone-aware")
        unresolved = (
            self.temporal.status
            in {
                TemporalApplicabilityStatus.HISTORICAL_VERSION_UNAVAILABLE,
                TemporalApplicabilityStatus.INDETERMINATE,
            }
            or self.authority.status is AuthorityStatus.UNKNOWN
            or self.validity.status is LegalValidityStatus.UNKNOWN
        )
        if self.coverage_complete and unresolved:
            raise ValueError("complete legal context cannot contain unresolved states")
        return self


class LegalContextResult(BaseModel):
    """Bounded provider response; absence and provider failure remain distinct."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.legal-context-result/v1"] = (
        "alr-tw.legal-context-result/v1"
    )
    provider_id: str = Field(min_length=1)
    status: LegalContextResultStatus
    records: list[SourceLegalContext] = Field(default_factory=list)
    error_codes: list[str] = Field(default_factory=list, max_length=32)
    limitations: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_result(self) -> LegalContextResult:
        source_ids = [record.source_id for record in self.records]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("legal-context source_id values must be unique")
        if self.status is LegalContextResultStatus.COMPLETE and (
            self.error_codes or any(not record.coverage_complete for record in self.records)
        ):
            raise ValueError("complete legal-context result cannot contain gaps or errors")
        if self.status is LegalContextResultStatus.UNAVAILABLE and self.records:
            raise ValueError("unavailable legal-context result cannot contain records")
        return self


@runtime_checkable
class LegalContextProvider(Protocol):
    """Public port for user-supplied legal-time and authority providers."""

    @property
    def provider_id(self) -> str: ...

    def assess(
        self,
        sources: Sequence[SourceRecord],
        *,
        as_of_date: date,
        assessed_at: datetime,
    ) -> LegalContextResult: ...
