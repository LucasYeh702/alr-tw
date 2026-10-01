import hashlib
import json
import pytest
from alr_tw.evaluation.dataset_audit import audit_csv, AuditDisposition

RAW = (
    "question,gold_law,gold_article,gold_version_date,legal_date,tau\n"
    "合成刑事訴訟法問題,刑法,1,2020-01-01,2019-01-01,Shifted\n"
    "合成民法問題,民法,1,2010-01-01,2019-01-01,Stable\n"
).encode()


def audit(raw=RAW, **kwargs):
    return audit_csv(
        raw,
        revision="a" * 40,
        expected_sha256=hashlib.sha256(raw).hexdigest(),
        law_aliases={"刑事訴訟法": "刑事訴訟法", "刑法": "刑法", "民法": "民法"},
        **kwargs,
    )


def test_audit_preserves_raw_reports_denominators_and_no_question_or_gold():
    result = audit()
    assert result["raw_count"] == result["pending_count"] == 2
    assert result["rows"][0]["flags"] == [
        "law_name_mismatch_needs_review",
        "version_after_question_date",
    ]
    assert result["rows"][1]["flags"] == []
    assert "合成刑事訴訟法問題" not in json.dumps(result, ensure_ascii=False)
    assert not result["agent_input_authorized"]


def test_corrections_require_two_reviewers_and_match_immutable_row():
    key = audit()["rows"][0]["row_digest"]
    with pytest.raises(ValueError, match="INDEPENDENT_REVIEW"):
        AuditDisposition(
            row_digest=key,
            status="corrected",
            reason="synthetic",
            reviewers=["a"],
            corrections={"gold_law": "x"},
        )
    correction = AuditDisposition(
        row_digest=key,
        status="corrected",
        reason="synthetic",
        reviewers=["a", "b"],
        corrections={"gold_law": "x"},
    )
    assert audit(dispositions=[correction])["corrected_count"] == 1
    with pytest.raises(ValueError, match="IDENTITY_MISMATCH"):
        audit(dispositions=[correction.model_copy(update={"row_digest": "0" * 64})])


def test_digest_and_duplicates():
    with pytest.raises(ValueError, match="DIGEST_MISMATCH"):
        audit_csv(RAW, revision="a" * 40, expected_sha256="0" * 64, law_aliases={})
    result = audit(RAW + RAW.splitlines(keepends=True)[1])
    assert result["raw_count"] == 3
    assert "duplicate_row" in result["rows"][0]["flags"]
