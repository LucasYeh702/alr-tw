from __future__ import annotations

import json
from typing import Any, Literal, cast

from tw_legal_rag_mcp.legal_nlp.privacy import mask_sensitive_text
from tw_legal_rag_mcp.legal_nlp.query_normalizer import normalize_query
from tw_legal_rag_mcp.verification.citation_validator import validate_citation
from alr_tw.verification.claim_support import (
    AnswerClaim,
    ClaimSupport,
    ClaimSupportingSegment,
    LegalSegment,
    SectionRole,
    SemanticGroundingSummary,
    SupportStatus,
    SupportType,
    claim_support_failure_reasons,
    summarize_claim_support,
)

from .constants import FinalAction, ToolExecutionMode, TrustFailureReason
from .execution_graph import TRANSITIONS, StepKind
from .trace_schema import AgenticRunTrace, EvidenceRecord, ToolCallTrace, TrustGateTrace

SCENARIOS = {
    "auto",
    "pass_official_source",
    "pass_claim_supported",
    "fail_candidate_only",
    "fail_synthetic_only",
    "fail_verified_cache_incomplete",
    "fail_no_final_citation",
    "fail_low_coverage",
    "human_review_required_claim_support",
    "human_review_claim_unchecked",
    "fail_party_argument_as_court_view",
    "fail_overstated_case_specific_rule",
    "fail_unsupported_paraphrase",
}


def _scenario_records(scenario: str) -> list[dict[str, Any]]:
    if scenario in {
        "auto",
        "pass_official_source",
        "pass_claim_supported",
        "fail_low_coverage",
        "human_review_required_claim_support",
        "human_review_claim_unchecked",
        "fail_party_argument_as_court_view",
        "fail_overstated_case_specific_rule",
        "fail_unsupported_paraphrase",
    }:
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


def _official_claim_segment() -> LegalSegment:
    return LegalSegment(
        segment_id="official-demo-law-184-seg-01",
        source_id="official-demo-law-184",
        citation_id="official-demo-law-184",
        source_tier="official",
        legal_material_type="law",
        section_role=SectionRole.STATUTE_TEXT,
        text="依民法規定，關於押金之約定，得依契約條款及事實情節個別檢討。",
        span_start=0,
        span_end=36,
        official_url="https://example.test/synthetic-official/civil-law-demo#article-184",
        content_hash="sha256:synthetic-official-law-184",
        verified_at="2026-01-01T00:00:00Z",
    )


def _party_argument_segment() -> LegalSegment:
    return LegalSegment(
        segment_id="official-demo-law-184-seg-02",
        source_id="official-demo-law-184",
        citation_id="official-demo-law-184",
        source_tier="official",
        legal_material_type="law",
        section_role=SectionRole.PARTY_ARGUMENT,
        text="當事人主張法院應認定出租人應返還全部押金。",
        span_start=36,
        span_end=74,
        official_url="https://example.test/synthetic-official/civil-law-demo#article-184",
        content_hash="sha256:synthetic-official-law-184",
        verified_at="2026-01-01T00:00:00Z",
    )


def _court_reason_segment() -> LegalSegment:
    return LegalSegment(
        segment_id="official-demo-law-184-seg-03",
        source_id="official-demo-law-184",
        citation_id="official-demo-law-184",
        source_tier="official",
        legal_material_type="law",
        section_role=SectionRole.COURT_HOLDING,
        text="本件以本次契約事實為限，認為租賃法院可斟酌雙方意思自治與實際損失。",
        span_start=74,
        span_end=138,
        official_url="https://example.test/synthetic-official/civil-law-demo#article-184",
        content_hash="sha256:synthetic-official-law-184",
        verified_at="2026-01-01T00:00:00Z",
    )


