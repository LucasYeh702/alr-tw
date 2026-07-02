from __future__ import annotations

from .trace_schema import AgenticRunTrace


def _source_lines(trace: AgenticRunTrace, citation_use: str) -> list[str]:
    rows = [
        f"- `{item.citation_id}` ({item.source_tier}, {item.validation_status}): {item.title or ''}"
        for item in trace.evidence
        if item.citation_use == citation_use
    ]
    return rows or ["- None"]


def build_validation_report(trace: AgenticRunTrace) -> str:
    reasons = ", ".join(trace.trust_gate.failure_reasons) or "none"
    sections = [
        "# Legal Research Validation Report",
        "",
        "## 1. Query",
        trace.query,
        "",
        "## 2. Normalized Query",
        trace.normalized_query or "",
        "",
        "## 3. Tool Plan",
        "\n".join(f"- {call.tool_name}: {call.status}" for call in trace.tool_calls),
        "",
        "## 4. Retrieved Sources",
        "\n".join(
            f"- `{item.citation_id}` ({item.source_tier}, {item.citation_use})"
            for item in trace.evidence
        )
        or "- None",
        "",
        "## 5. Final Citations",
        "\n".join(_source_lines(trace, "allow_final")),
        "",
        "## 6. Candidate-only Sources",
        "\n".join(_source_lines(trace, "allow_candidate_only")),
        "",
        "## 7. Rejected / Unverifiable Sources",
        "\n".join(
            f"- `{item.citation_id}` ({item.citation_use}, {item.validation_status})"
            for item in trace.evidence
            if item.citation_use in {"reject", "demo_only"} or item.validation_status == "unverifiable"
        )
        or "- None",
        "",
        "## 8. Coverage",
        "\n".join(f"- {key}: {value}" for key, value in trace.coverage.items()),
        "",
        "## 9. Trust Gate Decision",
        f"- safe_to_present: {trace.trust_gate.safe_to_present}",
        f"- failure_reasons: {reasons}",
        "",
        "## 10. Final Action",
        trace.final_action,
        "",
        "## 11. Human Review Notes",
        "\n".join(f"- {note}" for note in trace.human_review_notes) or "- None",
    ]
    return "\n".join(sections) + "\n"

