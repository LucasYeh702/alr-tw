from tw_legal_rag_mcp.contracts import run_synthetic_contract_pipeline
from tw_legal_rag_mcp.verification.trust_gates import evaluate_trust_gate


def test_synthetic_contract_pipeline_exposes_production_shape_without_parameters():
    result = run_synthetic_contract_pipeline("民法第184條 押金")

    assert result["schema"] == "tw-legal-rag-mcp-reference.synthetic-contract-pipeline/v1"
    assert result["source_manifest"]["schema"] == "tw-legal-rag-mcp-reference.source-manifest/v1"
    assert result["source_manifest"]["provider"] == "Synthetic Official Source"
    assert result["adapter_result"]["schema"] == "tw-legal-rag-mcp-reference.adapter-result/v1"
    assert result["adapter_result"]["status"] == "loaded"

    candidates = result["retrieval_candidates"]
    assert [candidate["source_tier"] for candidate in candidates] == [
        "official",
        "external_semantic_recall",
    ]
    assert all(candidate["schema"] == "tw-legal-rag-mcp-reference.retrieval-candidate/v1" for candidate in candidates)

    verifications = result["citation_verifications"]
    assert verifications[0]["citation_use"] == "allow_final"
    assert verifications[1]["citation_use"] == "allow_candidate_only"
    assert verifications[1]["status"] == "unverifiable"

    assert [citation["source_id"] for citation in result["final_citations"]] == ["official-demo-law-184"]
    assert result["trust_gate"]["safe_to_present"] is True
    assert result["answer_validation"]["has_final_citation"] is True
    assert result["answer_validation"]["safe_to_present"] is True


def test_candidate_only_contract_results_fail_closed_when_no_final_citation():
    result = run_synthetic_contract_pipeline("民法第184條 押金")
    candidate_only_citations = [
        candidate
        for candidate in result["retrieval_candidates"]
        if candidate["source_tier"] == "external_semantic_recall"
    ]

    gate = evaluate_trust_gate(
        answer="Synthetic answer must not be presented with candidate-only citations.",
        citations=candidate_only_citations,
        coverage={"has_laws": "present", "has_judgments": "not_checked"},
    )

    assert candidate_only_citations
    assert gate["safe_to_present"] is False
    assert "no_final_citation" in gate["failure_reasons"]
    assert gate["validation_summary"]["has_final_citation"] is False


def test_synthetic_contract_pipeline_does_not_expose_production_parameters():
    result_text = repr(run_synthetic_contract_pipeline("民法第184條 押金")).lower()

    assert "chunk_size" not in result_text
    assert "hnsw" not in result_text
    assert "ranking_weight" not in result_text
    assert "embedding_model" not in result_text