def _scenario_claim_support(
    scenario: str,
) -> tuple[list[AnswerClaim], list[ClaimSupport], SemanticGroundingSummary]:
    if scenario in {"auto", "pass_official_source", "pass_claim_supported"}:
        claims = [
            AnswerClaim(
                claim_id="claim-001",
                claim_text="法院認為押金可否返還需依契約約定與事實情節判斷。",
                claim_type="court_view",
                referenced_citation_ids=["official-demo-law-184"],
                importance="core",
            )
        ]
        support = [
            ClaimSupport(
                claim_id="claim-001",
                support_status=SupportStatus.SUPPORTED,
                supporting_segments=[
                    ClaimSupportingSegment(
                        segment_id="official-demo-law-184-seg-01",
                        support_type=SupportType.DIRECT_SUPPORT,
                        section_role=SectionRole.STATUTE_TEXT,
                        span_start=0,
                        span_end=36,
                    )
                ],
                risk_flags=[],
                review_required=False,
                support_strength_note="Synthetic segment confirms claim framing and source-role match.",
            )
        ]
        return claims, support, summarize_claim_support(support)

    if scenario in {"human_review_required_claim_support", "human_review_claim_unchecked"}:
        claims = [
            AnswerClaim(
                claim_id="claim-001",
                claim_text="官方資料未進行逐句核對前，不能宣告可直接引用。",
                claim_type="unknown",
                referenced_citation_ids=["official-demo-law-184"],
                importance="core",
            )
        ]
        support = [
            ClaimSupport(
                claim_id="claim-001",
                support_status=SupportStatus.UNCHECKED,
                supporting_segments=[],
                risk_flags=["role_not_linked"],
                review_required=True,
                support_strength_note="Claim support intentionally未檢查。",
            )
        ]
        summary = summarize_claim_support(support)
        return claims, support, summary

    if scenario == "fail_party_argument_as_court_view":
        claims = [
            AnswerClaim(
                claim_id="claim-001",
                claim_text="法院認為出租人應無條件返還押金。",
                claim_type="court_view",
                referenced_citation_ids=["official-demo-law-184"],
                importance="core",
            )
        ]
        support = [
            ClaimSupport(
                claim_id="claim-001",
                support_status=SupportStatus.ROLE_ERROR,
                supporting_segments=[
                    ClaimSupportingSegment(
                        segment_id="official-demo-law-184-seg-02",
                        support_type=SupportType.DIRECT_SUPPORT,
                        section_role=SectionRole.PARTY_ARGUMENT,
                        span_start=36,
                        span_end=74,
                    )
                ],
                risk_flags=["party_argument_as_court_view"],
                review_required=False,
                support_strength_note="Party argument被誤述為法院見解。",
            )
        ]
        return claims, support, summarize_claim_support(support)

    if scenario == "fail_overstated_case_specific_rule":
        claims = [
            AnswerClaim(
                claim_id="claim-001",
                claim_text="此判決規則一律適用於所有押金契約。",
                claim_type="case_specific_application",
                referenced_citation_ids=["official-demo-law-184"],
                importance="core",
            )
        ]
        support = [
            ClaimSupport(
                claim_id="claim-001",
                support_status=SupportStatus.OVERSTATED,
                supporting_segments=[
                    ClaimSupportingSegment(
                        segment_id="official-demo-law-184-seg-03",
                        support_type=SupportType.DIRECT_SUPPORT,
                        section_role=SectionRole.COURT_HOLDING,
                        span_start=74,
                        span_end=138,
                    )
                ],
                risk_flags=["case_specific_overgeneralized"],
                review_required=True,
                support_strength_note="證據僅涵蓋個案，句意被擴張。",
            )
        ]
        return claims, support, summarize_claim_support(support)

    if scenario == "fail_unsupported_paraphrase":
        claims = [
            AnswerClaim(
                claim_id="claim-001",
                claim_text="法院主張承租人得無視契約文字而請求全額賠償。",
                claim_type="court_view",
                referenced_citation_ids=["official-demo-law-184"],
                importance="core",
            )
        ]
        support = [
            ClaimSupport(
                claim_id="claim-001",
                support_status=SupportStatus.UNSUPPORTED,
                supporting_segments=[],
                risk_flags=["unsupported_paraphrase"],
                review_required=False,
                support_strength_note="段落文字與主張在重述邏輯上不相容。",
            )
        ]
        return claims, support, summarize_claim_support(support)

    return [], [], SemanticGroundingSummary()


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


def _semantic_segments_for_scenario(scenario: str) -> list[LegalSegment]:
    if scenario == "fail_party_argument_as_court_view":
        return [_official_claim_segment(), _party_argument_segment()]
    if scenario == "fail_overstated_case_specific_rule":
        return [_official_claim_segment(), _court_reason_segment()]
    if scenario == "fail_unsupported_paraphrase":
        return [_official_claim_segment()]
    if scenario in {
        "auto",
        "pass_official_source",
        "pass_claim_supported",
        "fail_low_coverage",
        "human_review_required_claim_support",
        "human_review_claim_unchecked",
    }:
        return [_official_claim_segment()]
    return []


