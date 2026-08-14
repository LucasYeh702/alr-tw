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
    as_of_date: date
    bounded_scope: str = Field(min_length=1, max_length=500)
    include_legislative_history: bool = True
    max_results: int = Field(default=20, ge=1, le=50)

    @model_validator(mode="after")
    def validate_query(self) -> HistoricalLawQuery:
        if self.law_identifier is None and self.law_name is None:
            raise ValueError("HISTORICAL_LAW_IDENTIFIER_OR_NAME_REQUIRED")
        if not self.bounded_scope.strip():
            raise ValueError("HISTORICAL_LAW_BOUNDED_SCOPE_REQUIRED")
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
    provider_result: PublicLawProviderResult
    normative_source_ids: list[str] = Field(default_factory=list, max_length=50)
    legislative_material_source_ids: list[str] = Field(default_factory=list, max_length=50)
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
    "HistoricalLawResolution",
    "HistoricalLawValidationResult",
    "validate_historical_law_resolution",
]
