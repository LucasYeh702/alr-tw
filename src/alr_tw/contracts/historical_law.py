"""Historical-law and Legislative Yuan provider-neutral contracts.

The public package exposes a bounded port for a deployer-owned Legislative
Yuan connector.  It does not ship an endpoint, credentials, corpus, or a
claim that legislative history is itself the applicable statute.  Normative
law-version sources and explanatory legislative materials remain separate so
an applicability resolver cannot accidentally treat a committee report as a
law text.
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import date, datetime
from enum import Enum
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .public_law import (
    PublicLawMaterialType,
    PublicLawProviderResult,
    PublicLawSourceRole,
    PublicLawServerMetadata,
    PublicLawValidationDecision,
    validate_public_law_result,
)


_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"


class HistoricalLawRecordRole(str, Enum):
    """Role of a record returned by a historical-law provider."""

    NORMATIVE_TEXT = "normative_text"
    LEGISLATIVE_HISTORY = "legislative_history"


class LegislativeMaterialRole(str, Enum):
    """Typed role of an official Legislative Yuan locator.

    These roles describe the legislative record that was located.  They do
    not turn a proposal, report, caucus record, or third-reading record into
    normative law text.
    """

    PROPOSAL_REASON = "proposal_reason"
    PROPOSAL_DOCUMENT = "proposal_document"
    ARTICLE_REASON = "article_reason"
    ARTICLE_COMPARISON = "article_comparison"
    COMMITTEE_REPORT = "committee_report"
    COMMITTEE_BILL = "committee_bill"
    CAUCUS_RECORD = "caucus_record"
    THIRD_READING_TEXT = "third_reading_text"
    THIRD_READING_RECORD = "third_reading_record"
    PROMULGATED_VERSION_LINK = "promulgated_version_link"


class LegislativeStage(str, Enum):
    """Legislative process stage attached to a locator."""

    PROPOSAL = "proposal"
    COMMITTEE_REVIEW = "committee_review"
    CAUCUS = "caucus"
    SECOND_READING = "second_reading"
    THIRD_READING = "third_reading"
    PROMULGATION = "promulgation"
    UNKNOWN = "unknown"


_LEGISLATIVE_HOSTS = {"data.ly.gov.tw", "ppg.ly.gov.tw", "lis.ly.gov.tw"}


class LegislativeHistoryRecord(BaseModel):
    """One bounded, typed Legislative Yuan record or locator.

    ``text`` is populated only from structured JSON fields supplied by the
    official dataset.  The connector deliberately does not parse linked PDF
    or DOC files.  A record may therefore be locator-only and remain
    candidate material until the server-owned source promotion gate accepts
    it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.legislative-history-record/v1"] = (
        "alr-tw.legislative-history-record/v1"
    )
    record_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    role: LegislativeMaterialRole
    bill_no: str | None = Field(default=None, min_length=1, max_length=128)
    term: str | None = Field(default=None, min_length=1, max_length=32)
    session: str | None = Field(default=None, min_length=1, max_length=32)
    stage: LegislativeStage = LegislativeStage.UNKNOWN
    document_date: date | None = None
    source_id: str | None = Field(default=None, pattern=_IDENTIFIER_PATTERN)
    candidate_id: str | None = Field(default=None, pattern=_IDENTIFIER_PATTERN)
    locator_url: str | None = Field(default=None, max_length=2000)
    title: str | None = Field(default=None, max_length=500)
    text: str | None = Field(default=None, max_length=4000)
    metadata: dict[str, str | int | bool | None] = Field(default_factory=dict)
    candidate_only: Literal[True] = True

    @staticmethod
    def _validate_locator_url(value: str) -> None:
        try:
            parsed = urlparse(value)
            port = parsed.port
        except ValueError as exc:
            raise ValueError("LEGISLATIVE_HISTORY_LOCATOR_URL_INVALID") from exc
        if (
            parsed.scheme != "https"
            or parsed.hostname is None
            or parsed.hostname.lower() not in _LEGISLATIVE_HOSTS
            or parsed.username is not None
            or parsed.password is not None
            or port not in {None, 443}
            or parsed.fragment
        ):
            raise ValueError("LEGISLATIVE_HISTORY_LOCATOR_URL_INVALID")

    @model_validator(mode="after")
    def validate_record(self) -> LegislativeHistoryRecord:
        if self.source_id is None and self.candidate_id is None:
            raise ValueError("LEGISLATIVE_HISTORY_SOURCE_OR_CANDIDATE_REQUIRED")
        if self.locator_url is not None:
            self._validate_locator_url(self.locator_url)
        return self


# Readable aliases for deployers that use the shorter role/model names.
LegislativeRecord = LegislativeHistoryRecord
LegislativeRole = LegislativeMaterialRole


def _same_legislative_scope_value(actual: str | None, expected: str) -> bool:
    """Compare term/session values without treating zero-padding as a mismatch."""
    if actual is None:
        return True
    normalized_actual = actual.strip()
    normalized_expected = expected.strip()
    if normalized_actual.isdecimal() and normalized_expected.isdecimal():
        return int(normalized_actual) == int(normalized_expected)
    return normalized_actual == normalized_expected


