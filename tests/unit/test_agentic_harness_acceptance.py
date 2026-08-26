from pathlib import Path

from alr_tw.harness.execution_graph import StepKind, graph_as_dict
from alr_tw.harness.orchestrator import run_agentic_demo
from tw_legal_rag_mcp.mcp_server.server import tool_definitions


def test_agentic_harness_release_acceptance_artifacts_exist():
    required_paths = [
        "docs/AGENTIC_HARNESS_ACCEPTANCE.md",
        "docs/ERROR_CODES.md",
        "docs/AGENTIC_WORKFLOW.md",
        "docs/TRUST_MODEL.md",
        "docs/TLR_CANDIDATE_MODE.md",
        "docs/TLR_CANDIDATE_MODE.zh-TW.md",
        "docs/AGENT_CLIENT_GUIDE.md",
        "docs/TOOL_CONTRACT.md",
        "docs/TRACE_SCHEMA.md",
        "docs/VALIDATION_REPORT.md",
        "docs/RELEASE_NOTES.md",
        "docs/RELEASE_AUDIT_PROCEDURE.md",
        "docs/DEPLOYMENT_STARTING_POINTS.md",
        "docs/PUBLIC_PRIVATE_BOUNDARY.md",
        "examples/agentic_runs/pass_official_source.json",
        "examples/reports/pass_official_source.md",
        "examples/identifier_backed_demo.py",
        "examples/external_agent_trace_demo.py",
    ]

    for path in required_paths:
        assert Path(path).exists(), path


def test_agentic_harness_0_4_scenarios_are_executable_and_classified():
    query = "民法第184條 押金"
    expected = {
        "pass_claim_supported": "answer",
        "fail_party_argument_as_court_view": "refuse",
        "fail_overstated_case_specific_rule": "human_review_required",
        "fail_unsupported_paraphrase": "refuse",
        "human_review_claim_unchecked": "human_review_required",
    }

    for scenario, expected_action in expected.items():
        trace = run_agentic_demo(query, scenario=scenario)
        assert trace.final_action == expected_action


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
        "begin_agentic_run",
        "finalize_agentic_run",
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

    assert "v0.10.1" in text
    assert "server-owned" in text
    assert "Coverage v2" in text
    assert "不可宣稱" in text or "不宣稱" in text
    assert "完整台灣法律資料庫" in text
    assert "production SLA" in text
    assert "semantic entailment" in text
    assert "research_sufficiency" in text


def test_v070_optional_external_integrations_are_documented_consistently():
    paths = [
        "README.md",
        "README.zh-TW.md",
        "README.en.md",
        "docs/INTEROPERABILITY_CONTRACT.md",
    ]
    required_link = "https://github.com/aa0101181514/tw-legal-rag"
    for path in paths:
        text = Path(path).read_text(encoding="utf-8")
        assert required_link in text, f"{path}: {required_link}"
        assert "optional" in text.lower() or "可選" in text, path

    interop_text = Path("docs/INTEROPERABILITY_CONTRACT.md").read_text(encoding="utf-8")
    assert "client_assisted" in interop_text
    assert "civil_substantive" in interop_text
    assert "validate_legal_analysis" in interop_text
