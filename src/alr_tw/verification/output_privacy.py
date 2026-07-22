"""Local-only privacy screen for final answer output."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AnswerPrivacyResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed: bool
    status: Literal["safe", "redaction_required", "blocked"]
    reasons: list[str] = Field(default_factory=list)
    redactions: list[str] = Field(default_factory=list)
    redacted_answer: str | None = None


_REDACTABLE_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("TW_ID", re.compile(r"(?<![A-Z0-9])[A-Z][12]\d{8}(?!\d)")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")),
    ("MOBILE", re.compile(r"(?<!\d)09\d{2}[- ]?\d{3}[- ]?\d{3}(?!\d)")),
    ("PHONE", re.compile(r"(?<!\d)0\d{1,2}[- ]?\d{3,4}[- ]?\d{4}(?!\d)")),
    (
        "ADDRESS",
        re.compile(
            r"[\u4e00-\u9fff]{2,3}[縣市][\u4e00-\u9fff]{1,5}[區鄉鎮市]"
            r"[^\n，。；;]{0,24}?[路街巷弄]\d{0,5}(?:之\d+)?號"
        ),
    ),
    (
        "ACCESS_TOKEN",
        re.compile(
            r"(?i)(?P<label>\b(?:access[_ -]?token|api[_ -]?key|bearer)\s*[:=]?\s*)"
            r"(?P<secret>[A-Za-z0-9._~+/=-]{12,})"
        ),
    ),
)
_BLOCKED_MARKERS = (
    "未公開訴訟策略",
    "未公開攻防策略",
    "未公開談判底線",
    "未公開證據弱點",
    "公司內部機密",
    "客戶機密",
    "律師保密資訊",
)


def screen_answer_output(answer_text: str) -> AnswerPrivacyResult:
    """Screen the local answer without a length or case-fact threshold."""

    text = answer_text.strip()
    if not text:
        raise ValueError("answer_text is required")
    blocked = [marker for marker in _BLOCKED_MARKERS if marker in text]
    if blocked:
        return AnswerPrivacyResult(
            allowed=False,
            status="blocked",
            reasons=["UNREDACTABLE_CONFIDENTIAL_CONTENT"],
        )

    redacted = text
    labels: list[str] = []
    for label, pattern in _REDACTABLE_RULES:
        if label == "ACCESS_TOKEN":
            redacted, count = pattern.subn(
                lambda match: f"{match.group('label')}[{label}]",
                redacted,
            )
        else:
            redacted, count = pattern.subn(f"[{label}]", redacted)
        if count:
            labels.append(label)
    if labels:
        return AnswerPrivacyResult(
            allowed=False,
            status="redaction_required",
            reasons=["DIRECT_IDENTIFIER_PRESENT"],
            redactions=labels,
            redacted_answer=redacted,
        )
    return AnswerPrivacyResult(allowed=True, status="safe")
