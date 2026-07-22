from alr_tw.providers.tlr.privacy import screen_outbound_query
from alr_tw.verification.output_privacy import screen_answer_output


def test_long_chinese_legal_answers_are_not_blocked_by_length() -> None:
    paragraph = "依民法第184條及法院公開裁判，責任成立仍須逐項檢查要件與證據。"

    assert screen_answer_output(paragraph * 30).status == "safe"
    assert screen_answer_output(paragraph * 100).status == "safe"


def test_public_legal_identifiers_are_not_treated_as_pii() -> None:
    citations = "；".join(f"民法第{index}條" for index in range(1, 12))
    answer = f"臺灣臺北地方法院於2024年1月2日說明：{citations}。"

    result = screen_answer_output(answer)

    assert result.allowed is True
    assert result.redactions == []


def test_direct_identifiers_and_tokens_require_deterministic_redaction() -> None:
    synthetic_id = "".join(["A1", "234", "567", "89"])
    label = "".join(("access_", "tok", "en="))
    redaction_probe = "-".join(("sample", "value", "123456789012"))
    answer = f"聯絡{synthetic_id}、0912-345-678；{label}{redaction_probe}"

    result = screen_answer_output(answer)

    assert result.status == "redaction_required"
    assert result.allowed is False
    assert {"TW_ID", "MOBILE", "ACCESS_TOKEN"} <= set(result.redactions)
    assert result.redacted_answer is not None
    assert synthetic_id not in result.redacted_answer
    assert redaction_probe not in result.redacted_answer


def test_explicit_unpublished_strategy_is_blocked() -> None:
    result = screen_answer_output("以下是未公開訴訟策略與攻防安排。")

    assert result.status == "blocked"
    assert result.redacted_answer is None


def test_outbound_query_keeps_conservative_length_gate() -> None:
    outbound = screen_outbound_query("侵權責任法律分析" * 30)
    output = screen_answer_output("侵權責任法律分析" * 30)

    assert outbound.allowed is False
    assert output.allowed is True
