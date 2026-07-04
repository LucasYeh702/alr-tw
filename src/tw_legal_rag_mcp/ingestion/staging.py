from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from ..contracts import AdapterResult, SourceManifest


def mark_staging(source_id: str) -> dict[str, str]:
    return {"source_id": source_id, "state": "staging"}


def _synthetic_staging_manifest() -> SourceManifest:
    return SourceManifest(
        provider="Synthetic Staging Source",
        dataset_name="synthetic-staging-demo",
        dataset_version="v0.4",
        source_url="https://example.test/synthetic-staging",
        license_name="Synthetic demo fixture",
        attribution_text="Synthetic staging data generated for this reference repository.",
        retrieved_at="2026-01-01T00:00:00Z",
        terms_reviewed_at="2026-01-01T00:00:00Z",
        source_tier="staging",
        redistribution_allowed=True,
    )


def stage_records(
    records: Iterable[Mapping[str, Any]],
    *,
    adapter_name: str = "synthetic_staging_adapter",
    manifest: SourceManifest | None = None,
) -> AdapterResult:
    """Build a public-safe staging result without production tuning parameters."""

    manifest = _synthetic_staging_manifest() if manifest is None else manifest
    staged_records: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        source_id = str(record.get("source_id") or f"synthetic-staging-{index:03d}")
        staged_records.append(
            {
                "source_id": source_id,
                "source_tier": "staging",
                "title": str(record.get("title") or "Synthetic staging record"),
                "text": str(record.get("text") or ""),
                "manifest_id": manifest.dataset_name,
                "state": "staging",
            }
        )
    return AdapterResult(
        adapter_name=adapter_name,
        status="staged",
        manifest=manifest,
        records=staged_records,
    )


class SyntheticStagingAdapter:
    """Illustrative staging adapter skeleton for public integration tests."""

    def load(self) -> AdapterResult:
        return stage_records(
            [
                {
                    "source_id": "synthetic-staging-001",
                    "title": "Synthetic staging record",
                    "text": "Synthetic public-safe staging text for adapter wiring.",
                }
            ]
        )
