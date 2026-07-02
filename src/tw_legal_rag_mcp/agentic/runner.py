from __future__ import annotations

from typing import Any

from alr_tw.harness.trace_schema import (
    AgenticRunTrace,
    EvidenceRecord,
    ToolCallTrace,
    TrustGateTrace,
)
from alr_tw.harness.constants import FinalAction, ToolExecutionMode

from ..contracts import SyntheticOfficialAdapter, SyntheticRetriever, SourcePolicyCitationVerifier
from ..legal_nlp.privacy import mask_sensitive_text
from ..legal_nlp.query_understanding import understand_query
from ..verification.answer_validation import answer_with_validation
from ..verification.trust_gates import evaluate_trust_gate


def _trace_step(tool: str, decision: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"tool": tool, "decision": decision, "details": details}


def _public_understanding(understanding: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in understanding.items() if key != "raw_query"}


def _tool_call(tool_trace: dict[str, Any]) -> ToolCallTrace:
    return ToolCallTrace(
        tool_name=str(tool_trace["tool"]),
        execution_mode=ToolExecutionMode.HARNESS_RECORDED.value,
        output_summary={
            "decision": tool_trace["decision"],
            "synthetic": True,
            "trace_kind": "deterministic_harness_step",
            **dict(tool_trace["details"]),
        },
        status="success",
    )


def run_agentic_legal_research(query: str) -> dict[str, Any]:
    """Run a public-safe synthetic agentic RAG loop.

    The loop mirrors the production shape without loading production corpora,
    indexes, model settings, local paths, or private ranking parameters.
    """
    query = query.strip()
    if not query:
        raise ValueError("query is required")

    public_query = mask_sensitive_text(query, mask_names=True)
    tool_trace: list[dict[str, Any]] = []
    understanding = understand_query(public_query)
    safe_understanding = _public_understanding(understanding)
    tool_trace.append(
        _trace_step(
            "query_understanding",
            "parse_query_before_retrieval",
            {
                "intent": safe_understanding["intent"],
                "issue_tags": list(safe_understanding["issue_tags"]),
                "citation_count": len(safe_understanding["citations"]),
            },
        )
    )

    adapter_result = SyntheticOfficialAdapter().load()
    candidates = SyntheticRetriever().search(public_query, adapter_result)
    tool_trace.append(
        _trace_step(
            "synthetic_retrieval",
            "retrieve_candidates_from_synthetic_adapter",
            {
                "candidate_count": len(candidates),
                "source_tiers": [candidate.source_tier for candidate in candidates],
            },
        )
    )

    verifier = SourcePolicyCitationVerifier()
    verifications = [verifier.verify(candidate, require_final=True) for candidate in candidates]
    final_citations = [
        candidate.to_dict()
        for candidate, verification in zip(candidates, verifications, strict=True)
        if verification["citation_use"] == "allow_final"
    ]
    tool_trace.append(
        _trace_step(
            "citation_validation",
            "filter_final_citations",
            {
                "verified_count": len(verifications),
                "final_citation_count": len(final_citations),
                "candidate_only_count": sum(
                    1 for item in verifications if item["citation_use"] == "allow_candidate_only"
                ),
            },
        )
    )

    answer = "Synthetic answer guarded by official-grounded citation validation."
    coverage = {
        "has_laws": "present" if candidates else "absent",
        "has_judgments": "not_checked",
    }
    trust_gate = evaluate_trust_gate(answer=answer, citations=final_citations, coverage=coverage)
    tool_trace.append(
        _trace_step(
            "trust_gate",
            "decide_whether_answer_can_be_presented",
            {
                "safe_to_present": trust_gate["safe_to_present"],
                "failure_reasons": trust_gate["failure_reasons"],
            },
        )
    )

    wrapped_answer = answer_with_validation(answer, final_citations)
    tool_trace.append(
        _trace_step(
            "answer_validation",
            "wrap_answer_with_validation_summary",
            {
                "safe_to_present": wrapped_answer["validation_summary"]["safe_to_present"],
                "has_final_citation": wrapped_answer["validation_summary"]["has_final_citation"],
            },
        )
    )

    evidence = [
        EvidenceRecord(
            citation_id=str(verification["citation_id"]),
            source_id=candidate.source_id,
            source_tier=str(verification["source_tier"]),
            citation_use=str(verification["citation_use"]),
            title=candidate.title,
            snippet=candidate.snippet,
            official_url=verification.get("official_url"),
            validation_status=str(verification["status"]),
        )
        for candidate, verification in zip(candidates, verifications, strict=True)
    ]
    final_action = str(trust_gate["recommended_action"])
    decision_trace = [
        {
            "step": "citation_validation",
            "final_citation_count": len(final_citations),
            "candidate_count": len(candidates),
        },
        {
            "step": "trust_gate",
            "safe_to_present": bool(trust_gate["safe_to_present"]),
            "failure_reasons": list(trust_gate["failure_reasons"]),
            "final_action": final_action,
            "answer_present": final_action == FinalAction.ANSWER.value,
        },
    ]
    trace = AgenticRunTrace(
        query=str(safe_understanding["masked_query"]),
        normalized_query=str(safe_understanding["normalized_query"]),
        steps=[
            {"from": "query_understanding", "to": "synthetic_retrieval"},
            {"from": "synthetic_retrieval", "to": "citation_validation"},
            {"from": "citation_validation", "to": "trust_gate"},
            {"from": "trust_gate", "to": "answer_validation"},
        ],
        tool_calls=[_tool_call(step) for step in tool_trace],
        decision_trace=decision_trace,
        evidence=evidence,
        coverage=coverage,
        trust_gate=TrustGateTrace(
            safe_to_present=bool(trust_gate["safe_to_present"]),
            failure_reasons=list(trust_gate["failure_reasons"]),
            validation_summary=dict(wrapped_answer["validation_summary"]),
            recommended_action=final_action,  # type: ignore[arg-type]
        ),
        final_action=final_action,  # type: ignore[arg-type]
        answer=answer if final_action == "answer" else None,
    )
    return trace.model_dump()