class HistoricalLawQuery(BaseModel):
    """Bounded historical-law lookup request.

    ``as_of_date`` is mandatory.  A caller asking for the current law should
    still explicitly choose today's date; the provider must never silently
    substitute the retrieval date for a historical applicability date.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.historical-law-query/v1"] = (
        "alr-tw.historical-law-query/v1"
    )
    query_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    law_identifier: str | None = Field(default=None, min_length=1, max_length=300)
    law_name: str | None = Field(default=None, min_length=1, max_length=300)
    bill_no: str | None = Field(default=None, min_length=1, max_length=128)
    term: str | None = Field(default=None, min_length=1, max_length=32)
    session: str | None = Field(default=None, min_length=1, max_length=32)
    as_of_date: date
    bounded_scope: str = Field(min_length=1, max_length=500)
    include_legislative_history: bool = True
    max_results: int = Field(default=20, ge=1, le=50)

    @model_validator(mode="after")
    def validate_query(self) -> HistoricalLawQuery:
        if self.law_identifier is None and self.law_name is None:
            raise ValueError("HISTORICAL_LAW_IDENTIFIER_OR_NAME_REQUIRED")
        for field_name in ("law_identifier", "law_name"):
            value = getattr(self, field_name)
            if value is not None and not value.strip():
                raise ValueError(f"HISTORICAL_LAW_{field_name.upper()}_REQUIRED")
        if not self.bounded_scope.strip():
            raise ValueError("HISTORICAL_LAW_BOUNDED_SCOPE_REQUIRED")
        for field_name in ("bill_no", "term", "session"):
            value = getattr(self, field_name)
            if value is not None and not value.strip():
                raise ValueError(f"HISTORICAL_LAW_{field_name.upper()}_REQUIRED")
        return self


class HistoricalLawResolution(BaseModel):
    """Server-owned separation of law-version and legislative-material IDs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.historical-law-resolution/v1"] = (
        "alr-tw.historical-law-resolution/v1"
    )
    query_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    provider_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    law_identifier: str = Field(min_length=1, max_length=300)
    as_of_date: date
    bounded_scope: str = Field(min_length=1, max_length=500)
    bill_no: str | None = Field(default=None, min_length=1, max_length=128)
    term: str | None = Field(default=None, min_length=1, max_length=32)
    session: str | None = Field(default=None, min_length=1, max_length=32)
    provider_result: PublicLawProviderResult
    normative_source_ids: list[str] = Field(default_factory=list, max_length=50)
    legislative_material_source_ids: list[str] = Field(default_factory=list, max_length=50)
    legislative_records: list[LegislativeHistoryRecord] = Field(
        default_factory=list,
        max_length=50,
    )
    server_owned: Literal[True] = True
    semantic_entailment_performed: Literal[False] = False
    warnings: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_resolution(self) -> HistoricalLawResolution:
        if self.provider_result.provider_id != self.provider_id:
            raise ValueError("HISTORICAL_LAW_PROVIDER_MISMATCH")
        if self.provider_result.query_id != self.query_id:
            raise ValueError("HISTORICAL_LAW_QUERY_MISMATCH")
        if self.provider_result.bounded_scope != self.bounded_scope:
            raise ValueError("HISTORICAL_LAW_SCOPE_MISMATCH")
        normative = set(self.normative_source_ids)
        legislative = set(self.legislative_material_source_ids)
        if len(normative) != len(self.normative_source_ids):
            raise ValueError("HISTORICAL_LAW_NORMATIVE_SOURCE_DUPLICATE")
        if len(legislative) != len(self.legislative_material_source_ids):
            raise ValueError("HISTORICAL_LAW_LEGISLATIVE_SOURCE_DUPLICATE")
        if normative & legislative:
            raise ValueError("HISTORICAL_LAW_SOURCE_ROLE_OVERLAP")
        source_map = {source.source_id: source for source in self.provider_result.sources}
        if not normative.issubset(source_map) or not legislative.issubset(source_map):
            raise ValueError("HISTORICAL_LAW_SOURCE_NOT_IN_RESULT")
        if any(
            source_map[source_id].material_type is not PublicLawMaterialType.HISTORICAL_STATUTE
            for source_id in normative
        ):
            raise ValueError("HISTORICAL_LAW_NORMATIVE_SOURCE_TYPE_MISMATCH")
        if any(
            source_map[source_id].material_type is not PublicLawMaterialType.LEGISLATIVE_MATERIAL
            for source_id in legislative
        ):
            raise ValueError("HISTORICAL_LAW_LEGISLATIVE_SOURCE_TYPE_MISMATCH")
        record_ids = [record.record_id for record in self.legislative_records]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("HISTORICAL_LAW_LEGISLATIVE_RECORD_DUPLICATE")
        if self.bill_no is not None and any(
            record.bill_no not in {None, self.bill_no} for record in self.legislative_records
        ):
            raise ValueError("HISTORICAL_LAW_BILL_MISMATCH")
        if self.term is not None and any(
            not _same_legislative_scope_value(record.term, self.term)
            for record in self.legislative_records
        ):
            raise ValueError("HISTORICAL_LAW_TERM_MISMATCH")
        if self.session is not None and any(
            not _same_legislative_scope_value(record.session, self.session)
            for record in self.legislative_records
        ):
            raise ValueError("HISTORICAL_LAW_SESSION_MISMATCH")
        for record in self.legislative_records:
            if record.source_id is None:
                continue
            if record.source_id in normative:
                raise ValueError("HISTORICAL_LAW_LEGISLATIVE_RECORD_NORMATIVE_OVERLAP")
            if record.source_id not in legislative:
                raise ValueError("HISTORICAL_LAW_LEGISLATIVE_RECORD_SOURCE_NOT_IN_RESULT")
        return self


