"""Synthetic same-source passage perturbations, not a legal accuracy benchmark."""
from __future__ import annotations

from dataclasses import dataclass

from alr_tw.verification.claim_support import AnswerClaim, LegalSegment, check_claim_support


@dataclass(frozen=True)
class CitationCase:
    case_id: str
    claim: str
    passages: tuple[str, ...]
    roles: tuple[str, ...]
    expected_support: bool
    rationale: str


def cases() -> tuple[CitationCase, ...]:
    result: list[CitationCase] = []

    def pair(key: str, claim: str, negative: str, role: str = "court_reasoning") -> None:
        result.extend((
            CitationCase(key + ":positive", claim, (claim,), ("court_reasoning",), True,
                         "合成法院理由逐字支持主張。"),
            CitationCase(key + ":negative", claim, (negative,), (role,), False,
                         "同一合成來源中的角色、條件、數值、極性或主題已改變。"),
        ))

    for index, (positive, negative) in enumerate([
        ("得請求返還", "不得請求返還"),
        ("應負責任", "不應負責任"),
        ("可以解除契約", "不可以解除契約"),
    ]):
        pair(f"polarity-{index}", "法院認為當事人" + positive, "法院認為當事人" + negative)
    for role in ("party_argument", "dissenting_opinion", "quoted_authority"):
        pair(role, "法院認為當事人得請求返還", "法院認為當事人得請求返還", role)
    for index, (claim, negative) in enumerate([
        ("法院認為應於10日內提出", "法院認為應於30日內提出"),
        ("法院認為應於2020年提出", "法院認為應於2021年提出"),
        ("法院認為應依第7條辦理", "法院認為應依第8條辦理"),
    ]):
        pair(f"anchor-{index}", claim, negative)
    for index, condition in enumerate(("但另有約定者除外", "除法律另有規定外", "僅限符合條件時")):
        pair(f"condition-{index}", "法院認為當事人得請求返還",
             condition + "，法院認為當事人得請求返還")
    pair("unrelated", "法院認為當事人得請求返還", "管理機關保存紀錄的格式由附表規範")
    pair("same-subject-different-duty", "法院認為當事人應保存紀錄", "當事人得申請閱覽檔案")
    # A deliberate positive paraphrase and a multi-passage positive control reveal false refusals.
    result.extend((
        CitationCase("paraphrase:positive", "法院認為當事人得請求返還。",
                     ("法院認為，當事人得請求返還。",), ("court_reasoning",), True,
                     "僅增減標點，命題不變。"),
        CitationCase("adjacent:positive", "法院認為當事人得請求返還，並應保存紀錄",
                     ("法院認為當事人得請求返還", "並應保存紀錄"),
                     ("court_reasoning", "court_reasoning"), True,
                     "兩個相鄰合成段落共同表達完整主張。"),
    ))
    return tuple(result)


def evaluate_case(case: CitationCase) -> dict:
    segments = [LegalSegment(
        segment_id=f"span-{index}", source_id="same-synthetic-source",
        citation_id=f"span-{index}", source_tier="official", legal_material_type="judgment",
        section_role=role, text=text, span_start=0, span_end=len(text),
    ) for index, (text, role) in enumerate(zip(case.passages, case.roles, strict=True))]
    supports, summary, reasons = check_claim_support(
        answer=case.claim,
        claims=[AnswerClaim(claim_id=case.case_id, claim_text=case.claim, claim_type="court_view",
                            referenced_citation_ids=[s.citation_id for s in segments])],
        segments=segments, require_explicit_bindings=True,
    )
    return {"case_id": case.case_id, "expected_support": case.expected_support,
            "gate_allows": summary.semantic_safe_to_present,
            "support_status": supports[0].support_status.value, "reasons": reasons,
            "rationale": case.rationale}


def replay_report() -> dict:
    rows = [evaluate_case(case) for case in cases()]
    negatives = [r for r in rows if not r["expected_support"]]
    positives = [r for r in rows if r["expected_support"]]
    return {"schema_version": "alr-tw.synthetic-citation-replay/v1", "cases": rows,
            "ungated_false_accepts": {"numerator": len(negatives), "denominator": len(negatives)},
            "gated_false_accepts": {"numerator": sum(r["gate_allows"] for r in negatives),
                                    "denominator": len(negatives)},
            "gated_false_refusals": {"numerator": sum(not r["gate_allows"] for r in positives),
                                     "denominator": len(positives)},
            "limitations": ["engineering-authored synthetic expectations; no expert legal review",
                            "ungated arm deliberately presents every fixed draft",
                            "claim gate only; does not establish source trust or answer authorization",
                            "no model quality, live retrieval, or population error-rate claim"]}
