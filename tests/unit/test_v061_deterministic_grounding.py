from alr_tw.verification.claim_support import (
    AnswerClaim,
    ClaimType,
    LegalSegment,
    SectionRole,
    SupportStatus,
    check_claim_support,
)


def _segment(
    segment_id: str,
    text: str,
    *,
    role: SectionRole = SectionRole.COURT_REASONING,
) -> LegalSegment:
    return LegalSegment(
        segment_id=segment_id,
        source_id=f"source-{segment_id}",
        citation_id=segment_id,
        source_tier="official",
        legal_material_type="judgment",
        section_role=role,
        text=text,
        span_start=0,
        span_end=len(text),
    )


def _check(
    claim_text: str,
    evidence_text: str,
    *,
    claim_type: ClaimType = ClaimType.COURT_VIEW,
    role: SectionRole = SectionRole.COURT_REASONING,
):
    return check_claim_support(
        answer=claim_text,
        claims=[
            AnswerClaim(
                claim_id="claim-1",
                claim_text=claim_text,
                claim_type=claim_type,
                referenced_citation_ids=["evidence-1"],
            )
        ],
        segments=[_segment("evidence-1", evidence_text, role=role)],
        require_explicit_bindings=True,
    )[0][0]


def test_chinese_reordered_paraphrase_is_supported() -> None:
    result = _check(
        "法院認為調動命令仍須符合權利濫用禁止原則",
        "本院認為，權利濫用禁止原則仍是調動命令必須符合之要求",
    )

    assert result.support_status is SupportStatus.SUPPORTED


def test_opposing_polarity_is_contradicted_even_with_high_overlap() -> None:
    result = _check(
        "法院認為當事人得請求返還",
        "法院認為當事人不得請求返還",
    )

    assert result.support_status is SupportStatus.CONTRADICTED
    assert "POLARITY_MISMATCH" in result.risk_flags


def test_material_qualifier_omission_is_overstated() -> None:
    result = _check(
        "法院認為當事人一律得解除契約",
        "法院認為當事人原則上得解除契約，但有特別約定者除外",
    )

    assert result.support_status is SupportStatus.OVERSTATED
    assert "QUALIFIER_OMITTED" in result.risk_flags


def test_party_argument_cannot_support_court_view() -> None:
    result = _check(
        "法院認為契約有效",
        "法院認為契約有效",
        role=SectionRole.PARTY_ARGUMENT,
    )

    assert result.support_status is SupportStatus.ROLE_ERROR


def test_numeric_and_article_anchor_mismatches_are_unsupported() -> None:
    days = _check(
        "法律規定應於30日內提出",
        "法律規定應於10日內提出",
        claim_type=ClaimType.STATUTORY_RULE,
        role=SectionRole.STATUTE_TEXT,
    )
    article = _check(
        "依民法第10條應負責任",
        "依民法第11條應負責任",
        claim_type=ClaimType.STATUTORY_RULE,
        role=SectionRole.STATUTE_TEXT,
    )

    assert days.support_status is SupportStatus.UNSUPPORTED
    assert article.support_status is SupportStatus.UNSUPPORTED
    assert "ANCHOR_MISMATCH" in days.risk_flags
    assert "ANCHOR_MISMATCH" in article.risk_flags


def test_unbound_core_claim_requires_span_level_binding() -> None:
    text = "法院認為契約有效"
    support, _, reasons = check_claim_support(
        answer=text,
        claims=[AnswerClaim(claim_id="claim-1", claim_text=text, claim_type="court_view")],
        segments=[_segment("evidence-1", text)],
        require_explicit_bindings=True,
    )

    assert support[0].support_status is SupportStatus.UNCHECKED
    assert "CLAIM_CITATION_BINDING_REQUIRED" in reasons


def test_citation_dumping_does_not_turn_weak_overlap_into_support() -> None:
    claim = "法院認為僱主應給付加班費"
    support, _, _ = check_claim_support(
        answer=claim,
        claims=[
            AnswerClaim(
                claim_id="claim-1",
                claim_text=claim,
                claim_type="court_view",
                referenced_citation_ids=["unrelated", "weak"],
            )
        ],
        segments=[
            _segment("unrelated", "法院說明契約解釋方法"),
            _segment("weak", "僱主與勞工曾有爭議"),
        ],
        require_explicit_bindings=True,
    )

    assert support[0].support_status is SupportStatus.UNSUPPORTED
