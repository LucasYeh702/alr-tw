from pathlib import Path

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

