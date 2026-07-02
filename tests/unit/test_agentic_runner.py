import json

from tw_legal_rag_mcp.agentic.runner import run_agentic_legal_research


def test_agentic_legal_research_traces_tool_decisions_and_final_gate():
    result = run_agentic_legal_research("民法第184條 押金")

    assert result["schema_version"] == "alr-tw.agentic_trace/v1"
    assert [step["tool_name"] for step in result["tool_calls"]] == [
        "query_understanding",
        "synthetic_retrieval",
        "citation_validation",
        "trust_gate",
        "answer_validation",
    ]
    assert [item["source_tier"] for item in result["evidence"]] == [
        "official",
        "external_semantic_recall",
    ]
    assert [item["source_id"] for item in result["evidence"] if item["citation_use"] == "allow_final"] == [
        "official-demo-law-184"
    ]
    assert result["trust_gate"]["safe_to_present"] is True
    assert result["final_action"] == "answer"


def test_agentic_legal_research_fails_closed_without_final_citation():
    result = run_agentic_legal_research("完全無關的查詢")

    assert result["evidence"] == []
    assert result["trust_gate"]["safe_to_present"] is False
    assert "NO_FINAL_CITATION" in result["trust_gate"]["failure_reasons"]
    assert result["final_action"] == "refuse"


def test_agentic_legal_research_does_not_return_raw_sensitive_query():
    synthetic_id = "A" + "123456789"
    result = run_agentic_legal_research(f"王小明 {synthetic_id} 想問房東不退押金")
    serialized = json.dumps(result, ensure_ascii=False)

    assert synthetic_id not in serialized
    assert "王小明" not in serialized
    assert result["query"] == "[NAME] [TW_ID] 想問房東不退押金"