class HistoricalLawValidationResult(BaseModel):
    """Fail-closed result for a historical-law resolution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.historical-law-validation/v1"] = (
        "alr-tw.historical-law-validation/v1"
    )
    provider_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    query_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    decision: PublicLawValidationDecision
    applicability_source_ids: list[str] = Field(default_factory=list, max_length=50)
    legislative_material_source_ids: list[str] = Field(default_factory=list, max_length=50)
    reason_codes: list[str] = Field(default_factory=list, max_length=64)
    semantic_entailment_performed: Literal[False] = False


def validate_historical_law_resolution(
    resolution: HistoricalLawResolution,
    *,
    server_metadata: PublicLawServerMetadata | None,
    server_source_ids: Collection[str] | None,
    now: datetime | None = None,
) -> HistoricalLawValidationResult:
    """Validate provider receipt and preserve normative/material separation."""

    public = validate_public_law_result(
        resolution.provider_result,
        server_metadata=server_metadata,
        server_source_ids=server_source_ids,
        now=now,
    )
    if public.decision is PublicLawValidationDecision.BLOCKED:
        return HistoricalLawValidationResult(
            provider_id=resolution.provider_id,
            query_id=resolution.query_id,
            decision=PublicLawValidationDecision.BLOCKED,
            reason_codes=list(public.reason_codes),
        )
    source_map = {source.source_id: source for source in resolution.provider_result.sources}
    normative = set(resolution.normative_source_ids)
    owned = set(server_source_ids or ())
    if any(
        source_map[source_id].source_role is PublicLawSourceRole.NORMATIVE_RULE
        for source_id in resolution.legislative_material_source_ids
        if source_id in source_map
    ):
        return HistoricalLawValidationResult(
            provider_id=resolution.provider_id,
            query_id=resolution.query_id,
            decision=PublicLawValidationDecision.BLOCKED,
            reason_codes=["HISTORICAL_LAW_LEGISLATIVE_ROLE_MISMATCH"],
        )
    if not normative:
        return HistoricalLawValidationResult(
            provider_id=resolution.provider_id,
            query_id=resolution.query_id,
            decision=PublicLawValidationDecision.QUALIFIED,
            legislative_material_source_ids=list(resolution.legislative_material_source_ids),
            reason_codes=list(
                dict.fromkeys(
                    ["HISTORICAL_LAW_NORMATIVE_SOURCE_MISSING", *public.reason_codes]
                )
            ),
        )
    if not normative.issubset(owned):
        return HistoricalLawValidationResult(
            provider_id=resolution.provider_id,
            query_id=resolution.query_id,
            decision=PublicLawValidationDecision.BLOCKED,
            reason_codes=["HISTORICAL_LAW_NORMATIVE_SOURCE_NOT_SERVER_OWNED"],
        )
    if any(
        source_map[source_id].source_role is not PublicLawSourceRole.NORMATIVE_RULE
        for source_id in normative
    ):
        return HistoricalLawValidationResult(
            provider_id=resolution.provider_id,
            query_id=resolution.query_id,
            decision=PublicLawValidationDecision.BLOCKED,
            reason_codes=["HISTORICAL_LAW_NORMATIVE_ROLE_MISMATCH"],
        )
    reason_codes = list(public.reason_codes)
    if public.decision is PublicLawValidationDecision.QUALIFIED:
        decision = PublicLawValidationDecision.QUALIFIED
        reason_codes.append("HISTORICAL_LAW_PROVIDER_SCOPE_QUALIFIED")
    else:
        decision = PublicLawValidationDecision.ACCEPTED
    return HistoricalLawValidationResult(
        provider_id=resolution.provider_id,
        query_id=resolution.query_id,
        decision=decision,
        applicability_source_ids=sorted(normative),
        legislative_material_source_ids=list(resolution.legislative_material_source_ids),
        reason_codes=list(dict.fromkeys(reason_codes)),
    )


__all__ = [
    "HistoricalLawQuery",
    "HistoricalLawRecordRole",
    "LegislativeHistoryRecord",
    "LegislativeMaterialRole",
    "LegislativeRecord",
    "LegislativeRole",
    "LegislativeStage",
    "HistoricalLawResolution",
    "HistoricalLawValidationResult",
    "validate_historical_law_resolution",
]
