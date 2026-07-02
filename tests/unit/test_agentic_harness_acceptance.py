from pathlib import Path

from alr_tw.harness.execution_graph import StepKind, graph_as_dict
from alr_tw.harness.orchestrator import run_agentic_demo
from tw_legal_rag_mcp.mcp_server.server import tool_definitions


def test_agentic_harness_release_acceptance_artifacts_exist():
    required_paths = [
        "docs/AGENTIC_HARNESS_ACCEPTANCE.md",
        "docs/AGENTIC_WORKFLOW.md",
        "docs/TRUST_MODEL.md",
        "docs/TOOL_CONTRACT.md",
        "docs/TRACE_SCHEMA.md",
        "docs/VALIDATION_REPORT.md",
        "docs/PUBLIC_PRIVATE_BOUNDARY.md",
        "examples/agentic_runs/pass_official_source.json",
        "examples/reports/pass_official_source.md",
    ]

    for path in required_paths:
        assert Path(path).exists(), path


def test_agentic_harness_name_is_backed_by_graph_tools_and_scenarios():
    graph = graph_as_dict()
    tool_names = {tool["name"] for tool in tool_definitions()}

    assert graph["steps"] == [step.value for step in StepKind]
    assert {
        "agentic_legal_research",
        "run_agentic_demo",
        "build_validation_report",
        "get_trust_model",
        "validate_citation",
    }.issubset(tool_names)

    pass_trace = run_agentic_demo("民法第184條 押金", scenario="pass_official_source")
    fail_trace = run_agentic_demo("民法第184條 押金", scenario="fail_candidate_only")
    review_trace = run_agentic_demo(
        "民法第184條 押金",
        scenario="human_review_required_claim_support",
    )

    assert pass_trace.final_action == "answer"
    assert fail_trace.final_action == "refuse"
    assert review_trace.final_action == "human_review_required"


def test_acceptance_doc_states_current_claim_boundary():
    text = Path("docs/AGENTIC_HARNESS_ACCEPTANCE.md").read_text(encoding="utf-8")

    assert "bounded agentic legal RAG harness" in text
    assert "Not Claimed" in text
    assert "unrestricted autonomous legal agent" in text
    assert "production legal research agent" in text
