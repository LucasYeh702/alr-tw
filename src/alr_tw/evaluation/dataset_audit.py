"""Evaluator-only immutable CSV audit overlay; never feeds labels to agents."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections import Counter
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AuditDisposition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    row_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["flagged", "corrected", "excluded", "needs_review"]
    reason: str = Field(min_length=1, max_length=500)
    reviewers: list[str] = Field(default_factory=list, max_length=2)
    corrections: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_review(self):
        if set(self.corrections) - {
            "gold_law",
            "gold_article",
            "gold_version_date",
            "tau",
            "answer",
        }:
            raise ValueError("AUDIT_CORRECTION_FIELD_FORBIDDEN")
        if self.status == "corrected" and (len(set(self.reviewers)) != 2 or not self.corrections):
            raise ValueError("AUDIT_INDEPENDENT_REVIEW_REQUIRED")
        if self.status != "corrected" and self.corrections:
            raise ValueError("AUDIT_CORRECTIONS_NOT_APPROVED")
        return self


def audit_csv(
    raw: bytes,
    *,
    revision: str,
    expected_sha256: str,
    law_aliases: dict[str, str],
    dispositions: list[AuditDisposition] | None = None,
) -> dict:
    if len(raw) > 20_000_000 or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("AUDIT_INPUT_INVALID")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise ValueError("AUDIT_INPUT_DIGEST_MISMATCH")
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    if not rows or len(rows) > 10000:
        raise ValueError("AUDIT_ROWS_INVALID")
    import json

    keys = [
        hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        for row in rows
    ]
    counts = Counter(keys)
    questions = Counter(re.sub(r"\s+", "", row.get("question", "")) for row in rows)
    overrides = {item.row_digest: item for item in dispositions or []}
    if len(overrides) != len(dispositions or []) or set(overrides) - set(keys):
        raise ValueError("AUDIT_OVERLAY_IDENTITY_MISMATCH")
    findings = []
    # Longest match consumes aliases so a short law name is never extracted
    # from an already recognized longer statute name.
    pattern = (
        re.compile("|".join(re.escape(name) for name in sorted(law_aliases, key=len, reverse=True)))
        if law_aliases
        else None
    )
    for row, key in zip(rows, keys, strict=True):
        flags = []
        if counts[key] > 1:
            flags.append("duplicate_row")
        if questions[re.sub(r"\s+", "", row.get("question", ""))] > 1:
            flags.append("duplicate_or_whitespace_variant_question")
        names = (
            {law_aliases[m.group()] for m in pattern.finditer(row.get("question", ""))}
            if pattern
            else set()
        )
        gold = law_aliases.get(row.get("gold_law", ""), row.get("gold_law", ""))
        if names and gold not in names:
            flags.append("law_name_mismatch_needs_review")
        if not re.fullmatch(r"(?:第)?\d+(?:[-之]\d+)*(?:條)?", row.get("gold_article", "").strip()):
            flags.append("article_format_needs_review")
        try:
            if date.fromisoformat(row.get("gold_version_date", "")) > date.fromisoformat(
                row.get("legal_date", "")
            ):
                flags.append("version_after_question_date")
        except ValueError:
            flags.append("date_invalid_or_definition_unconfirmed")
        disposition = overrides.get(key)
        findings.append(
            {
                "row_digest": key,
                "flags": flags,
                "status": disposition.status if disposition else "needs_review",
                "stratum": row.get("tau", "unknown"),
                "corrections_approved": bool(disposition and disposition.status == "corrected"),
            }
        )
    statuses = Counter(item["status"] for item in findings)
    return {
        "schema_version": "alr-tw.dataset-audit/v1",
        "dataset_revision": revision,
        "source_sha256": digest,
        "checker_version": "1",
        "raw_count": len(rows),
        "corrected_count": statuses["corrected"],
        "excluded_count": statuses["excluded"],
        "pending_count": statuses["needs_review"] + statuses["flagged"],
        "strata": dict(Counter(item["stratum"] for item in findings)),
        "rows": findings,
        "version_date_definition": "unconfirmed_until_independent_review",
        "legal_quality_verified": False,
        "agent_input_authorized": False,
    }
