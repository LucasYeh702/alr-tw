import pytest

from alr_tw.harness.trace_schema import EvidenceRecord
from alr_tw.verification.claim_support import SemanticGroundingSummary
from alr_tw.harness.orchestrator import _trust_gate_trace
from alr_tw.harness.orchestrator import run_agentic_demo


@pytest.mark.parametrize(
    ("scenario", "expected_action", "safe_to_present"),
    [
        ("pass_official_source", "answer", True),
        ("fail_candidate_only", "refuse", False),
        ("fail_synthetic_only", "refuse", False),
        ("fail_verified_cache_incomplete", "refuse", False),
        ("fail_no_final_citation", "refuse", False),
        ("fail_low_coverage", "refuse", False),
        ("pass_claim_supported", "answer", True),
        ("human_review_required_claim_support", "human_review_required", False),
        ("human_review_claim_unchecked", "human_review_required", False),
        ("fail_party_argument_as_court_view", "refuse", False),
        ("fail_overstated_case_specific_rule", "human_review_required", False),
        ("fail_unsupported_paraphrase", "refuse", False),
    ],
)
def test_agentic_demo_scenarios_have_expected_final_action(
    scenario, expected_action, safe_to_present
):
    trace = run_agentic_demo("民法第184條 押金", scenario=scenario)

    assert trace.final_action == expected_action
    assert trace.trust_gate.safe_to_present is safe_to_present
    if expected_action == "answer":
        assert any(item.citation_use == "allow_final" for item in trace.evidence)
    if expected_action == "refuse":
        assert trace.answer is None
    if expected_action == "human_review_required":
        assert trace.answer is None
        assert trace.human_review_notes


def test_trust_gate_refuses_critical_failure_even_when_human_review_required():
    trace = _trust_gate_trace(
        evidence=[
            EvidenceRecord(
                citation_id="official-demo",
                source_id="official-demo",
                source_tier="official",
                citation_use="allow_final",
                validation_status="exists",
            ),
            EvidenceRecord(
                citation_id="bad-cache",
                source_id="bad-cache",
                source_tier="verified_cache",
                citation_use="reject",
                validation_status="unverifiable",
            ),
        ],
        coverage={"has_laws": "present", "has_judgments": "not_checked"},
        semantic_summary=SemanticGroundingSummary(
            claim_count=1,
            unchecked_count=1,
        ),
    )

    assert trace.recommended_action == "refuse"


def test_agentic_demo_masks_sensitive_query_in_trace():
    synthetic_id = "A" + "123456789"
    trace = run_agentic_demo(f"王小明 {synthetic_id} 想問房東不退押金")
    serialized = trace.model_dump_json()

    assert synthetic_id not in serialized
    assert "王小明" not in serialized
    assert "[TW_ID]" in serialized
