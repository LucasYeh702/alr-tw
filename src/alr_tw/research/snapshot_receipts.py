"""Server-issued receipts for the exact official material set of one run."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json

from alr_tw.contracts.provider_snapshot import (
    ProviderSnapshotReceipt,
    SnapshotReceiptStatus,
)
from alr_tw.contracts.research import ResearchRun
from alr_tw.contracts.sources import EvidenceSpan, SourceRecord, SourceTier, TrustStatus


_RECEIPT_SOURCE_TIERS = {SourceTier.OFFICIAL, SourceTier.VERIFIED_CACHE}


@dataclass(frozen=True)
class RunSnapshotReceiptCheck:
    """Internal binding result for persisted receipts and current run material."""

    valid: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class _ProviderMaterial:
    provider_id: str
    content_digest: str
    snapshot_id: str
    generation: str
    receipt_id: str
    expires_at: datetime


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _provider_materials(
    run: ResearchRun,
    sources: Sequence[SourceRecord],
    evidence: Sequence[EvidenceSpan],
    *,
    now: datetime,
) -> dict[str, _ProviderMaterial]:
    """Describe the current official/verified-cache material without raw text."""

    run_source_ids = set(run.source_ids)
    run_evidence_ids = set(run.evidence_ids)
    eligible_sources = {
        item.source_id: item
        for item in sources
        if item.source_id in run_source_ids
        and item.source_tier in _RECEIPT_SOURCE_TIERS
        and item.trust_status is TrustStatus.EVIDENCE_ELIGIBLE
        and item.expires_at > now
    }
    evidence_by_provider: dict[str, list[EvidenceSpan]] = defaultdict(list)
    sources_by_provider: dict[str, list[SourceRecord]] = defaultdict(list)
    for item in evidence:
        source = eligible_sources.get(item.source_id)
        if (
            source is not None
            and item.evidence_id in run_evidence_ids
            and item.eligible_for_claim_support
        ):
            evidence_by_provider[source.provider_id].append(item)
    for source in eligible_sources.values():
        if evidence_by_provider.get(source.provider_id):
            sources_by_provider[source.provider_id].append(source)

    materials: dict[str, _ProviderMaterial] = {}
    for provider_id in sorted(sources_by_provider):
        provider_sources = sorted(sources_by_provider[provider_id], key=lambda item: item.source_id)
        provider_source_ids = {item.source_id for item in provider_sources}
        provider_evidence = sorted(
            (
                item
                for item in evidence_by_provider[provider_id]
                if item.source_id in provider_source_ids
            ),
            key=lambda item: item.evidence_id,
        )
        payload = {
            "provider_id": provider_id,
            "sources": [
                {
                    "source_id": item.source_id,
                    "source_version_id": item.source_version_id,
                    "content_hash": item.content_hash,
                    "normalized_content_hash": item.normalized_content_hash,
                    "verified_at": (
                        item.verified_at.isoformat() if item.verified_at is not None else None
                    ),
                    "expires_at": item.expires_at.isoformat(),
                }
                for item in provider_sources
            ],
            "evidence": [
                {
                    "evidence_id": item.evidence_id,
                    "source_id": item.source_id,
                    "section_id": item.section_id,
                    "section_type": item.section_type.value,
                    "text_hash": item.text_hash,
                }
                for item in provider_evidence
            ],
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = f"sha256:{_sha256(canonical)}"
        run_provider_key = _sha256(f"{run.run_id}\0{provider_id}")
        receipt_key = _sha256(f"{run.run_id}\0{provider_id}\0{digest}")
        materials[provider_id] = _ProviderMaterial(
            provider_id=provider_id,
            content_digest=digest,
            snapshot_id=f"snap:{digest[7:39]}",
            generation=f"gen:{run_provider_key[:32]}",
            receipt_id=f"rcpt:{receipt_key[:32]}",
            expires_at=min(run.expires_at, *(item.expires_at for item in provider_sources)),
        )
    return materials


def issue_run_snapshot_receipts(
    run: ResearchRun,
    sources: Sequence[SourceRecord],
    evidence: Sequence[EvidenceSpan],
    *,
    existing: Sequence[ProviderSnapshotReceipt] = (),
    now: datetime,
) -> list[ProviderSnapshotReceipt]:
    """Issue one current, run-bound receipt for each eligible server provider."""

    materials = _provider_materials(run, sources, evidence, now=now)
    existing_by_provider = {item.provider_id: item for item in existing}
    receipts: list[ProviderSnapshotReceipt] = []
    for provider_id, material in materials.items():
        previous = existing_by_provider.get(provider_id)
        if (
            previous is not None
            and previous.receipt_id == material.receipt_id
            and previous.snapshot_id == material.snapshot_id
            and previous.generation == material.generation
            and previous.content_digest == material.content_digest
            and previous.expires_at == material.expires_at
            and previous.is_current(now=now)
        ):
            receipts.append(previous)
            continue
        receipts.append(
            ProviderSnapshotReceipt(
                receipt_id=material.receipt_id,
                provider_id=provider_id,
                snapshot_id=material.snapshot_id,
                generation=material.generation,
                issued_at=now,
                expires_at=material.expires_at,
                content_digest=material.content_digest,
            )
        )
    return receipts


def check_run_snapshot_receipts(
    run: ResearchRun,
    sources: Sequence[SourceRecord],
    evidence: Sequence[EvidenceSpan],
    receipts: Sequence[ProviderSnapshotReceipt],
    *,
    now: datetime,
) -> RunSnapshotReceiptCheck:
    """Recompute receipt bindings so persisted fields cannot self-certify."""

    materials = _provider_materials(run, sources, evidence, now=now)
    values = list(receipts)
    reasons: list[str] = []
    if len({item.provider_id for item in values}) != len(values):
        reasons.append("RUN_SNAPSHOT_RECEIPT_PROVIDER_DUPLICATED")
    by_provider = {item.provider_id: item for item in values}
    if set(by_provider) != set(materials):
        reasons.append("RUN_SNAPSHOT_RECEIPT_PROVIDER_SET_MISMATCH")
    for provider_id, material in materials.items():
        receipt = by_provider.get(provider_id)
        if receipt is None:
            reasons.append("RUN_SNAPSHOT_RECEIPT_MISSING")
            continue
        if (
            receipt.receipt_id != material.receipt_id
            or receipt.snapshot_id != material.snapshot_id
            or receipt.generation != material.generation
            or receipt.content_digest != material.content_digest
            or receipt.expires_at != material.expires_at
        ):
            reasons.append("RUN_SNAPSHOT_RECEIPT_MATERIAL_MISMATCH")
        if not receipt.is_current(now=now):
            reasons.append("RUN_SNAPSHOT_RECEIPT_NOT_CURRENT")
    return RunSnapshotReceiptCheck(
        valid=not reasons,
        reason_codes=tuple(sorted(set(reasons))),
    )


def mark_receipts_inconsistent(
    receipts: Sequence[ProviderSnapshotReceipt],
) -> list[ProviderSnapshotReceipt]:
    """Project a corrupt/mixed server set into the existing fail-closed gate."""

    return [
        item.model_copy(update={"status": SnapshotReceiptStatus.INCONSISTENT}) for item in receipts
    ]


__all__ = [
    "RunSnapshotReceiptCheck",
    "check_run_snapshot_receipts",
    "issue_run_snapshot_receipts",
    "mark_receipts_inconsistent",
]
