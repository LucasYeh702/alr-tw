from __future__ import annotations

import re


EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"\b(?:09\d{2}[- ]?\d{3}[- ]?\d{3}|0\d{1,2}[- ]?\d{3,4}[- ]?\d{4})\b")
TW_ID_RE = re.compile(r"\b[A-Z][12]\d{8}\b")
ADDRESS_RE = re.compile(r"[\u4e00-\u9fff]{2,3}[縣市][\u4e00-\u9fff]{1,4}[區鄉鎮市][^\s，。,.]{2,20}")
NAME_RE = re.compile(r"\b[\u4e00-\u9fff]{2,3}\b")
MASK_MARKERS = ("[EMAIL]", "[PHONE]", "[TW_ID]", "[ADDRESS]", "[NAME]")


def mask_sensitive_text(text: str, *, mask_names: bool = False) -> str:
    masked = EMAIL_RE.sub("[EMAIL]", text)
    masked = PHONE_RE.sub("[PHONE]", masked)
    masked = TW_ID_RE.sub("[TW_ID]", masked)
    masked = ADDRESS_RE.sub("[ADDRESS]", masked)
    if mask_names:
        masked = NAME_RE.sub(lambda m: "[NAME]" if m.group(0).endswith(("明", "華", "芳")) else m.group(0), masked)
    return masked


def external_recall_safety_gate(text: str, *, mask_names: bool = True) -> dict[str, object]:
    masked = mask_sensitive_text(text, mask_names=mask_names)
    markers = [marker for marker in MASK_MARKERS if marker in masked]
    return {
        "allowed": not markers,
        "masked_query": masked,
        "sensitive_markers": markers,
    }
