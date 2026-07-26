from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from alr_tw.contracts.legal_context import (
    AuthorityAssessment,
    AuthorityLevel,
    AuthorityStatus,
    LegalValidityAssessment,
    LegalValidityStatus,
    SourceLegalContext,
    TemporalApplicabilityStatus,
    TemporalAssessment,
)
from alr_tw.contracts.sources import (
    EvidenceSpan,
    MaterialType,
    SourceRecord,
    SourceTier,
    TrustStatus,
)
from alr_tw.providers.synthetic import SyntheticLegalContextProvider


def _source(source_tier: SourceTier) -> SourceRecord:
    now = datetime.now(UTC)
    text = "合成法規內容"
    digest = EvidenceSpan.hash_text(text)
    return SourceRecord(
        source_id="source-demo",
        source_key="law:demo",
        source_version_id="law:demo:v1",
        material_type=MaterialType.LAW,
        provider_id="synthetic-source",
        source_tier=source_tier,
        trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
        official_identifier="DEMO0001",
        official_url="https://example.test/law/demo",
        citation="示範法第1條",
        fetched_at=now,
        verified_at=now,
        expires_at=now + timedelta(hours=24),
        content_hash=digest,
        normalized_content_hash=digest,
        normalized_text=text,
        metadata={"synthetic_fixture": True},
    )


def test_complete_legal_context_cannot_hide_unknown_status():
    now = datetime.now(UTC)
    with pytest.raises(ValidationError, match="unresolved states"):
        SourceLegalContext(
            source_id="source-demo",
            provider_id="provider-demo",
            assessed_at=now,
            temporal=TemporalAssessment(
                as_of_date=date.today(),
                status=TemporalApplicabilityStatus.APPLICABLE,
            ),
            authority=AuthorityAssessment(
                level=AuthorityLevel.STATUTE,
                status=AuthorityStatus.UNKNOWN,
            ),
            validity=LegalValidityAssessment(status=LegalValidityStatus.VALID),
            coverage_complete=True,
        )


def test_synthetic_provider_is_complete_only_for_allowlisted_fixtures():
    provider = SyntheticLegalContextProvider({"source-demo"})
    unconfigured = SyntheticLegalContextProvider()
    now = datetime.now(UTC)

    allowlisted = provider.assess(
        [_source(SourceTier.OFFICIAL)],
        as_of_date=date.today(),
        assessed_at=now,
    )
    not_allowlisted = unconfigured.assess(
        [_source(SourceTier.OFFICIAL)],
        as_of_date=date.today(),
        assessed_at=now,
    )

    assert allowlisted.status.value == "complete"
    assert allowlisted.records[0].authority.status is AuthorityStatus.BINDING
    assert allowlisted.records[0].validity.status is LegalValidityStatus.VALID
    assert not_allowlisted.status.value == "partial"
    assert not_allowlisted.records[0].coverage_complete is False
    assert not_allowlisted.records[0].validity.status is LegalValidityStatus.UNKNOWN
