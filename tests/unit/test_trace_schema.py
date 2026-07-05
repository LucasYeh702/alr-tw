from pathlib import Path

from alr_tw.harness.constants import TrustFailureReason
from alr_tw.harness.orchestrator import run_agentic_demo
from alr_tw.harness.trace_schema import AgenticRunTrace


def test_agentic_run_trace_schema_validates_demo_output():
    trace = AgenticRunTrace.model_validate(
        {
            "query": "民法第184條 押金",
            "normalized_query": "民法第184條 擔保金",
            "trust_gate": {"safe_to_present": False},
            "final_action": "refuse",
        }
    )

    assert trace.schema_version == "alr-tw.agentic_trace/v1"
    assert trace.trust_gate.failure_reasons == []


def test_example_traces_validate_against_schema():
    paths = sorted(Path("examples/agentic_runs").glob("*.json"))

    assert len(paths) >= 5
    for path in paths:
        AgenticRunTrace.model_validate_json(path.read_text(encoding="utf-8"))


def test_demo_trace_marks_harness_recorded_tool_calls_and_decisions():
    trace = run_agentic_demo("民法第184條 押金", scenario="pass_official_source")

    assert trace.tool_calls
    assert {tool_call.execution_mode for tool_call in trace.tool_calls} == {"harness_recorded"}
    assert "trace_kind" not in trace.model_dump()
    assert trace.decision_trace[-1]["final_action"] == "answer"
    assert trace.decision_trace[-1]["safe_to_present"] is True


def test_external_trace_schema_accepts_actual_tool_and_externally_driven_marker():
    trace = AgenticRunTrace.model_validate(
        {
            "schema_version": "alr-tw.agentic_trace/v1",
            "trace_kind": "externally_driven",
            "query": "民法第184條 押金",
            "tool_calls": [
                {
                    "tool_name": "validate_citation",
                    "execution_mode": "actual_tool",
                    "input_summary": {"citation_id": "official-demo-law-184"},
                    "output_summary": {"citation_use": "allow_final"},
                    "status": "success",
                }
            ],
            "trust_gate": {
                "safe_to_present": True,
                "recommended_action": "answer",
            },
            "final_action": "answer",
            "answer": "Synthetic answer.",
        }
    )

    dumped = trace.model_dump()
    assert dumped["trace_kind"] == "externally_driven"
    assert dumped["tool_calls"][0]["execution_mode"] == "actual_tool"


def test_non_answer_example_traces_do_not_include_answer_body():
    for scenario in [
        "fail_candidate_only",
        "fail_synthetic_only",
        "fail_verified_cache_incomplete",
        "fail_no_final_citation",
        "fail_low_coverage",
        "human_review_required_claim_support",
    ]:
        trace = run_agentic_demo("民法第184條 押金", scenario=scenario)

        assert trace.final_action != "answer"
        assert trace.answer is None


def test_example_failure_reasons_are_known_constants_and_documented():
    allowed = {reason.value for reason in TrustFailureReason}
    docs_text = Path("docs/ERROR_CODES.md").read_text(encoding="utf-8")

    for reason in allowed:
        assert f"`{reason}`" in docs_text

    for path in sorted(Path("examples/agentic_runs").glob("*.json")):
        trace = AgenticRunTrace.model_validate_json(path.read_text(encoding="utf-8"))
        assert set(trace.trust_gate.failure_reasons).issubset(allowed)
