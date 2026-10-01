"""Synthetic regression cases, not a legal-accuracy benchmark."""

import pytest

from alr_tw.verification.claim_support import (
    AnswerClaim,
    LegalSegment,
    SupportStatus,
    check_claim_support,
)


def check(texts, *, roles=None, bound=None):
    claim = "法院認為當事人得請求返還"
    segments = [
        LegalSegment(
            segment_id=f"e{index}", source_id=f"s{index}", citation_id=f"e{index}",
            source_tier="official", legal_material_type="judgment",
            section_role=roles[index] if roles else "court_reasoning",
            text=text, span_start=0, span_end=len(text),
        )
        for index, text in enumerate(texts)
    ]
    return check_claim_support(
        answer=claim,
        claims=[AnswerClaim(
            claim_id="c1", claim_text=claim, claim_type="court_view",
            referenced_citation_ids=bound or [item.citation_id for item in segments],
        )],
        segments=segments, require_explicit_bindings=True,
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_opposite_bound_statements_require_review_in_either_order(reverse):
    texts = ["法院認為當事人得請求返還", "法院認為當事人不得請求返還"]
    support, summary, reasons = check(list(reversed(texts)) if reverse else texts)
    assert support[0].support_status is SupportStatus.NEEDS_REVIEW
    assert "BOUND_EVIDENCE_POLARITY_CONFLICT" in support[0].risk_flags
    assert len(support[0].supporting_segments) == 2
    assert summary.semantic_safe_to_present is False
    assert "CLAIM_SUPPORT_NEEDS_REVIEW" in reasons


@pytest.mark.parametrize("texts,roles,bound", [
    (["法院認為當事人得請求返還"] * 2, None, None),
    (["法院認為當事人得請求返還", "法院認為當事人不得請求返還"], None, ["e0"]),
    (["法院認為當事人得請求返還", "法院認為當事人不得請求返還"],
     ["court_reasoning", "party_argument"], None),
    (["法院認為當事人得請求返還", "法院認為第三人不得請求返還"], None, None),
])
def test_duplicate_unbound_non_court_and_different_subject_controls(texts, roles, bound):
    support, summary, _ = check(texts, roles=roles, bound=bound)
    assert support[0].support_status is SupportStatus.SUPPORTED
    assert summary.semantic_safe_to_present is True


def test_sole_opposing_statement_remains_contradicted():
    support, summary, _ = check(["法院認為當事人不得請求返還"])
    assert support[0].support_status is SupportStatus.CONTRADICTED
    assert summary.semantic_safe_to_present is False


@pytest.mark.parametrize("roles", [
    ["party_argument", "court_reasoning"],
    ["court_reasoning", "party_argument"],
])
def test_identical_bound_holding_wins_a_role_tie_in_either_order(roles):
    support, summary, _ = check(["法院認為當事人得請求返還"] * 2, roles=roles)
    assert support[0].support_status is SupportStatus.SUPPORTED
    assert support[0].supporting_segments[0].section_role == "court_reasoning"
    assert summary.semantic_safe_to_present is True


def test_party_only_statement_remains_role_error():
    support, summary, _ = check(["法院認為當事人得請求返還"], roles=["party_argument"])
    assert support[0].support_status is SupportStatus.ROLE_ERROR
    assert summary.semantic_safe_to_present is False
