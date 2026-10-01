"""Bounded exact-text offset proposals. Never mutates or authorizes a draft."""

import hashlib
from datetime import datetime
from typing import Any

from alr_tw.contracts.sources import EvidenceSpan, SourceRecord, TrustStatus
from alr_tw.verification.claim_support import ClaimBinding

WINDOW = 16


def prepare_citations(answer: str, bindings: list[ClaimBinding], *,
                      evidence: dict[str, EvidenceSpan], sources: dict[str, SourceRecord],
                      now: datetime) -> dict[str, Any]:
    # Reuse the strict source/claim relationship check, not a second relaxed validator.
    from alr_tw.research.service import _citation_occurrence_reasons

    proposals = []
    candidates = []
    # Stage every deterministic correction before checking relationships.  One
    # original offset error must not poison another independently located span.
    for binding in bindings:
        occurrences = []
        for index, occurrence in enumerate(binding.citation_occurrences):
            item: dict[str, Any] = {"claim_id": binding.claim_id, "occurrence_index": index,
                                    "original": occurrence.model_dump(mode="json"), "proposed": None}
            corrected = occurrence
            start = answer.find(occurrence.citation_text)
            if start < 0:
                item["status"] = "text_not_found"
            elif answer.find(occurrence.citation_text, start + 1) >= 0:
                item["status"] = "ambiguous_text"
            elif abs(start - occurrence.start_offset) > WINDOW or abs(
                start + len(occurrence.citation_text) - occurrence.end_offset
            ) > WINDOW:
                item["status"] = "outside_window"
            else:
                corrected = occurrence.model_copy(update={
                    "start_offset": start, "end_offset": start + len(occurrence.citation_text),
                })
                item["status"] = "candidate"
            occurrences.append(corrected)
            proposals.append(item)
        candidates.append(binding.model_copy(update={"citation_occurrences": occurrences}))

    # Keep all bindings, including unresolved spans, to retain ambiguity guards.
    reasons = _citation_occurrence_reasons(
        answer, candidates, evidence_by_id=evidence, sources=sources,
    )
    for binding in candidates:
        for occurrence in binding.citation_occurrences:
            span = evidence.get(occurrence.evidence_id)
            source = sources.get(span.source_id) if span else None
            if not source or source.expires_at <= now or (
                source.trust_status != TrustStatus.EVIDENCE_ELIGIBLE
            ) or not span or not span.eligible_for_claim_support:
                reasons.append("CITATION_SOURCE_NOT_ELIGIBLE")
    corrected_spans = (occurrence for binding in candidates for occurrence in binding.citation_occurrences)
    for item, corrected in zip(proposals, corrected_spans, strict=True):
        if item["status"] != "candidate":
            continue
        if reasons:
            item.update(status="requires_revision", reasons=sorted(set(reasons)))
        else:
            payload = corrected.model_dump(mode="json")
            item.update(status="unchanged" if payload == item["original"] else "proposed",
                        proposed=payload)
    return {"draft_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
            "offset_unit": "unicode_code_point", "end_exclusive": True,
            "window_code_points": WINDOW, "answer_authorized": False,
            "proposals": proposals,
            "next_step": "核對草稿摘要及修正位置，更新原綁定後以新的操作編號完整驗證；改稿後重新預檢。"}
