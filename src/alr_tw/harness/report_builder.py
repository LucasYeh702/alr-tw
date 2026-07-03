from __future__ import annotations

import json

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
    semantic_failure_reasons = ", ".join(trace.semantic_failure_reasons) or "none"

    answer_claim_lines = [
        f"- `{claim.claim_id}` ({claim.claim_type}): {claim.claim_text}"
        for claim in trace.answer_claims
    ]
    if not answer_claim_lines:
        answer_claim_lines = ["- None"]

    claim_support_lines = []
    for item in trace.claim_support:
        supporting_segment_ids = [
            segment.segment_id for segment in item.supporting_segments
        ]
        if supporting_segment_ids:
            support_detail = ", ".join(supporting_segment_ids)
            risk_detail = "[" + ", ".join(item.risk_flags) + "]" if item.risk_flags else "[]"
            claim_support_lines.append(
                f"- `{item.claim_id}`: {item.support_status} ({risk_detail}) via `{support_detail}`"
            )
        else:
            claim_support_lines.append(f"- `{item.claim_id}`: {item.support_status}")
    if not claim_support_lines:
        claim_support_lines = ["- None"]

    grounding_summary = trace.semantic_grounding_summary
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
        "\n".join(
            "- "
            f"{call.tool_name}: {call.status}, "
            f"execution_mode={call.execution_mode}, "
            f"trace_kind={call.output_summary.get('trace_kind', 'unspecified')}"
            for call in trace.tool_calls
        ),
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
        "## 10. Decision Trace",
        "\n".join(
            f"- {json.dumps(decision, ensure_ascii=False, sort_keys=True)}"
            for decision in trace.decision_trace
        )
        or "- None",
        "",
        "## 11. Answer Claims",
        "\n".join(answer_claim_lines),
        "",
        "## 12. Claim Support Review",
        "\n".join(claim_support_lines),
        "",
        "## 13. Semantic Hallucination Risk",
        f"- semantic_safe_to_present: {grounding_summary.semantic_safe_to_present}",
        f"- supported_count: {grounding_summary.supported_count}",
        f"- unsupported_count: {grounding_summary.unsupported_count}",
        f"- overstated_count: {grounding_summary.overstated_count}",
        f"- role_error_count: {grounding_summary.role_error_count}",
        f"- needs_review_count: {grounding_summary.needs_review_count}",
        f"- failure_reasons: {semantic_failure_reasons}",
        "",
        "## 14. Final Action",
        trace.final_action,
        "",
        "## 15. Human Review Notes",
        "\n".join(f"- {note}" for note in trace.human_review_notes) or "- None",
    ]
    return "\n".join(sections) + "\n"
