from alr_tw.contracts.judgment_semantics import (
    AttributionConfidence,
    DispositionRelation,
    JudgmentAttribution,
    JudgmentDisposition,
    JudgmentDispositionFinding,
    JudgmentSemanticsContract,
    JudgmentSpeaker,
    JudgmentStance,
    classify_disposition_text,
    validate_judgment_semantics,
)
from alr_tw.providers.official.judgment_parser import (
    JudgmentParseStatus,
    parse_judgment_blocks,
)


JID = "DEMO,130,測,653,20990101,1"


def test_lower_court_reasoning_is_not_current_court_support() -> None:
    parsed = parse_judgment_blocks(
        [
            "主文",
            "原判決廢棄，發回臺灣高等法院。",
            "理由",
            "原審認定被上訴人年滿65歲後有受扶養之必要。",
        ],
        canonical_jid=JID,
    )

    section = parsed.sections[-1]
    assert parsed.parse_status is JudgmentParseStatus.PARTIAL
    assert section.speaker is JudgmentSpeaker.LOWER_COURT
    assert section.stance is JudgmentStance.DESCRIBES
    assert section.relation_to_disposition is DispositionRelation.BACKGROUND_ONLY
    assert section.eligible_for_claim_support is False
    assert "JUDGMENT_LOWER_COURT_ATTRIBUTION_PRESENT" in parsed.warnings


def test_current_court_rejection_of_lower_court_view_is_eligible() -> None:
    parsed = parse_judgment_blocks(
        [
            "主文",
            "原判決廢棄，發回臺灣高等法院。",
            "理由",
            "原審未予調查審認，遽謂被上訴人年滿65歲後難以自行謀生，不免率斷。",
        ],
        canonical_jid=JID,
    )

    section = parsed.sections[-1]
    assert parsed.parse_status is JudgmentParseStatus.COMPLETE
    assert section.speaker is JudgmentSpeaker.CURRENT_COURT
    assert section.stance is JudgmentStance.REJECTS
    assert section.relation_to_disposition is DispositionRelation.REASON_FOR_REMAND
    assert section.eligible_for_claim_support is True


def test_lower_court_fact_with_negative_legal_word_stays_lower_court() -> None:
    parsed = parse_judgment_blocks(
        [
            "主文",
            "上訴駁回。",
            "理由",
            "原審認定被告之行為違法。",
        ],
        canonical_jid=JID,
    )

    section = parsed.sections[-1]
    assert section.speaker is JudgmentSpeaker.LOWER_COURT
    assert section.stance is JudgmentStance.DESCRIBES
    assert section.eligible_for_claim_support is False


def test_current_court_adoption_of_lower_court_view_is_explicit() -> None:
    parsed = parse_judgment_blocks(
        [
            "主文",
            "上訴駁回。",
            "理由",
            "法院認為原判決並無違誤。",
        ],
        canonical_jid=JID,
    )

    section = parsed.sections[-1]
    assert section.speaker is JudgmentSpeaker.CURRENT_COURT
    assert section.stance is JudgmentStance.ADOPTS
    assert section.eligible_for_claim_support is True


def test_vacated_reversed_reason_is_not_labeled_remand_reason() -> None:
    parsed = parse_judgment_blocks(
        [
            "主文",
            "原判決廢棄，自為判決。",
            "理由",
            "原審判斷有所違誤。",
        ],
        canonical_jid=JID,
    )

    section = parsed.sections[-1]
    assert section.stance is JudgmentStance.REJECTS
    assert section.relation_to_disposition is DispositionRelation.SUPPORTS_RESULT


def test_disposition_classifier_keeps_main_result_separate_from_reasoning() -> None:
    assert classify_disposition_text("原判決廢棄，發回臺灣高等法院。") == (
        JudgmentDisposition.VACATED_REMANDED,
    )
    assert classify_disposition_text("上訴駁回，原判決維持。") == (
        JudgmentDisposition.APPEAL_DISMISSED,
        JudgmentDisposition.AFFIRMED,
    )


def _contract(*, lower: bool = False) -> JudgmentSemanticsContract:
    attribution = JudgmentAttribution(
        section_id="section-002",
        speaker=JudgmentSpeaker.LOWER_COURT if lower else JudgmentSpeaker.CURRENT_COURT,
        stance=JudgmentStance.DESCRIBES if lower else JudgmentStance.REJECTS,
        relation_to_disposition=(
            DispositionRelation.BACKGROUND_ONLY
            if lower
            else DispositionRelation.REASON_FOR_REMAND
        ),
        confidence=AttributionConfidence.HIGH,
        source_ids=["src-1"],
        evidence_ids=["ev-1"],
        eligible_for_claim_support=not lower,
    )
    return JudgmentSemanticsContract(
        run_id="run-1",
        source_id="src-1",
        canonical_jid=JID,
        parser_version="judgment-parser/v3",
        attributions=[attribution],
        dispositions=[
            JudgmentDispositionFinding(
                finding_id="disp-1",
                section_id="section-001",
                disposition=JudgmentDisposition.VACATED_REMANDED,
                confidence=AttributionConfidence.HIGH,
                source_ids=["src-1"],
                evidence_ids=["ev-2"],
            )
        ],
    )


def test_server_bound_contract_is_structurally_valid_but_not_citation_authority() -> None:
    result = validate_judgment_semantics(
        _contract(),
        server_run_id="run-1",
        server_source_ids=["src-1"],
        server_evidence_ids=["ev-1", "ev-2"],
    )
    assert result.valid is True
    assert result.eligible_for_current_court_claim is True
    assert result.safe_for_citation is False
    assert result.semantic_entailment_performed is False


def test_disposition_only_does_not_claim_current_court_holding_support() -> None:
    contract = _contract().model_copy(update={"attributions": []})
    result = validate_judgment_semantics(
        contract,
        server_run_id="run-1",
        server_source_ids=["src-1"],
        server_evidence_ids=["ev-1", "ev-2"],
    )
    assert result.valid is True
    assert result.eligible_for_current_court_claim is False
    assert result.eligible_for_disposition_claim is True


def test_lower_court_and_forged_eligibility_fail_closed() -> None:
    lower = validate_judgment_semantics(
        _contract(lower=True),
        server_run_id="run-1",
        server_source_ids=["src-1"],
        server_evidence_ids=["ev-1", "ev-2"],
    )
    assert lower.valid is True
    assert lower.eligible_for_current_court_claim is False
    assert lower.eligible_for_disposition_claim is True
    assert "JUDGMENT_CURRENT_COURT_ATTRIBUTION_UNRESOLVED" in lower.qualifications

    forged = _contract(lower=True).model_copy(
        update={
            "attributions": [
                _contract(lower=True).attributions[0].model_copy(
                    update={"eligible_for_claim_support": True}
                )
            ]
        }
    )
    result = validate_judgment_semantics(
        forged,
        server_run_id="run-1",
        server_source_ids=["src-1"],
        server_evidence_ids=["ev-1", "ev-2"],
    )
    assert result.valid is False
    assert any("ELIGIBILITY_FORGED" in item for item in result.blockers)


def test_missing_disposition_is_a_blocker() -> None:
    contract = _contract().model_copy(update={"dispositions": []})
    result = validate_judgment_semantics(
        contract,
        server_run_id="run-1",
        server_source_ids=["src-1"],
        server_evidence_ids=["ev-1"],
    )
    assert result.valid is False
    assert "JUDGMENT_DISPOSITION_UNRESOLVED" in result.blockers
