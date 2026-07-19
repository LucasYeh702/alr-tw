from alr_tw.verification.claim_support import (
    AnswerClaim,
    ClaimType,
    LegalSegment,
    SectionRole,
    SupportStatus,
    check_claim_support,
)


def test_dissent_cannot_be_presented_as_the_courts_view() -> None:
    text = "法院認為本規定一律無效"
    support, summary, reasons = check_claim_support(
        answer=text,
        claims=[
            AnswerClaim(
                claim_id="claim-1",
                claim_text=text,
                claim_type=ClaimType.COURT_VIEW,
            )
        ],
        segments=[
            LegalSegment(
                segment_id="dissent-1",
                source_id="constitutional-1",
                citation_id="constitutional-1",
                source_tier="official",
                legal_material_type="constitutional_material",
                section_role=SectionRole.DISSENTING_OPINION,
                text=text,
                span_start=0,
                span_end=len(text),
            )
        ],
    )

    assert support[0].support_status == SupportStatus.ROLE_ERROR
    assert "separate_opinion_as_court_view" in support[0].risk_flags
    assert summary.semantic_safe_to_present is False
    assert "CLAIM_ROLE_ERROR" in reasons
