"""Verification facade for server-owned finalization decisions.

The contract module owns the immutable models and deterministic posture
builder.  This facade keeps the public verification namespace stable and
provides the structured-refusal projection used by MCP adapters.
"""

from __future__ import annotations

from collections.abc import Sequence

from alr_tw.contracts.finalization import (
    FinalizationContract,
    FinalizationValidationResult,
    StructuredRefusal,
    build_finalization_contract,
    build_finalization_from_run,
    build_structured_refusal,
)
from alr_tw.contracts.provider_snapshot import ProviderSnapshotReceipt
from alr_tw.contracts.research import ResearchRun


def validate_server_finalization(
    contract: FinalizationContract,
    *,
    server_run_id: str,
    server_source_ids: Sequence[str],
    server_evidence_ids: Sequence[str],
    server_snapshot_receipts: Sequence[ProviderSnapshotReceipt] | None = None,
    server_run: ResearchRun | None = None,
    now=None,
) -> FinalizationValidationResult:
    """Validate a finalization envelope against one server-owned run."""

    from alr_tw.contracts.finalization import validate_finalization

    return validate_finalization(
        contract,
        server_run_id=server_run_id,
        server_source_ids=server_source_ids,
        server_evidence_ids=server_evidence_ids,
        server_snapshot_receipts=server_snapshot_receipts,
        server_run=server_run,
        now=now,
    )


def structured_refusal(
    result: FinalizationContract | FinalizationValidationResult,
) -> StructuredRefusal:
    """Return only refusal reasons/actions; never a draft or client proposal."""

    return build_structured_refusal(result)


__all__ = [
    "build_finalization_contract",
    "build_finalization_from_run",
    "structured_refusal",
    "validate_server_finalization",
]
