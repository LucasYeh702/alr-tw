from tw_legal_rag_mcp.verification.answer_validation import answer_with_validation


def test_answer_validation_summary_tracks_rejected_and_unverifiable_citations():
    result = answer_with_validation(
        "混合引用測試。",
        [
            {"citation_id": "official-1", "source_id": "official-1", "source_tier": "official"},
            {"citation_id": "unknown-1", "source_id": "unknown-1", "source_tier": "unknown"},
        ],
    )

    assert result["validation_summary"]["has_final_citation"] is True
    assert result["validation_summary"]["has_rejected_citation"] is True
    assert result["validation_summary"]["has_unverifiable_citation"] is True
    assert result["validation_summary"]["safe_to_present"] is False
