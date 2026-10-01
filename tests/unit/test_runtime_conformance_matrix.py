import pytest
from alr_tw.contracts.provider_conformance import (
    ProviderConformanceRequest,
    ProviderRole,
    validate_provider_conformance,
)
from alr_tw.contracts.providers import ProviderResult, ProviderResultStatus


@pytest.mark.parametrize("provider", ["official-pilot", "compatible-candidate", "tlr-pilot"])
@pytest.mark.parametrize(
    "scenario",
    ["timeout", "rate_limit", "partial", "unknown_year", "malformed_identity", "official_failure"],
)
def test_replacement_failure_never_authorizes_absence_or_answer(provider, scenario):
    status = ProviderResultStatus.PARTIAL if scenario == "partial" else ProviderResultStatus.ERROR
    result = ProviderResult(
        provider_id=provider,
        status=status,
        coverage_complete=False,
        metadata={"failure_scenario": scenario},
    )
    request = ProviderConformanceRequest(
        provider_id=provider,
        role=ProviderRole.PROVIDER_NEUTRAL,
        bounded_scope="synthetic-fixed-scope",
        require_snapshot_receipt=True,
    )
    decision = validate_provider_conformance(
        result,
        request=request,
        server_source_ids=[],
        server_evidence_ids=[],
        server_sources={},
        server_evidence={},
        receipts=[],
        server_receipts=[],
    )
    assert not decision.ordinary_eligible
    assert not decision.absence_claim_allowed
    assert decision.eligible_source_ids == []
