from __future__ import annotations

import json
from typing import Any

from tw_legal_rag_mcp.legal_nlp.privacy import mask_sensitive_text
from tw_legal_rag_mcp.legal_nlp.query_normalizer import normalize_query
from tw_legal_rag_mcp.verification.citation_validator import validate_citation

from .constants import FinalAction, ToolExecutionMode, TrustFailureReason
from .execution_graph import StepKind, graph_as_dict
from .trace_schema import AgenticRunTrace, EvidenceRecord, ToolCallTrace, TrustGateTrace

SCENARIOS = {
    "auto",
    "pass_official_source",
    "fail_candidate_only",
    "fail_synthetic_only",
    "fail_verified_cache_incomplete",
    "fail_no_final_citation",
    "fail_low_coverage",
    "human_review_required_claim_support",
}


def _scenario_records(scenario: str) -> list[dict[str, Any]]:
    if scenario in {"auto", "pass_official_source", "fail_low_coverage", "human_review_required_claim_support"}:
        return [
            {
                "citation_id": "official-demo-law-184",
                "source_id": "official-demo-law-184",
                "source_tier": "official",
                "title": "Synthetic Civil Code Article 184",
                "snippet": "Synthetic official-grounded fixture for tort and lease-deposit discussion.",
                "official_url": "https://example.test/synthetic-official/civil-law-demo#article-184",
            }
        ]
    if scenario == "fail_candidate_only":
        return [
            {
                "citation_id": "tlr-candidate-demo-001",
                "source_id": "tlr-candidate-demo-001",
                "source_tier": "external_semantic_recall",
                "title": "Synthetic TLR Candidate",
                "snippet": "Synthetic candidate-only judgment lead.",
            }
        ]
    if scenario == "fail_synthetic_only":
        return [
            {
                "citation_id": "synthetic-demo-001",
                "source_id": "synthetic-demo-001",
                "source_tier": "synthetic",
                "title": "Synthetic Demo Source",
                "snippet": "Synthetic source must not become final legal authority.",
            }
        ]
    if scenario == "fail_verified_cache_incomplete":
        return [
            {
                "citation_id": "cache-demo-001",
                "source_id": "cache-demo-001",
                "source_tier": "verified_cache",
                "title": "Incomplete Verified Cache Fixture",
                "snippet": "Missing official hash and verified_at metadata.",
                "official_url": "https://example.test/cache/demo",
            }
        ]
    return []


def _coverage_for(scenario: str) -> dict[str, str]:
    if scenario == "fail_low_coverage":
        return {"has_laws": "low_confidence", "has_judgments": "not_checked"}
    return {"has_laws": "present", "has_judgments": "not_checked"}


def _evidence(records: list[dict[str, Any]]) -> list[EvidenceRecord]:
    evidence: list[EvidenceRecord] = []
    for record in records:
        validation = validate_citation(record, require_final=True)
        evidence.append(
            EvidenceRecord(
                citation_id=str(validation["citation_id"]),
                source_id=str(record.get("source_id") or validation["citation_id"]),
                source_tier=str(validation["source_tier"]),
                citation_use=str(validation["citation_use"]),
                title=record.get("title"),
                snippet=record.get("snippet"),
                official_url=validation.get("official_url"),
                validation_status=str(validation["status"]),
            )
        )
    return evidence


