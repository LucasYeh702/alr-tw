from tw_legal_rag_mcp.verification.answer_validation import answer_with_validation


def test_answer_only_with_tlr_citation_is_not_safe_to_present():
    result = answer_with_validation(
        "候選結果如下。",
        [{"citation_id": "tlr-1", "source_id": "tlr-1", "source_tier": "external_semantic_recall"}],
    )

    assert result["validation_summary"]["safe_to_present"] is False
    assert result["validation_summary"]["has_final_citation"] is False


def test_answer_only_with_hf_staging_citation_is_not_safe_to_present():
    result = answer_with_validation(
        "候選結果如下。",
        [{"citation_id": "hf-1", "source_id": "hf-1", "source_tier": "staging"}],
    )

    assert result["validation_summary"]["safe_to_present"] is False


def test_answer_with_official_citation_is_safe_to_present():
    result = answer_with_validation(
        "官方來源可作引用。",
        [{"citation_id": "official-1", "source_id": "official-1", "source_tier": "official"}],
    )

    assert result["validation_summary"]["safe_to_present"] is True
    assert result["validation_summary"]["has_final_citation"] is True


def test_answer_with_mixed_official_and_tlr_keeps_tlr_non_final():
    result = answer_with_validation(
        "官方引用加候選召回。",
        [
            {"citation_id": "official-1", "source_id": "official-1", "source_tier": "official"},
            {"citation_id": "tlr-1", "source_id": "tlr-1", "source_tier": "external_semantic_recall"},
        ],
    )

    assert result["validation_summary"]["safe_to_present"] is True
    tlr = [item for item in result["citations"] if item["citation_id"] == "tlr-1"][0]
    assert tlr["citation_use"] == "allow_candidate_only"
