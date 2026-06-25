from tw_legal_rag_mcp.retrieval.search_coordinator import demo_search
from tw_legal_rag_mcp.verification.answer_validation import answer_with_validation


def test_demo_search_uses_synthetic_sources_and_marks_answer_demo_only():
    results = demo_search("房東不退押金怎麼辦？")

    assert results["normalized_query"].startswith("出租人")
    assert results["coverage"]["has_laws"] == "present"
    assert results["results"]
    assert all(item["source_tier"] == "synthetic" for item in results["results"])

    wrapped = answer_with_validation("以下為合成資料展示。", results["results"])
    assert wrapped["validation_summary"]["safe_to_present"] is False
    assert wrapped["validation_summary"]["demo_only"] is True
