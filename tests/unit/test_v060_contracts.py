from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import subprocess
import sys

import pytest
from pydantic import ValidationError

from alr_tw.contracts.providers import (
    DataMode,
    LegalSourceProvider,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
)
from alr_tw.contracts.research import (
    CoverageState,
    PrivacyStatus,
    ResearchDepth,
    ResearchObligation,
    ResearchObligationKind,
    ResearchRun,
    ResearchState,
)
from alr_tw.contracts.sources import (
    EvidenceSpan,
    MaterialType,
    SourceRecord,
    SourceTier,
    TrustStatus,
)
from alr_tw.contracts.storage import StorageMode, StoragePolicy


def test_provider_capabilities_are_provider_neutral_and_immutable():
    capabilities = ProviderCapabilities(
        exact_lookup=True,
        keyword_search=False,
        semantic_recall=True,
        official_verification=False,
        historical_versions=False,
        current_status_check=False,
        external_query_transfer=True,
    )

    assert capabilities.semantic_recall is True
    assert capabilities.external_query_transfer is True
    with pytest.raises(ValidationError):
        capabilities.semantic_recall = False


def test_provider_protocol_captures_health_without_defining_search_semantics():
    class DemoProvider:
        provider_id = "synthetic"

        def capabilities(self) -> ProviderCapabilities:
            return ProviderCapabilities(
                exact_lookup=True,
                keyword_search=False,
                semantic_recall=False,
                official_verification=False,
                historical_versions=False,
                current_status_check=False,
                external_query_transfer=False,
            )

        async def health_check(self) -> ProviderHealth:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderHealthStatus.HEALTHY,
            )

    assert isinstance(DemoProvider(), LegalSourceProvider)


def test_research_run_rejects_naive_or_reverse_expiry_timestamps():
    now = datetime.now(UTC)
    obligation = ResearchObligation(kind=ResearchObligationKind.QUERY_UNDERSTANDING)
    common = {
        "run_id": "run_test",
        "query": "民法第184條",
        "created_at": now,
        "updated_at": now,
        "requested_mode": DataMode.OFFICIAL_ONLY,
        "effective_mode": DataMode.OFFICIAL_ONLY,
        "research_depth": ResearchDepth.STANDARD,
        "as_of_date": date(2026, 7, 19),
        "privacy_status": PrivacyStatus.NOT_REQUIRED,
        "state": ResearchState.CREATED,
        "obligations": [obligation],
        "coverage": CoverageState(),
    }

    with pytest.raises(ValidationError):
        ResearchRun(expires_at=now - timedelta(seconds=1), **common)

    with pytest.raises(ValidationError):
        ResearchRun(
            expires_at=(now + timedelta(hours=1)).replace(tzinfo=None),
            **common,
        )


def test_evidence_span_requires_server_owned_exact_text_hash():
    text = "行為人因故意或過失，不法侵害他人之權利者。"
    evidence = EvidenceSpan.from_exact_text(
        evidence_id="evidence_1",
        source_id="source_1",
        section_id="article-184",
        section_type="law_text",
        exact_text=text,
        eligible_for_claim_support=True,
    )

    assert evidence.text_hash.startswith("sha256:")
    assert evidence.verify_text(text) is True
    assert evidence.verify_text(f"{text}變造") is False


def test_source_tier_is_reexported_by_legacy_source_policy():
    from tw_legal_rag_mcp.verification.source_policy import SourceTier as LegacySourceTier

    assert LegacySourceTier is SourceTier
    assert SourceTier.EXTERNAL_SEMANTIC_RECALL.value == "external_semantic_recall"
    assert MaterialType.CONSTITUTIONAL.value == "constitutional"
    assert TrustStatus.EVIDENCE_ELIGIBLE.value == "evidence_eligible"


def test_provider_neutral_contracts_are_reexported_from_legacy_contract_module():
    from tw_legal_rag_mcp import contracts as legacy_contracts

    assert legacy_contracts.ProviderCapabilities is ProviderCapabilities
    assert legacy_contracts.ResearchRun is ResearchRun
    assert legacy_contracts.SourceTier is SourceTier


def test_external_recall_source_cannot_be_marked_evidence_eligible():
    now = datetime.now(UTC)
    digest = "sha256:" + ("a" * 64)

    with pytest.raises(ValidationError, match="external semantic recall"):
        SourceRecord(
            source_id="source_1",
            source_key="tlr:1",
            source_version_id="tlr:1:v1",
            material_type=MaterialType.JUDGMENT,
            provider_id="tlr",
            source_tier=SourceTier.EXTERNAL_SEMANTIC_RECALL,
            trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
            official_identifier="synthetic-identifier",
            citation="Synthetic candidate",
            fetched_at=now,
            verified_at=now,
            expires_at=now + timedelta(hours=1),
            content_hash=digest,
            normalized_content_hash=digest,
            normalized_text="Synthetic candidate text",
        )


def test_new_core_contracts_do_not_import_compatibility_namespace():
    script = (
        "import sys; import alr_tw.contracts, alr_tw.config; "
        "assert not any(name == 'tw_legal_rag_mcp' or "
        "name.startswith('tw_legal_rag_mcp.') for name in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_storage_policy_has_one_external_retention_value():
    policy = StoragePolicy(mode=StorageMode.TIMED, retention_seconds=24 * 60 * 60)

    assert policy.retention_seconds == 86400
    assert policy.cleanup_on_expiry is True

    with pytest.raises(ValidationError):
        StoragePolicy(mode=StorageMode.TIMED, retention_seconds=0)
