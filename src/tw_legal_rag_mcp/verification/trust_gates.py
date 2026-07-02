from __future__ import annotations

from typing import Any

from .answer_validation import answer_with_validation


LOW_TRUST_COVERAGE_STATES = {"absent", "low_confidence"}
NO_FINAL_CITATION = "NO_FINAL_CITATION"
REJECTED_CITATION = "REJECTED_CITATION"
UNVERIFIABLE_CITATION = "UNVERIFIABLE_CITATION"
LAWS_COVERAGE_LOW = "LAWS_COVERAGE_LOW"
JUDGMENTS_COVERAGE_LOW = "JUDGMENTS_COVERAGE_LOW"


def evaluate_trust_gate(
    *,
    answer: str,
    citations: list[dict[str, Any]],
    coverage: dict[str, str | dict[str, object]],
) -> dict[str, object]:
    wrapped = answer_with_validation(answer, citations)
    summary = wrapped["validation_summary"]
    reasons: list[str] = []

    if not summary["has_final_citation"]:
        reasons.append(NO_FINAL_CITATION)
    if summary["has_rejected_citation"]:
        reasons.append(REJECTED_CITATION)
    if summary["has_unverifiable_citation"]:
        reasons.append(UNVERIFIABLE_CITATION)

    for field, value in coverage.items():
        state = value.get("state") if isinstance(value, dict) else value
        if state in LOW_TRUST_COVERAGE_STATES and field in {"has_laws", "has_judgments"}:
            reasons.append(LAWS_COVERAGE_LOW if field == "has_laws" else JUDGMENTS_COVERAGE_LOW)

    safe = bool(summary["safe_to_present"]) and not reasons
    return {
        "schema_version": "alr-tw.trust_gate/v1",
        "safe_to_present": safe,
        "failure_reasons": reasons,
        "validation_summary": summary,
        "recommended_action": "answer" if safe else "refuse",
    }
