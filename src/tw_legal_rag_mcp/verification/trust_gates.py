from __future__ import annotations

from typing import Any

from .answer_validation import answer_with_validation


LOW_TRUST_COVERAGE_STATES = {"absent", "low_confidence"}


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
        reasons.append("no_final_citation")
    if summary["has_rejected_citation"]:
        reasons.append("rejected_citation")
    if summary["has_unverifiable_citation"]:
        reasons.append("unverifiable_citation")

    for field, value in coverage.items():
        state = value.get("state") if isinstance(value, dict) else value
        if state in LOW_TRUST_COVERAGE_STATES and field in {"has_laws", "has_judgments"}:
            reasons.append(f"{field}_{state}")

    safe = bool(summary["safe_to_present"]) and not reasons
    return {
        "safe_to_present": safe,
        "failure_reasons": reasons,
        "validation_summary": summary,
    }
