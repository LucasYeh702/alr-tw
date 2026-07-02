from __future__ import annotations

from typing import Any

from ..contracts import SyntheticOfficialAdapter, SyntheticRetriever, SourcePolicyCitationVerifier
from ..legal_nlp.privacy import mask_sensitive_text
from ..legal_nlp.query_understanding import understand_query
from ..verification.answer_validation import answer_with_validation
from ..verification.trust_gates import evaluate_trust_gate

AGENTIC_LEGAL_RAG_SCHEMA = "alr-tw.agentic-legal-rag/v1"


def _trace_step(tool: str, decision: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"tool": tool, "decision": decision, "details": details}


def _public_understanding(understanding: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in understanding.items() if key != "raw_query"}


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

    return {
        "schema": AGENTIC_LEGAL_RAG_SCHEMA,
        "plan": {
            "mode": "synthetic_agentic_rag",
            "policy": "retrieve_candidates_validate_citations_fail_closed",
            "data_boundary": "synthetic_demo_only",
        },
        "query": safe_understanding["masked_query"],
        "query_understanding": safe_understanding,
        "tool_trace": tool_trace,
        "source_manifest": adapter_result.manifest.to_dict(),
        "retrieval_candidates": [candidate.to_dict() for candidate in candidates],
        "citation_verifications": verifications,
        "final_citations": final_citations,
        "trust_gate": trust_gate,
        "answer_validation": wrapped_answer["validation_summary"],
    }
