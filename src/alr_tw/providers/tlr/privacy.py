"""Deterministic, conservative external-query privacy screen."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from alr_tw.contracts.research import PrivacyStatus

_RULES = [
    ("TW_ID", re.compile(r"(?<![A-Z0-9])[A-Z][12]\d{8}(?!\d)")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")),
    ("MOBILE", re.compile(r"(?<!\d)09\d{2}[- ]?\d{3}[- ]?\d{3}(?!\d)")),
    ("PHONE", re.compile(r"(?<!\d)0\d{1,2}[- ]?\d{3,4}[- ]?\d{4}(?!\d)")),
    (
        "ADDRESS",
        re.compile(r"[\u4e00-\u9fff]{2,3}[縣市][\u4e00-\u9fff]{1,5}[區鄉鎮市].{0,24}?[路街巷弄號]"),
    ),
]
_HARD_SENSITIVE = (
    "未公開契約",
    "保密條款",
    "公司內部代號",
    "內部調查",
    "證據弱點",
    "談判底線",
    "訴訟策略",
    "攻防策略",
    "不要告訴對方",
)
_CASE_FACT_MARKERS = ("我方", "對方", "當事人", "本公司", "客戶", "被告", "原告")


class PrivacyScreenResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: PrivacyStatus
    allowed: bool
    query_to_send: str | None = None
    reasons: list[str] = Field(default_factory=list)
    redactions: list[str] = Field(default_factory=list)


def screen_external_query(query: str) -> PrivacyScreenResult:
    """Screen locally; no model or network call occurs in this function."""

    text = query.strip()
    if not text:
        raise ValueError("query is required")
    if any(marker in text for marker in _HARD_SENSITIVE):
        return PrivacyScreenResult(
            status=PrivacyStatus.SENSITIVE,
            allowed=False,
            reasons=["CONFIDENTIAL_OR_STRATEGY_CONTENT"],
        )
    masked = text
    redactions: list[str] = []
    for label, pattern in _RULES:
        masked, count = pattern.subn(f"[{label}]", masked)
        if count:
            redactions.append(label)
    factual_markers = sum(marker in masked for marker in _CASE_FACT_MARKERS)
    if len(masked) > 180 or factual_markers >= 2:
        return PrivacyScreenResult(
            status=PrivacyStatus.UNCERTAIN,
            allowed=False,
            reasons=["CASE_FACTS_TOO_SPECIFIC"],
            redactions=redactions,
        )
    if redactions:
        return PrivacyScreenResult(
            status=PrivacyStatus.REDACTED_SAFE,
            allowed=True,
            query_to_send=masked,
            reasons=["PII_REDACTED"],
            redactions=redactions,
        )
    return PrivacyScreenResult(
        status=PrivacyStatus.SAFE,
        allowed=True,
        query_to_send=text,
    )


# Precise public alias: this policy applies only before data leaves the process.
screen_outbound_query = screen_external_query
