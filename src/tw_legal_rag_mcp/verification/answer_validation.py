from __future__ import annotations

from typing import Any

from .citation_validator import CitationStatus, is_final_citation, validate_citation
from .source_policy import CitationUse


def answer_with_validation(answer: str, citations: list[dict[str, Any]]) -> dict[str, Any]:
    validated = [validate_citation(citation, require_final=False) for citation in citations]

    has_final = any(is_final_citation(item) for item in validated)
    has_rejected = any(item["citation_use"] == CitationUse.REJECT.value for item in validated)
    has_unverifiable = any(item["status"] == CitationStatus.UNVERIFIABLE.value for item in validated)
    demo_only = bool(validated) and all(
        item["citation_use"] == CitationUse.DEMO_ONLY.value for item in validated
    )
    safe_to_present = has_final and not has_rejected and not has_unverifiable

    return {
        "answer": answer,
        "citations": validated,
        "validation_summary": {
            "has_final_citation": has_final,
            "has_rejected_citation": has_rejected,
            "has_unverifiable_citation": has_unverifiable,
            "demo_only": demo_only,
            "safe_to_present": safe_to_present,
        },
    }