def _trust_gate_trace(
    *,
    evidence: list[EvidenceRecord],
    coverage: dict[str, str],
    human_review_required: bool,
) -> TrustGateTrace:
    final_count = sum(1 for item in evidence if item.citation_use == "allow_final")
    rejected_count = sum(1 for item in evidence if item.citation_use in {"reject", "demo_only"})
    unverifiable_count = sum(1 for item in evidence if item.validation_status == "unverifiable")
    reasons: list[str] = []

    if final_count == 0:
        reasons.append(TrustFailureReason.NO_FINAL_CITATION.value)
    if rejected_count:
        reasons.append(TrustFailureReason.REJECTED_CITATION.value)
    if unverifiable_count:
        reasons.append(TrustFailureReason.UNVERIFIABLE_CITATION.value)
    if coverage.get("has_laws") in {"absent", "low_confidence"}:
        reasons.append(TrustFailureReason.LAWS_COVERAGE_LOW.value)
    if coverage.get("has_judgments") in {"absent", "low_confidence"}:
        reasons.append(TrustFailureReason.JUDGMENTS_COVERAGE_LOW.value)
    if human_review_required:
        reasons.append(TrustFailureReason.CLAIM_SUPPORT_NOT_CHECKED.value)
        reasons.append(TrustFailureReason.HUMAN_REVIEW_REQUIRED.value)

    critical_reasons = {
        TrustFailureReason.REJECTED_CITATION.value,
        TrustFailureReason.UNVERIFIABLE_CITATION.value,
        TrustFailureReason.LAWS_COVERAGE_LOW.value,
        TrustFailureReason.JUDGMENTS_COVERAGE_LOW.value,
    }
    has_critical_failure = any(reason in critical_reasons for reason in reasons)
    safe = final_count > 0 and not reasons
    if safe:
        action = FinalAction.ANSWER.value
    elif human_review_required and final_count > 0 and not has_critical_failure:
        action = FinalAction.HUMAN_REVIEW_REQUIRED.value
    else:
        action = FinalAction.REFUSE.value

    return TrustGateTrace(
        safe_to_present=safe,
        failure_reasons=reasons,
        validation_summary={
            "has_final_citation": final_count > 0,
            "has_rejected_citation": rejected_count > 0,
            "has_unverifiable_citation": unverifiable_count > 0,
            "safe_to_present": safe,
            "human_review_required": human_review_required,
        },
        recommended_action=action,
    )


def run_agentic_demo(
    query: str,
    *,
    scenario: str = "auto",
    require_final: bool = True,
) -> AgenticRunTrace:
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario: {scenario}")
    public_query = mask_sensitive_text(query.strip(), mask_names=True)
    if not public_query:
        raise ValueError("query is required")

    normalized_query = normalize_query(public_query)
    records = _scenario_records(scenario)
    coverage = _coverage_for(scenario)
    evidence = _evidence(records)
    human_review = scenario == "human_review_required_claim_support"
    trust_gate = _trust_gate_trace(
        evidence=evidence,
        coverage=coverage,
        human_review_required=human_review,
    )
    answer = (
        "Synthetic answer grounded by final citation."
        if trust_gate.recommended_action == FinalAction.ANSWER.value
        else None
    )
    notes = ["Claim support has not been checked; human legal review is required."] if human_review else []
    final_citation_count = sum(1 for item in evidence if item.citation_use == "allow_final")

    return AgenticRunTrace(
        query=public_query,
        normalized_query=normalized_query,
        steps=[
            {"from": source, "to": target}
            for source, target in graph_as_dict()["transitions"]
        ],
        tool_calls=[
            ToolCallTrace(
                tool_name=step.value,
                execution_mode=ToolExecutionMode.HARNESS_RECORDED.value,
                input_summary={"query": public_query} if step == StepKind.QUERY_UNDERSTANDING else {},
                output_summary=(
                    {
                        "scenario": scenario,
                        "synthetic": True,
                        "trace_kind": "deterministic_harness_step",
                    }
                    if step == StepKind.FINAL_DECISION
                    else {"synthetic": True, "trace_kind": "deterministic_harness_step"}
                ),
                status="success",
            )
            for step in StepKind
        ],
        decision_trace=[
            {
                "step": "citation_validation",
                "final_citation_count": final_citation_count,
                "candidate_count": len(evidence),
            },
            {
                "step": "trust_gate",
                "safe_to_present": trust_gate.safe_to_present,
                "failure_reasons": list(trust_gate.failure_reasons),
                "final_action": trust_gate.recommended_action,
                "answer_present": answer is not None,
            },
        ],
        evidence=evidence,
        coverage=coverage,
        trust_gate=trust_gate,
        final_action=trust_gate.recommended_action,
        answer=answer,
        human_review_notes=notes,
    )


def main() -> int:
    print(json.dumps(run_agentic_demo("民法第184條 押金").model_dump(), ensure_ascii=False, indent=2))
    return 0
