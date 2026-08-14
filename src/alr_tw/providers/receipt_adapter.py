"""Receipt-aware provider adapter for deployer-owned server gates.

The adapter never creates a receipt. A deployer may inject a server-owned
issuer, but the receipt is eligible only after the caller also supplies the
run-bound server receipt set to the conformance validator.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from alr_tw.contracts.provider_conformance import (
    ProviderConformanceRequest,
    ProviderConformanceResult,
    ProviderConformanceStatus,
    validate_provider_conformance,
)
from alr_tw.contracts.provider_snapshot import ProviderSnapshotReceipt
from alr_tw.contracts.providers import ProviderResult
from alr_tw.contracts.sources import EvidenceSpan, SourceRecord


ProviderReceiptIssuer = Callable[
    [str, Sequence[str], Sequence[str]],
    Sequence[ProviderSnapshotReceipt],
]


class ReceiptAwareProviderEnvelope(BaseModel):
    """Provider output plus server-owned conformance and receipt projection."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "alr-tw.receipt-aware-provider/v1"
    result: ProviderResult
    conformance: ProviderConformanceResult
    snapshot_receipts: list[ProviderSnapshotReceipt] = Field(default_factory=list, max_length=64)
    receipt_issuance_attempted: bool = False
    ordinary_eligible: bool = False


class ReceiptAwareProviderAdapter:
    """Wrap a provider result without changing its candidate/evidence roles."""

    def __init__(
        self,
        *,
        request: ProviderConformanceRequest,
        receipt_issuer: ProviderReceiptIssuer | None = None,
    ) -> None:
        self._request = request
        self._receipt_issuer = receipt_issuer

    def adapt(
        self,
        result: ProviderResult,
        *,
        server_source_ids: Sequence[str] | None,
        server_evidence_ids: Sequence[str] | None,
        server_sources: Mapping[str, SourceRecord] | None = None,
        server_evidence: Mapping[str, EvidenceSpan] | None = None,
        server_receipts: Sequence[ProviderSnapshotReceipt] | None = None,
        now: datetime | None = None,
    ) -> ReceiptAwareProviderEnvelope:
        receipts: Sequence[ProviderSnapshotReceipt] = ()
        attempted = self._receipt_issuer is not None
        issuance_reason: str | None = None
        if self._receipt_issuer is not None:
            try:
                issued = self._receipt_issuer(
                    result.provider_id,
                    tuple(result.source_ids),
                    tuple(result.evidence_ids),
                )
                receipts = tuple(
                    item
                    if isinstance(item, ProviderSnapshotReceipt)
                    else ProviderSnapshotReceipt.model_validate(item)
                    for item in issued
                )
            except Exception as exc:
                receipts = ()
                issuance_reason = f"PROVIDER_SNAPSHOT_RECEIPT_ISSUANCE_FAILED:{type(exc).__name__}"
        conformance = validate_provider_conformance(
            result,
            request=self._request,
            server_source_ids=server_source_ids,
            server_evidence_ids=server_evidence_ids,
            server_sources=server_sources,
            server_evidence=server_evidence,
            receipts=receipts,
            server_receipts=server_receipts,
            now=now,
        )
        if issuance_reason is not None:
            conformance = conformance.model_copy(
                update={
                    "decision": (
                        ProviderConformanceStatus.BLOCKED
                        if conformance.decision is ProviderConformanceStatus.BLOCKED
                        else ProviderConformanceStatus.QUALIFIED
                    ),
                    "ordinary_eligible": False,
                    "eligible_source_ids": [],
                    "eligible_evidence_ids": [],
                    "absence_claim_allowed": False,
                    "reason_codes": list(
                        dict.fromkeys([*conformance.reason_codes, issuance_reason])
                    ),
                }
            )
        return ReceiptAwareProviderEnvelope(
            result=result,
            conformance=conformance,
            snapshot_receipts=list(receipts),
            receipt_issuance_attempted=attempted,
            ordinary_eligible=conformance.ordinary_eligible,
        )


__all__ = [
    "ProviderReceiptIssuer",
    "ReceiptAwareProviderAdapter",
    "ReceiptAwareProviderEnvelope",
]
