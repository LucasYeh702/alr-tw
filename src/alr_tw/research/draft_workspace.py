"""Read-only exploratory draft projection; never a final answer decision."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from alr_tw.contracts.sources import EvidenceSpan, SourceRecord, TrustStatus
from alr_tw.storage.sqlite_store import SqliteStore
from .drafting_rules import drafting_guidance
from .citation_preparation import prepare_citations
from alr_tw.verification.claim_support import ClaimBinding, check_claim_support
from alr_tw.verification.output_privacy import screen_answer_output


def _registered_law_digests(
    sources: dict[str, SourceRecord], evidence: dict[str, EvidenceSpan],
) -> tuple[set[str], set[str]]:
    """Known opaque fields only; callers must still screen all free text."""
    evidence_ids = {
        key for key, item in evidence.items()
        if re.fullmatch(r"ev_src_law_[a-f0-9]{24}_[a-f0-9]{12}", key)
        and key.startswith(f"ev_{item.source_id}_")
        and item.source_id in sources
        and sources[item.source_id].provider_id == "official_moj_laws"
    }
    return evidence_ids, {evidence[key].source_id for key in evidence_ids}


def _text_ranges(text: str, claim: str) -> tuple[list[dict[str, int]], bool]:
    ranges: list[dict[str, int]] = []
    position = text.find(claim)
    while position >= 0 and len(ranges) < 32:
        ranges.append({"start": position, "end": position + len(claim)})
        position = text.find(claim, position + 1)
    return ranges, position >= 0


def review_draft(
    store: SqliteStore,
    run_id: str,
    answer_text: str,
    claim_bindings: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    timestamp = now or datetime.now(UTC)
    run = store.get_run(run_id)
    if run is None or run.expires_at <= timestamp:
        raise ValueError("RESEARCH_RUN_EXPIRED")
    if not answer_text.strip() or len(answer_text) > 100000 or len(claim_bindings) > 256:
        raise ValueError("DRAFT_INPUT_INVALID")
    try:
        bindings = [ClaimBinding.model_validate(item) for item in claim_bindings]
    except ValueError as exc:
        raise ValueError("DRAFT_INPUT_INVALID") from exc
    if len({item.claim_id for item in bindings}) != len(bindings):
        raise ValueError("DRAFT_INPUT_INVALID")
    sources = {item.source_id: item for item in store.list_sources(run_id)}
    evidence = {item.evidence_id: item for item in store.list_evidence(run_id)}
    # Registered server law digests are opaque references, not phone numbers.
    # Exclude only these exact structured fields; prose and unknown IDs still
    # undergo the unchanged privacy screen and all bindings are checked below.
    opaque_ids, _ = _registered_law_digests(sources, evidence)
    privacy_bindings = json.loads(json.dumps(claim_bindings, ensure_ascii=False))
    for privacy_binding in privacy_bindings:
        privacy_binding["evidence_ids"] = [
            "registered-law-digest" if key in opaque_ids else key
            for key in privacy_binding.get("evidence_ids", [])
        ]
        for occurrence in privacy_binding.get("citation_occurrences", []):
            if occurrence["evidence_id"] in opaque_ids:
                occurrence["evidence_id"] = "registered-law-digest"
    privacy = screen_answer_output(
        json.dumps({"draft": answer_text, "bindings": privacy_bindings}, ensure_ascii=False)
    )
    base: dict[str, Any] = {
        "schema_version": "alr-tw.draft-workspace/v1",
        "workflow_guidance": {"drafting": drafting_guidance()},
        "run_id": run_id,
        "presentation_mode": "exploratory_internal_only",
        "safe_to_present": False,
        "final_answer_authorized": False,
        "advisory_only": True,
        "advisory_disclaimer": "內部研究草稿；來源核對不等於主張成立，未標註文字均待查證。",
        "draft_text": None,
        "annotations": [],
        "default_label": "unverified_inference",
        "privacy_status": privacy.status,
    }
    if not privacy.allowed:
        base["blockers"] = ["ANSWER_CONTAINS_SENSITIVE_DATA"]
        return base
    if any(binding.claim_text not in answer_text for binding in bindings):
        raise ValueError("DRAFT_CLAIM_NOT_IN_TEXT")
    # Reuse the strict gate's role and claim mappings, without invoking or
    # persisting a final validation decision.
    from alr_tw.research.service import (
        ResearchService, _claims_for_validation, _citation_occurrence_reasons,
        _verified_citation_annotations,
    )

    citation_reasons = _citation_occurrence_reasons(
        answer_text, bindings, evidence_by_id=evidence, sources=sources,
    )
    citation_annotations = _verified_citation_annotations(answer_text, bindings, citation_reasons)

    segments = [
        ResearchService._claim_segment(
            span, sources[span.source_id].source_tier.value,
            sources[span.source_id].material_type.value,
            sources[span.source_id].official_url, sources[span.source_id].verified_at,
        )
        for span in evidence.values()
        if span.eligible_for_claim_support and span.source_id in sources
        and sources[span.source_id].trust_status == TrustStatus.EVIDENCE_ELIGIBLE
        and sources[span.source_id].expires_at > timestamp
    ]
    support, summary, _ = check_claim_support(
        answer=answer_text, claims=_claims_for_validation(
            answer_text, bindings, citation_annotations=citation_annotations,
        ),
        segments=segments, require_explicit_bindings=True,
    )
    support_by_id = {item.claim_id: item for item in support[:len(bindings)]}
    actions = {
        "supported": "規則檢查通過；核對引文位置、議題涵蓋與適用時間，再執行嚴格驗證。",
        "role_error": "更換符合主張角色的段落；當事人說法不能標成法院見解。",
        "overstated": "補回原文例外、條件與個案範圍，再重新檢視。",
        "contradicted": "逐句比較相反內容；修正主張或選取正確證據。",
        "unsupported": "縮小主張範圍或補上同次研究中的直接證據。",
    }
    annotations = []
    for binding in bindings:
        # Labels are server derived, never accepted from the caller. A verified
        # reference does not imply that it supports this claim or its role.
        references = []
        for evidence_id in binding.evidence_ids:
            span = evidence.get(evidence_id)
            source = sources.get(span.source_id) if span is not None else None
            verified = bool(
                span
                and source
                and source.expires_at > timestamp
                and source.trust_status == TrustStatus.EVIDENCE_ELIGIBLE
                and span.eligible_for_claim_support
            )
            references.append(
                {
                    "evidence_id": evidence_id,
                    "status": "source_verified" if verified else "unverified",
                    "claim_support_authorized": False,
                }
            )
        if binding.claim_text not in answer_text:
            raise ValueError("DRAFT_CLAIM_NOT_IN_TEXT")
        checked = support_by_id[binding.claim_id]
        status = checked.support_status.value
        ranges, ranges_truncated = _text_ranges(answer_text, binding.claim_text)
        annotations.append(
            {
                "claim_id": binding.claim_id,
                "claim_text": binding.claim_text,
                "label": "unverified_inference",
                "references": references,
                "support_status": status,
                "support_label": "support_candidate" if status == "supported" else status,
                "risk_flags": checked.risk_flags,
                "review_required": checked.review_required,
                "text_ranges": ranges,
                "text_ranges_truncated": ranges_truncated,
                "next_action": actions.get(status, "補足證據並核對範圍，必要時交由人工複核。"),
            }
        )
    base.update(
        draft_text=answer_text, annotations=annotations, blockers=sorted(set(citation_reasons)),
        citation_preparation=prepare_citations(
            answer_text, bindings, evidence=evidence, sources=sources, now=timestamp,
        ),
        support_summary=summary.model_dump(mode="json"),
        unbound_claim_count=len(support) - len(bindings),
        revision_steps=["依 annotations 修正草稿及證據綁定。", "重新執行 review-draft。",
                        "使用新的 operation-id 執行 complete-research 或 validate-draft。"],
    )
    return base
