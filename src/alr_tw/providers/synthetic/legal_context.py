"""Synthetic-only legal-context provider with no production corpus dependency."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import date, datetime

from alr_tw.contracts.legal_context import (
    AuthorityAssessment,
    AuthorityLevel,
    AuthorityStatus,
    LegalContextResult,
    LegalContextResultStatus,
    LegalValidityAssessment,
    LegalValidityStatus,
    SourceLegalContext,
    TemporalApplicabilityStatus,
    TemporalAssessment,
)
from alr_tw.contracts.sources import MaterialType, SourceRecord, TrustStatus


class SyntheticLegalContextProvider:
    """Assess only explicitly allowlisted, server-owned fixtures as complete."""

    provider_id = "synthetic-legal-context"

    def __init__(self, fixture_source_ids: Collection[str] = ()):
        self._fixture_source_ids = frozenset(fixture_source_ids)

    def assess(
        self,
        sources: Sequence[SourceRecord],
        *,
        as_of_date: date,
        assessed_at: datetime,
    ) -> LegalContextResult:
        records: list[SourceLegalContext] = []
        incomplete = False
        for source in sources:
            eligible = (
                source.source_id in self._fixture_source_ids
                and source.provider_id.startswith("synthetic-")
                and source.metadata.get("synthetic_fixture") is True
                and source.trust_status is TrustStatus.EVIDENCE_ELIGIBLE
            )
            if eligible:
                authority_level, authority_status = self._authority(source.material_type)
                temporal_status = TemporalApplicabilityStatus.APPLICABLE
                validity_status = LegalValidityStatus.VALID
                limitations = ["synthetic_fixture_only"]
            else:
                incomplete = True
                authority_level = AuthorityLevel.OTHER
                authority_status = AuthorityStatus.UNKNOWN
                temporal_status = TemporalApplicabilityStatus.INDETERMINATE
                validity_status = LegalValidityStatus.UNKNOWN
                limitations = ["live_legal_context_provider_required"]
            records.append(
                SourceLegalContext(
                    source_id=source.source_id,
                    provider_id=self.provider_id,
                    assessed_at=assessed_at,
                    temporal=TemporalAssessment(
                        as_of_date=as_of_date,
                        status=temporal_status,
                    ),
                    authority=AuthorityAssessment(
                        level=authority_level,
                        status=authority_status,
                    ),
                    validity=LegalValidityAssessment(status=validity_status),
                    coverage_complete=eligible,
                    limitations=limitations,
                )
            )
        return LegalContextResult(
            provider_id=self.provider_id,
            status=(
                LegalContextResultStatus.PARTIAL
                if incomplete
                else LegalContextResultStatus.COMPLETE
            ),
            records=records,
            limitations=[
                "synthetic provider validates contracts only; it is not production legal data"
            ],
        )

    @staticmethod
    def _authority(material_type: MaterialType) -> tuple[AuthorityLevel, AuthorityStatus]:
        if material_type is MaterialType.LAW:
            return AuthorityLevel.STATUTE, AuthorityStatus.BINDING
        if material_type is MaterialType.CONSTITUTIONAL:
            return AuthorityLevel.CONSTITUTIONAL_COURT, AuthorityStatus.BINDING
        if material_type is MaterialType.JUDGMENT:
            return AuthorityLevel.JUDGMENT, AuthorityStatus.PERSUASIVE
        return AuthorityLevel.OTHER, AuthorityStatus.UNKNOWN
