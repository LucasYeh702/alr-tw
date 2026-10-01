import pytest

from alr_tw.contracts.providers import DataMode
from alr_tw.research.service import _claims_for_validation
from alr_tw.verification.claim_support import ClaimBinding
from test_v080_finalization_integration import _prepared_service, NOW


SUPPORTED = "行為人應負合成責任"


def binding(text=SUPPORTED, *, claim_id="bound", evidence_id="evidence-1"):
    return {"claim_id": claim_id, "claim_text": text, "claim_type": "law_rule",
            "evidence_ids": [evidence_id]}


@pytest.mark.parametrize("answer", [
    SUPPORTED + "，主管機關應核發許可。",
    SUPPORTED + "且主管機關應核發許可。",
    SUPPORTED + "，" + SUPPORTED + "且主管機關應核發許可。",
    "行為人 應負合成責任，主管機關應核發許可。",
    SUPPORTED + "，無罪。",
])
def test_partial_binding_never_authorizes_unchecked_extension(tmp_path, answer):
    service, run_id, evidence_id = _prepared_service(tmp_path, mode=DataMode.OFFICIAL_ONLY)
    result = service.validate_answer(run_id, answer, "partial", now=NOW,
                                     claim_bindings=[binding(evidence_id=evidence_id)])
    assert result["safe_to_present"] is False
    assert result["answer_text"] is None
    assert result["semantic_summary"]["unchecked_count"] >= 1


def test_two_fully_bound_clauses_still_pass(tmp_path):
    service, run_id, evidence_id = _prepared_service(tmp_path, mode=DataMode.OFFICIAL_ONLY)
    first, second = "合成責任法第1條", SUPPORTED
    result = service.validate_answer(run_id, first + "，" + second + "。", "full", now=NOW,
        claim_bindings=[binding(first, claim_id="a", evidence_id=evidence_id),
                        binding(second, claim_id="b", evidence_id=evidence_id)])
    assert result["safe_to_present"] is True


def test_arbitrary_substrings_cannot_tile_one_claim():
    claims = _claims_for_validation(SUPPORTED + "。", [
        ClaimBinding(**binding("行為人", claim_id="a")),
        ClaimBinding(**binding("應負合成責任", claim_id="b")),
    ])
    assert any(not c.referenced_citation_ids for c in claims)


@pytest.mark.parametrize("answer,bound", [
    ("合成數值為10。", "合成數值為1.0"),
    ("合成數值為-10。", "合成數值為10"),
    ("合成值為Ab。", "合成值為ab"),
])
def test_binding_normalization_preserves_numbers_operators_and_case(answer, bound):
    with pytest.raises(ValueError, match="CLAIM_BINDING_TEXT_NOT_IN_ANSWER"):
        _claims_for_validation(answer, [ClaimBinding(**binding(bound))])


def test_exact_width_normalized_claim_can_be_covered():
    claims = _claims_for_validation("合成值為Ａ１。", [ClaimBinding(**binding("合成值為A1"))])
    assert len(claims) == 1


def test_unverified_citation_suffix_cannot_hide_a_new_conclusion(tmp_path):
    from test_v070_civil_analysis import _ready_service
    service, run_id, evidence, now = _ready_service(tmp_path)
    claim = "行為人違反示範義務時，應負合成測試責任"
    citation = "示範責任法第7條且主管機關應核發許可"
    answer = claim + "（" + citation + "）。"
    result = service.validate_answer(run_id, answer, "citation-smuggle", now=now, claim_bindings=[{
        **binding(claim, evidence_id=evidence.evidence_id), "issue_ids": ["issue-duty"],
        "citation_occurrences": [{"evidence_id": evidence.evidence_id, "citation_text": citation,
                                  "start_offset": answer.index(citation),
                                  "end_offset": answer.index(citation) + len(citation)}],
    }])
    assert not result["safe_to_present"]
    assert "CITATION_OCCURRENCE_SOURCE_MISMATCH" in result["blockers"]


@pytest.mark.parametrize("punctuation", ["！", "!", "！？"])
def test_chinese_sentence_final_punctuation_keeps_bound_positive(tmp_path, punctuation):
    service, run_id, evidence_id = _prepared_service(tmp_path, mode=DataMode.OFFICIAL_ONLY)
    result = service.validate_answer(run_id, SUPPORTED + punctuation, "punctuation", now=NOW,
                                     claim_bindings=[binding(evidence_id=evidence_id)])
    assert result["safe_to_present"]


def test_math_suffix_is_not_silently_dropped():
    claims = _claims_for_validation("合成值為n!", [ClaimBinding(**binding("合成值為n"))])
    assert any(not claim.referenced_citation_ids for claim in claims)


def test_compatibility_superscript_is_not_equivalent_to_plain_digit():
    with pytest.raises(ValueError, match="CLAIM_BINDING_TEXT_NOT_IN_ANSWER"):
        _claims_for_validation("合成數值為x²。", [ClaimBinding(**binding("合成數值為x2"))])


@pytest.mark.parametrize("before,after", [("!", ""), ("", "!"), ("", "！？")])
def test_verified_citation_and_sentence_punctuation_compose(tmp_path, before, after):
    from test_v070_civil_analysis import _ready_service
    service, run_id, evidence, now = _ready_service(tmp_path)
    claim = "行為人違反示範義務時，應負合成測試責任"
    citation = "示範責任法第7條"
    answer = claim + before + "（" + citation + "）" + after + "。"
    result = service.validate_answer(run_id, answer, "citation-punctuation", now=now, claim_bindings=[{
        **binding(claim, evidence_id=evidence.evidence_id), "issue_ids": ["issue-duty"],
        "citation_occurrences": [{"evidence_id": evidence.evidence_id, "citation_text": citation,
                                  "start_offset": answer.index(citation),
                                  "end_offset": answer.index(citation) + len(citation)}],
    }])
    assert result["safe_to_present"]
