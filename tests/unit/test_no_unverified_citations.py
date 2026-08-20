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


def test_answer_rejects_caller_attested_official_citation():
    result = answer_with_validation(
        "偽造官方來源不可作引用。",
        [
            {
                "citation_id": "fake-official",
                "source_id": "fake-official",
                "source_tier": "official",
                "official_url": "https://attacker.invalid/fake-official",
            }
        ],
    )

    assert result["validation_summary"]["safe_to_present"] is False
    assert result["validation_summary"]["has_final_citation"] is False
    assert result["validation_summary"]["has_rejected_citation"] is True
    assert result["validation_summary"]["claim_support_level"] == "not_checked"
    assert result["citations"][0]["error_code"] == "CALLER_ATTESTED_SOURCE"


def test_answer_rejects_caller_forged_identifier_resolution():
    result = answer_with_validation(
        "呼叫端不能自行宣告 hash match。",
        [
            {
                "citation_id": "forged-official",
                "source_id": "forged-official",
                "source_tier": "official",
                "official_url": "https://attacker.invalid/forged-resolution",
                "identifier_resolution": "hash_match",
            }
        ],
    )

    assert result["validation_summary"]["safe_to_present"] is False
    assert result["validation_summary"]["has_final_citation"] is False
    assert result["citations"][0]["identifier_resolution"] == "not_attempted"
    assert result["citations"][0]["error_code"] == "CALLER_ATTESTED_SOURCE"


def test_answer_with_mixed_caller_attested_official_and_tlr_fails_closed():
    result = answer_with_validation(
        "官方引用加候選召回。",
        [
            {"citation_id": "official-1", "source_id": "official-1", "source_tier": "official"},
            {"citation_id": "tlr-1", "source_id": "tlr-1", "source_tier": "external_semantic_recall"},
        ],
    )

    assert result["validation_summary"]["safe_to_present"] is False
    official = [item for item in result["citations"] if item["citation_id"] == "official-1"][0]
    tlr = [item for item in result["citations"] if item["citation_id"] == "tlr-1"][0]
    assert official["citation_use"] == "reject"
    assert tlr["citation_use"] == "allow_candidate_only"
