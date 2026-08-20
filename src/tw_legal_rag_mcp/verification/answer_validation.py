from __future__ import annotations

from typing import Any

from .citation_validator import (
    CitationStatus,
    is_final_citation,
    validate_untrusted_citation,
)
from .source_policy import CitationUse


def answer_with_validation(answer: str, citations: list[dict[str, Any]]) -> dict[str, Any]:
    validated = [
        validate_untrusted_citation(citation, require_final=True) for citation in citations
    ]

    has_final = any(is_final_citation(item) for item in validated)
    has_rejected = any(item["citation_use"] == CitationUse.REJECT.value for item in validated)
    has_unverifiable = any(item["status"] == CitationStatus.UNVERIFIABLE.value for item in validated)
    demo_only = bool(validated) and all(
        item["citation_use"] == CitationUse.DEMO_ONLY.value for item in validated
    )
    # This compatibility helper validates caller-authored source metadata only;
    # it performs no claim-support check and therefore cannot authorize legal
    # answer presentation. Use ResearchService.validate_legal_answer for that.
    safe_to_present = False
    human_review_required = (
        has_final and not has_rejected and not has_unverifiable and not demo_only
    )

    return {
        "schema_version": "alr-tw.answer_validation/v1",
        "answer": answer,
        "citations": validated,
        "validation_summary": {
            "has_final_citation": has_final,
            "has_rejected_citation": has_rejected,
            "has_unverifiable_citation": has_unverifiable,
            "demo_only": demo_only,
            "safe_to_present": safe_to_present,
            "human_review_required": human_review_required,
            "claim_support_level": "not_checked",
        },
        "claim_support_summary": {
            "level": "not_checked",
            "note": "Legacy metadata validation does not establish claim-level legal support.",
        },
        "validation_level": "source_verification",
    }