def _trust_gate_trace(
    *,
    evidence: list[EvidenceRecord],
    coverage: dict[str, str],
    semantic_summary: SemanticGroundingSummary,
    semantic_reason_override: list[str] | None = None,
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

    summary_reasons = semantic_reason_override or claim_support_failure_reasons(semantic_summary)
    reasons.extend(summary_reasons)

    has_human_review_reason = any(
        reason in {
            TrustFailureReason.CLAIM_SUPPORT_NOT_CHECKED.value,
            TrustFailureReason.CLAIM_SUPPORT_UNCHECKED.value,
            TrustFailureReason.CLAIM_SUPPORT_NEEDS_REVIEW.value,
            TrustFailureReason.CLAIM_OVERSTATED.value,
        }
        for reason in reasons
    )

    critical_reasons = {
        TrustFailureReason.REJECTED_CITATION.value,
        TrustFailureReason.UNVERIFIABLE_CITATION.value,
        TrustFailureReason.LAWS_COVERAGE_LOW.value,
        TrustFailureReason.JUDGMENTS_COVERAGE_LOW.value,
        TrustFailureReason.CLAIM_UNSUPPORTED.value,
        TrustFailureReason.CLAIM_CONTRADICTED.value,
        TrustFailureReason.CLAIM_ROLE_ERROR.value,
    }
    has_critical_failure = any(reason in critical_reasons for reason in reasons)

    if has_overstated_or_review := (TrustFailureReason.CLAIM_OVERSTATED.value in reasons):
        reasons.append(TrustFailureReason.HUMAN_REVIEW_REQUIRED.value)

    has_legacy_review_block = TrustFailureReason.CLAIM_SUPPORT_NOT_CHECKED.value in reasons
    safe = final_count > 0 and not reasons
    if safe:
        action = FinalAction.ANSWER.value
    elif final_count > 0 and (has_human_review_reason or has_overstated_or_review or has_legacy_review_block) and not has_critical_failure:
        action = FinalAction.HUMAN_REVIEW_REQUIRED.value
    else:
        action = FinalAction.REFUSE.value

    if action == FinalAction.HUMAN_REVIEW_REQUIRED.value:
        reasons = sorted(set(reasons))

    return TrustGateTrace(
        safe_to_present=safe,
        failure_reasons=sorted(set(reasons)),
        validation_summary={
            "has_final_citation": final_count > 0,
            "has_rejected_citation": rejected_count > 0,
            "has_unverifiable_citation": unverifiable_count > 0,
            "safe_to_present": safe,
            "human_review_required": action == FinalAction.HUMAN_REVIEW_REQUIRED.value,
            "claim_support": semantic_summary.model_dump(),
        },
        recommended_action=cast(
            Literal["answer", "refuse", "human_review_required"],
            action,
        ),
    )


def run_agentic_demo(
    query: str,
    *,
    scenario: str = "auto",
    require_final: bool = True,
) -> AgenticRunTrace:
    del require_final
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario: {scenario}")

    canonical_scenario = (
        "human_review_required_claim_support" if scenario == "human_review_claim_unchecked" else scenario
    )

    public_query = mask_sensitive_text(query.strip(), mask_names=True)
    if not public_query:
        raise ValueError("query is required")

    normalized_query = normalize_query(public_query)
    records = _scenario_records(canonical_scenario)
    coverage = _coverage_for(canonical_scenario)
    evidence = _evidence(records)
    _ = _semantic_segments_for_scenario(canonical_scenario)
    answer_claims, claim_support, claim_summary = _scenario_claim_support(canonical_scenario)

    trust_gate = _trust_gate_trace(
        evidence=evidence,
        coverage=coverage,
        semantic_summary=claim_summary,
    )

    answer = (
        "Synthetic answer grounded by final citation."
        if trust_gate.recommended_action == FinalAction.ANSWER.value
        else None
    )

    notes: list[str] = []
    if trust_gate.recommended_action == FinalAction.HUMAN_REVIEW_REQUIRED.value:
        notes = ["Claim support requires human legal review before presenting an answer."]

    if claim_summary and trust_gate.recommended_action != FinalAction.ANSWER.value:
        claim_summary.semantic_safe_to_present = False

    final_citation_count = sum(1 for item in evidence if item.citation_use == "allow_final")

    return AgenticRunTrace(
        query=public_query,
        normalized_query=normalized_query,
        steps=[
            {"from": source.value, "to": target.value}
            for source, target in TRANSITIONS
        ],
        tool_calls=[
            ToolCallTrace(
                tool_name=step.value,
                execution_mode=ToolExecutionMode.HARNESS_RECORDED.value,
                input_summary={"query": public_query} if step == StepKind.QUERY_UNDERSTANDING else {},
                output_summary=(
                    {
                        "scenario": canonical_scenario,
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
                "step": "claim_support",
                "claim_count": claim_summary.claim_count,
                "semantic_safe_to_present": claim_summary.semantic_safe_to_present,
                "failure_reasons": list(claim_support_failure_reasons(claim_summary)),
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
        answer_claims=answer_claims,
        claim_support=claim_support,
        semantic_grounding_summary=claim_summary,
        semantic_failure_reasons=list(claim_support_failure_reasons(claim_summary)),
        trust_gate=trust_gate,
        final_action=trust_gate.recommended_action,
        answer=answer,
        human_review_notes=notes,
    )


def main() -> int:
    print(json.dumps(run_agentic_demo("民法第184條 押金").model_dump(), ensure_ascii=False, indent=2))
    return 0
