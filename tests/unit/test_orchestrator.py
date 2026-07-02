import pytest

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
        ("human_review_required_claim_support", "human_review_required", False),
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
        assert trace.answer
        assert trace.human_review_notes


def test_agentic_demo_masks_sensitive_query_in_trace():
    trace = run_agentic_demo("王小明 A123456789 想問房東不退押金")
    serialized = trace.model_dump_json()

    assert "A123456789" not in serialized
    assert "王小明" not in serialized
    assert "[TW_ID]" in serialized

