from __future__ import annotations

from collections import Counter
from enum import Enum
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ClaimSupportLevel(str, Enum):
    NOT_CHECKED = "not_checked"
    SOURCE_VERIFIED = "source_verified"
    QUOTE_PRESENT = "quote_present"
    HOLDING_CANDIDATE = "holding_candidate"
    CLAIM_SUPPORT_CANDIDATE = "claim_support_candidate"
    CLAIM_SUPPORTED = "claim_supported"
    HUMAN_REVIEW_REQUIRED = "human_review_required"


class SectionRole(str, Enum):
    COURT_HOLDING = "court_holding"
    COURT_REASONING = "court_reasoning"
    PARTY_ARGUMENT = "party_argument"
    FACTS = "facts"
    PROCEDURE = "procedure"
    DISPOSITION = "disposition"
    STATUTE_TEXT = "statute_text"
    CONSTITUTIONAL_HOLDING = "constitutional_holding"
    CONCURRING_OPINION = "concurring_opinion"
    DISSENTING_OPINION = "dissenting_opinion"
    UNKNOWN = "unknown"


class ClaimType(str, Enum):
    STATUTORY_RULE = "statutory_rule"
    COURT_VIEW = "court_view"
    CASE_SPECIFIC_APPLICATION = "case_specific_application"
    PROCEDURAL_STATEMENT = "procedural_statement"
    FACTUAL_SUMMARY = "factual_summary"
    RISK_ASSESSMENT = "risk_assessment"
    RECOMMENDATION = "recommendation"
    UNKNOWN = "unknown"


