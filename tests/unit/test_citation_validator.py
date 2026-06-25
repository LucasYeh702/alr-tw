from tw_legal_rag_mcp.verification.citation_validator import (
    CitationStatus,
    validate_citation,
)


def test_validate_citation_reports_exists_for_official_source():
    result = validate_citation(
        {
            "citation_id": "official-law-001",
            "source_id": "official-law-001",
            "source_tier": "official",
            "official_url": "https://example.test/official/law/001",
        }
    )

    assert result["status"] == CitationStatus.EXISTS
    assert result["citation_use"] == "allow_final"


def test_validate_citation_rejects_tlr_as_final_citation():
    result = validate_citation(
        {
            "citation_id": "tlr-candidate-001",
            "source_id": "tlr-candidate-001",
            "source_tier": "external_semantic_recall",
        },
        require_final=True,
    )

    assert result["status"] == CitationStatus.UNVERIFIABLE
    assert result["citation_use"] == "allow_candidate_only"
    assert "not allowed as final" in result["reason"]


def test_validate_citation_distinguishes_not_found_from_unverifiable():
    result = validate_citation({"citation_id": "", "source_tier": "unknown"})

    assert result["status"] == CitationStatus.NOT_FOUND
