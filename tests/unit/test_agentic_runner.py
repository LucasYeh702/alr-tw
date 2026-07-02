import json

from tw_legal_rag_mcp.agentic.runner import run_agentic_legal_research


def test_agentic_legal_research_traces_tool_decisions_and_final_gate():
    result = run_agentic_legal_research("民法第184條 押金")

    assert result["schema"] == "alr-tw.agentic-legal-rag/v1"
    assert result["plan"]["mode"] == "synthetic_agentic_rag"
    assert [step["tool"] for step in result["tool_trace"]] == [
        "query_understanding",
        "synthetic_retrieval",
        "citation_validation",
        "trust_gate",
        "answer_validation",
    ]
    assert [candidate["source_tier"] for candidate in result["retrieval_candidates"]] == [
        "official",
        "external_semantic_recall",
    ]
    assert [citation["source_id"] for citation in result["final_citations"]] == [
        "official-demo-law-184"
    ]
    assert result["trust_gate"]["safe_to_present"] is True
    assert result["answer_validation"]["safe_to_present"] is True


def test_agentic_legal_research_fails_closed_without_final_citation():
    result = run_agentic_legal_research("完全無關的查詢")

    assert result["retrieval_candidates"] == []
    assert result["final_citations"] == []
    assert result["trust_gate"]["safe_to_present"] is False
    assert "NO_FINAL_CITATION" in result["trust_gate"]["failure_reasons"]
    assert result["answer_validation"]["safe_to_present"] is False


def test_agentic_legal_research_does_not_return_raw_sensitive_query():
    synthetic_id = "A" + "123456789"
    result = run_agentic_legal_research(f"王小明 {synthetic_id} 想問房東不退押金")
    serialized = json.dumps(result, ensure_ascii=False)

    assert synthetic_id not in serialized
    assert "王小明" not in serialized
    assert "raw_query" not in result["query_understanding"]
    assert result["query"] == result["query_understanding"]["masked_query"]
