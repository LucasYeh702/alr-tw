import pytest

from alr_tw.evaluation.citation_pairs import cases, evaluate_case, replay_report


@pytest.mark.parametrize("case", cases(), ids=lambda case: case.case_id)
def test_same_source_passage_support_matches_synthetic_expectation(case):
    result = evaluate_case(case)
    assert result["gate_allows"] is case.expected_support, result


def test_replay_denominators_are_explicit_and_not_model_scores():
    report = replay_report()
    assert report["gated_false_accepts"] == {"numerator": 0, "denominator": 14}
    assert report["gated_false_refusals"] == {"numerator": 0, "denominator": 16}
    assert report["ungated_false_accepts"] == {"numerator": 14, "denominator": 14}
    assert report["limitations"]