class SupportStatus(str, Enum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    OVERSTATED = "overstated"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    ROLE_ERROR = "role_error"
    UNCHECKED = "unchecked"
    NEEDS_REVIEW = "needs_review"


class LegalMaterialType(str, Enum):
    LAW = "law"
    JUDGMENT = "judgment"
    CONSTITUTIONAL_MATERIAL = "constitutional_material"
    UNKNOWN = "unknown"


class Importance(str, Enum):
    CORE = "core"
    SUPPLEMENTARY = "supplementary"
    CONTEXT = "context"


class SupportType(str, Enum):
    DIRECT_SUPPORT = "direct_support"
    IMPLICIT_SUPPORT = "implicit_support"
    INDIRECT_SUPPORT = "indirect_support"


class ClaimContractModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


class LegalSegment(ClaimContractModel):
    schema_version: str = Field(default="alr-tw.legal-segment/v1", alias="schema")
    segment_id: str
    source_id: str
    citation_id: str
    source_tier: str
    legal_material_type: LegalMaterialType | str
    section_role: SectionRole | str
    text: str
    span_start: int
    span_end: int
    official_url: str | None = None
    content_hash: str | None = None
    verified_at: str | None = None


class AnswerClaim(ClaimContractModel):
    schema_version: str = Field(default="alr-tw.answer-claim/v1", alias="schema")
    claim_id: str
    claim_text: str
    claim_type: ClaimType | str
    referenced_citation_ids: list[str] = Field(default_factory=list)
    importance: Importance | str = Importance.CORE


class ClaimSupportingSegment(ClaimContractModel):
    segment_id: str
    support_type: SupportType
    section_role: SectionRole | str
    span_start: int
    span_end: int


class ClaimSupport(ClaimContractModel):
    schema_version: str = Field(default="alr-tw.claim-support/v1", alias="schema")
    claim_id: str
    support_status: SupportStatus
    supporting_segments: list[ClaimSupportingSegment] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    review_required: bool = False
    support_strength_note: str | None = None


class SemanticGroundingSummary(ClaimContractModel):
    schema_version: str = Field(
        default="alr-tw.semantic-grounding-summary/v1",
        alias="schema",
    )
    claim_count: int = 0
    supported_count: int = 0
    partially_supported_count: int = 0
    overstated_count: int = 0
    unsupported_count: int = 0
    contradicted_count: int = 0
    role_error_count: int = 0
    unchecked_count: int = 0
    needs_review_count: int = 0
    semantic_safe_to_present: bool = False

    def as_mapping(self) -> dict[str, int | bool]:
        return self.model_dump()


def _tokenize(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", value)
        if len(token) > 1
    }


def _extract_importance(text: str) -> Importance:
    normalized = text.strip()
    if "應該" in normalized or "必須" in normalized or "不得" in normalized:
        return Importance.CORE
    if "同時" in normalized or "此外" in normalized:
        return Importance.SUPPLEMENTARY
    return Importance.CORE


def _guess_claim_type(text: str) -> ClaimType:
    if any(keyword in text for keyword in ("應", "不得", "可以", "禁止", "得")):
        if any(keyword in text for keyword in ("法院", "本院", "認為")):
            return ClaimType.COURT_VIEW
        return ClaimType.STATUTORY_RULE
    if any(keyword in text for keyword in ("本件", "本案", "此案", "此事")):
        return ClaimType.CASE_SPECIFIC_APPLICATION
    if any(keyword in text for keyword in ("程序", "訴訟", "上訴", "撤回")):
        return ClaimType.PROCEDURAL_STATEMENT
    return ClaimType.UNKNOWN


def _contains_generality(text: str) -> bool:
    return any(keyword in text for keyword in ("一律", "總是", "一定", "必然", "全部", "通常"))


def _missing_qualifier(text: str) -> bool:
    return any(keyword in text for keyword in ("但", "除非", "例如", "特別", "依")) is False


def _support_strength(text_overlap: float, has_role_mismatch: bool) -> SupportStatus:
    if has_role_mismatch:
        return SupportStatus.ROLE_ERROR
    if text_overlap >= 0.75:
        return SupportStatus.SUPPORTED
    if text_overlap >= 0.55:
        return SupportStatus.PARTIALLY_SUPPORTED
    if text_overlap >= 0.20:
        return SupportStatus.PARTIALLY_SUPPORTED
    return SupportStatus.UNSUPPORTED


def extract_answer_claims(answer: str) -> list[AnswerClaim]:
    text = (answer or "").strip()
    if not text:
        return []

    clauses = [segment.strip() for segment in re.split(r"[。\n;；]", text)]
    claims: list[AnswerClaim] = []
    counter = 1
    for clause in clauses:
        if len(clause) < 3:
            continue
        claims.append(
            AnswerClaim(
                claim_id=f"claim-{counter:03d}",
                claim_text=clause,
                claim_type=_guess_claim_type(clause),
                importance=_extract_importance(clause),
            )
        )
        counter += 1

    return claims


def check_claim_support(
    *,
    answer: str,
    claims: list[dict[str, Any]] | list[AnswerClaim],
    segments: list[dict[str, Any]] | list[LegalSegment],
) -> tuple[list[ClaimSupport], SemanticGroundingSummary, list[str]]:
    normalized_claims = [
        claim if isinstance(claim, AnswerClaim) else AnswerClaim(**claim)
        for claim in claims
    ]
    candidate_segments = [
        segment if isinstance(segment, LegalSegment) else LegalSegment(**segment)
        for segment in segments
    ]

    support_results: list[ClaimSupport] = []
    for claim in normalized_claims:
        support_result = _check_single_claim_support(answer, claim, candidate_segments)
        support_results.append(support_result)

    summary = summarize_claim_support(support_results)
    return support_results, summary, claim_support_failure_reasons(summary)


def _find_candidate_segments(
    claim: AnswerClaim,
    segments: list[LegalSegment],
) -> list[LegalSegment]:
    if claim.referenced_citation_ids:
        return [
            segment
            for segment in segments
            if segment.citation_id in claim.referenced_citation_ids
            or segment.source_id in claim.referenced_citation_ids
        ]
    return segments


def _segment_text_overlap_ratio(claim_text: str, segment_text: str) -> float:
    claim_tokens = _tokenize(claim_text)
    segment_tokens = _tokenize(segment_text)
    if not claim_tokens:
        return 0.0
    if not segment_tokens:
        return 0.0
    return len(claim_tokens & segment_tokens) / len(claim_tokens)


def _check_single_claim_support(
    answer: str,
    claim: AnswerClaim,
    all_segments: list[LegalSegment],
) -> ClaimSupport:
    del answer
    supported_segments = _find_candidate_segments(claim, all_segments)

    if not all_segments or not supported_segments:
        return ClaimSupport(
            claim_id=claim.claim_id,
            support_status=SupportStatus.UNCHECKED,
            review_required=True,
            risk_flags=["section_role_unknown"] if not all_segments else ["role_not_linked"],
        )

    role_mismatch = False
    risk_flags: list[str] = []
    best_segment = supported_segments[0]
    best_overlap = 0.0

    for segment in supported_segments:
        overlap = _segment_text_overlap_ratio(claim.claim_text, segment.text)
        if overlap > best_overlap:
            best_overlap = overlap
            best_segment = segment

        if claim.claim_type == ClaimType.COURT_VIEW and segment.section_role in {
            SectionRole.PARTY_ARGUMENT,
            SectionRole.FACTS,
            SectionRole.CONCURRING_OPINION,
            SectionRole.DISSENTING_OPINION,
        }:
            role_mismatch = True
            if "法院" in claim.claim_text and "認為" in claim.claim_text:
                risk_flags.append(
                    "separate_opinion_as_court_view"
                    if segment.section_role
                    in {SectionRole.CONCURRING_OPINION, SectionRole.DISSENTING_OPINION}
                    else "party_argument_as_court_view"
                )

        if segment.section_role == SectionRole.CONCURRING_OPINION and "協同意見" not in claim.claim_text:
            role_mismatch = True
            risk_flags.append("unlabelled_separate_opinion")
        if segment.section_role == SectionRole.DISSENTING_OPINION and "不同意見" not in claim.claim_text:
            role_mismatch = True
            risk_flags.append("unlabelled_separate_opinion")

        if segment.section_role in {SectionRole.UNKNOWN}:
            risk_flags.append("section_role_unknown")

    if role_mismatch:
        return ClaimSupport(
            claim_id=claim.claim_id,
            support_status=SupportStatus.ROLE_ERROR,
            review_required=True,
            supporting_segments=[
                ClaimSupportingSegment(
                    segment_id=best_segment.segment_id,
                    support_type=SupportType.DIRECT_SUPPORT,
                    section_role=best_segment.section_role,
                    span_start=best_segment.span_start,
                    span_end=best_segment.span_end,
                )
            ],
            risk_flags=sorted(set(risk_flags)),
            support_strength_note="Matched text from non-authoritative role segment.",
        )

    if claim.claim_type == ClaimType.CASE_SPECIFIC_APPLICATION and _contains_generality(claim.claim_text):
        risk_flags.append("case_specific_overgeneralized")
        return ClaimSupport(
            claim_id=claim.claim_id,
            support_status=SupportStatus.OVERSTATED,
            review_required=True,
            supporting_segments=[
                ClaimSupportingSegment(
                    segment_id=best_segment.segment_id,
                    support_type=SupportType.DIRECT_SUPPORT,
                    section_role=best_segment.section_role,
                    span_start=best_segment.span_start,
                    span_end=best_segment.span_end,
                )
            ],
            risk_flags=sorted(set(risk_flags)),
            support_strength_note="Claim appears more general than segment-level conclusion.",
        )

    support_status = _support_strength(best_overlap, False)

    if support_status == SupportStatus.UNSUPPORTED:
        risk_flags.append("unsupported_paraphrase")
    elif support_status in {SupportStatus.PARTIALLY_SUPPORTED, SupportStatus.SUPPORTED}:
        if support_status == SupportStatus.PARTIALLY_SUPPORTED and _missing_qualifier(claim.claim_text):
            risk_flags.append("missing_qualifier")

    if support_status == SupportStatus.PARTIALLY_SUPPORTED:
        return ClaimSupport(
            claim_id=claim.claim_id,
            support_status=support_status,
            supporting_segments=[
                ClaimSupportingSegment(
                    segment_id=best_segment.segment_id,
                    support_type=SupportType.INDIRECT_SUPPORT
                    if best_overlap < 0.55
                    else SupportType.DIRECT_SUPPORT,
                    section_role=best_segment.section_role,
                    span_start=best_segment.span_start,
                    span_end=best_segment.span_end,
                )
            ],
            risk_flags=sorted(set(risk_flags)),
            review_required=True,
            support_strength_note="Segment overlap is partial but non-zero.",
        )

    return ClaimSupport(
        claim_id=claim.claim_id,
        support_status=support_status,
        supporting_segments=[
            ClaimSupportingSegment(
                segment_id=best_segment.segment_id,
                support_type=SupportType.DIRECT_SUPPORT,
                section_role=best_segment.section_role,
                span_start=best_segment.span_start,
                span_end=best_segment.span_end,
            )
        ],
        risk_flags=sorted(set(risk_flags)),
        support_strength_note=(
            "Segment overlap is high and section role matches expected legal statement type."
            if support_status == SupportStatus.SUPPORTED
            else "Segment supports claim but with caveats."
        ),
    )


def summarize_claim_support(items: list[ClaimSupport]) -> SemanticGroundingSummary:
    counts: Counter[str] = Counter(item.support_status for item in items)

    summary = SemanticGroundingSummary(
        claim_count=len(items),
        supported_count=int(counts[SupportStatus.SUPPORTED]),
        partially_supported_count=int(counts[SupportStatus.PARTIALLY_SUPPORTED]),
        overstated_count=int(counts[SupportStatus.OVERSTATED]),
        unsupported_count=int(counts[SupportStatus.UNSUPPORTED]),
        contradicted_count=int(counts[SupportStatus.CONTRADICTED]),
        role_error_count=int(counts[SupportStatus.ROLE_ERROR]),
        unchecked_count=int(counts[SupportStatus.UNCHECKED]),
        needs_review_count=int(counts[SupportStatus.NEEDS_REVIEW]),
    )
    summary.semantic_safe_to_present = _is_semantically_safe(items)
    return summary


def _is_semantically_safe(items: list[ClaimSupport]) -> bool:
    if not items:
        return False
    unsafe_status = {
        SupportStatus.UNSUPPORTED,
        SupportStatus.CONTRADICTED,
        SupportStatus.ROLE_ERROR,
        SupportStatus.OVERSTATED,
        SupportStatus.NEEDS_REVIEW,
        SupportStatus.UNCHECKED,
        SupportStatus.PARTIALLY_SUPPORTED,
    }
    return all(item.support_status not in unsafe_status for item in items)


def claim_support_failure_reasons(summary: SemanticGroundingSummary) -> list[str]:
    reasons = []
    if summary.unsupported_count:
        reasons.append("CLAIM_UNSUPPORTED")
    if summary.overstated_count:
        reasons.append("CLAIM_OVERSTATED")
    if summary.contradicted_count:
        reasons.append("CLAIM_CONTRADICTED")
    if summary.role_error_count:
        reasons.append("CLAIM_ROLE_ERROR")
    if summary.unchecked_count:
        reasons.append("CLAIM_SUPPORT_UNCHECKED")
    if summary.needs_review_count:
        reasons.append("CLAIM_SUPPORT_NEEDS_REVIEW")
    if summary.partially_supported_count:
        reasons.append("CLAIM_SUPPORT_NEEDS_REVIEW")

    return reasons


def claim_grounding_policy() -> dict[str, Any]:
    return {
        "schema": "alr-tw.claim-grounding-policy/v1",
        "description": "公開版僅做 claim-grading 的可重現 schema 與檢核流程，並未做 production 司法語義判斷。",
        "capabilities": [
            "extract_answer_claims",
            "check_claim_support",
            "semantic_risk_flags",
            "partial_support",
        ],
        "limitations": [
            "no_private_section_role_classifier",
            "no_private_claim_entailment_engine",
            "no_private_appeal_lineage_reasoning",
            "no_private_issue_tagger",
            "synthetic_data_only_in_public_repo",
        ],
        "supported_support_status": [
            "supported",
            "partially_supported",
            "overstated",
            "unsupported",
            "contradicted",
            "role_error",
            "unchecked",
            "needs_review",
        ],
        "supported_risk_flags": [
            "party_argument_as_court_view",
            "facts_as_legal_rule",
            "dicta_as_holding",
            "case_specific_overgeneralized",
            "unsupported_paraphrase",
            "wrong_issue_mapping",
            "missing_qualifier",
            "temporal_context_missing",
            "authority_weight_missing",
            "section_role_unknown",
            "role_not_linked",
            "partially_linked",
        ],
    }
