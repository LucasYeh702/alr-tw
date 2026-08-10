"""Opaque, provider-neutral receipts for a research data snapshot.

The public runtime must be able to prove that one research run did not mix
different generations of a provider without exposing the provider's storage
layout.  A receipt therefore contains only opaque identifiers and bounded
metadata.  It deliberately has no path, manifest, catalog, database, or
deployment fields.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_OPAQUE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
_DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"


class SnapshotReceiptStatus(str, Enum):
    """State of a provider snapshot receipt as assessed by the server."""

    VERIFIED = "verified"
    UNKNOWN = "unknown"
    STALE = "stale"
    INCONSISTENT = "inconsistent"


class SnapshotConsistency(str, Enum):
    """Consistency state used by finalization, not a source-trust decision."""

    CONSISTENT = "consistent"
    LEGACY_NO_RECEIPT = "legacy_no_receipt"
    MISMATCH = "mismatch"
    FOREIGN_RECEIPT = "foreign_receipt"


class ProviderSnapshotReceipt(BaseModel):
    """Server-issued opaque snapshot reference.

    ``issuer`` and ``server_owned`` are descriptive invariants.  They are not
    treated as proof when supplied by a caller: verification code must compare
    the complete receipt to the server-owned receipt set for the same run.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.provider-snapshot-receipt/v1"] = (
        "alr-tw.provider-snapshot-receipt/v1"
    )
    receipt_id: str = Field(pattern=_OPAQUE_ID_PATTERN)
    provider_id: str = Field(pattern=_OPAQUE_ID_PATTERN)
    snapshot_id: str = Field(pattern=_OPAQUE_ID_PATTERN)
    generation: str = Field(pattern=_OPAQUE_ID_PATTERN)
    status: SnapshotReceiptStatus = SnapshotReceiptStatus.VERIFIED
    issued_at: datetime
    expires_at: datetime | None = None
    content_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    issuer: Literal["alr-tw.server"] = "alr-tw.server"
    server_owned: Literal[True] = True

    @field_validator("receipt_id", "provider_id", "snapshot_id", "generation")
    @classmethod
    def reject_private_layout_markers(cls, value: str) -> str:
        """Keep receipt identifiers opaque and free of deployment details."""

        lowered = value.casefold()
        forbidden = (
            "manifest",
            "catalog",
            "sqlite",
            "chroma",
            "postgres",
            "deployment",
            "topology",
            "data/",
            "private/",
        )
        if any(marker in lowered for marker in forbidden):
            raise ValueError("snapshot receipt identifiers must remain opaque")
        return value

    @model_validator(mode="after")
    def validate_receipt(self) -> ProviderSnapshotReceipt:
        if self.issued_at.tzinfo is None or self.issued_at.utcoffset() is None:
            raise ValueError("snapshot receipt issued_at must be timezone-aware")
        if self.expires_at is not None:
            if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
                raise ValueError("snapshot receipt expires_at must be timezone-aware")
            if self.expires_at <= self.issued_at:
                raise ValueError("snapshot receipt expires_at must follow issued_at")
        if self.status in {SnapshotReceiptStatus.STALE, SnapshotReceiptStatus.INCONSISTENT}:
            # A stale or inconsistent receipt may be retained for audit, but it
            # can never be interpreted as an eligible snapshot by finalization.
            return self
        return self

    def is_current(self, *, now: datetime | None = None) -> bool:
        """Return whether the receipt is currently usable by a server gate."""

        timestamp = now or datetime.now(UTC)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        if self.status is not SnapshotReceiptStatus.VERIFIED:
            return False
        # A server receipt cannot attest to data issued in the future.  This
        # is deliberately fail-closed: clock skew is not silently tolerated
        # by the public contract, and callers can retry once clocks converge.
        if self.issued_at > timestamp:
            return False
        return self.expires_at is None or self.expires_at > timestamp


class SnapshotConsistencyResult(BaseModel):
    """Deterministic assessment of receipts supplied for one research run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.snapshot-consistency/v1"] = (
        "alr-tw.snapshot-consistency/v1"
    )
    status: SnapshotConsistency
    consistent: bool
    receipt_count: int = Field(ge=0)
    reason_codes: list[str] = Field(default_factory=list, max_length=32)
    provider_generations: dict[str, str] = Field(default_factory=dict)


def _receipt_signature(receipt: ProviderSnapshotReceipt) -> tuple[object, ...]:
    """Return a complete, order-independent receipt identity."""

    return (
        receipt.schema_version,
        receipt.receipt_id,
        receipt.provider_id,
        receipt.snapshot_id,
        receipt.generation,
        receipt.status.value,
        receipt.issued_at.astimezone(UTC).isoformat(),
        (
            receipt.expires_at.astimezone(UTC).isoformat()
            if receipt.expires_at is not None
            else None
        ),
        receipt.content_digest,
        receipt.issuer,
        receipt.server_owned,
    )


def _append_scope_diagnostics(
    values: Sequence[ProviderSnapshotReceipt],
    reasons: list[str],
    *,
    timestamp: datetime,
    server_owned: bool,
) -> dict[str, str]:
    """Inspect one receipt set, including the server-owned set itself."""

    duplicate_code = (
        "SNAPSHOT_SERVER_RECEIPT_ID_DUPLICATED"
        if server_owned
        else "SNAPSHOT_RECEIPT_ID_DUPLICATED"
    )
    current_code = (
        "SNAPSHOT_SERVER_RECEIPT_NOT_CURRENT"
        if server_owned
        else "SNAPSHOT_RECEIPT_NOT_CURRENT"
    )
    generation_code = (
        "SNAPSHOT_SERVER_GENERATION_MISMATCH"
        if server_owned
        else "SNAPSHOT_GENERATION_MISMATCH"
    )
    if len({item.receipt_id for item in values}) != len(values):
        reasons.append(duplicate_code)

    generations: dict[str, str] = {}
    pairs_by_provider: dict[str, set[tuple[str, str]]] = {}
    for item in values:
        if not item.is_current(now=timestamp):
            reasons.append(current_code)
        pair = (item.snapshot_id, item.generation)
        pairs_by_provider.setdefault(item.provider_id, set()).add(pair)
        generations.setdefault(item.provider_id, item.generation)
    if any(len(pairs) > 1 for pairs in pairs_by_provider.values()):
        reasons.append(generation_code)
    return generations


def assess_snapshot_consistency(
    receipts: Sequence[ProviderSnapshotReceipt],
    *,
    server_receipts: Sequence[ProviderSnapshotReceipt] | None = None,
    now: datetime | None = None,
) -> SnapshotConsistencyResult:
    """Assess receipt consistency without trusting caller-provided attestations.

    Receipts are compared per provider.  Different providers naturally have
    different opaque snapshot IDs; a mismatch is only reported when one
    provider appears with multiple snapshot/generation pairs.  If
    ``server_receipts`` is supplied, every receipt must exactly match a
    server-owned receipt for the same run.
    """

    values = list(receipts)
    server_values = list(server_receipts) if server_receipts is not None else None
    timestamp = now or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if not values and (server_values is None or not server_values):
        return SnapshotConsistencyResult(
            status=SnapshotConsistency.LEGACY_NO_RECEIPT,
            consistent=False,
            receipt_count=0,
            reason_codes=["SNAPSHOT_RECEIPT_MISSING_LEGACY"],
        )

    reasons: list[str] = []
    generations = _append_scope_diagnostics(
        values,
        reasons,
        timestamp=timestamp,
        server_owned=False,
    )

    if server_values is None:
        # A caller-provided receipt is only a locator.  Without the server's
        # run-bound receipt set there is no authority to certify it, even if
        # all opaque fields happen to be internally consistent.
        reasons.append("SNAPSHOT_RECEIPT_SERVER_BINDING_REQUIRED")
    else:
        server_by_id = {item.receipt_id: item for item in server_values}
        _append_scope_diagnostics(
            server_values,
            reasons,
            timestamp=timestamp,
            server_owned=True,
        )
        for item in values:
            owned = server_by_id.get(item.receipt_id)
            if owned is None or owned != item:
                reasons.append("SNAPSHOT_RECEIPT_NOT_SERVER_OWNED")

        provided_set = Counter(_receipt_signature(item) for item in values)
        server_set = Counter(_receipt_signature(item) for item in server_values)
        if provided_set != server_set:
            reasons.append("SNAPSHOT_RECEIPT_SET_MISMATCH")
            if server_set - provided_set:
                reasons.append("SNAPSHOT_RECEIPT_SERVER_SET_MISSING")
            if provided_set - server_set:
                reasons.append("SNAPSHOT_RECEIPT_SERVER_SET_EXTRA")

    unique_reasons = sorted(set(reasons))
    if {
        "SNAPSHOT_RECEIPT_NOT_SERVER_OWNED",
        "SNAPSHOT_RECEIPT_SERVER_BINDING_REQUIRED",
        "SNAPSHOT_RECEIPT_SET_MISMATCH",
        "SNAPSHOT_RECEIPT_SERVER_SET_MISSING",
        "SNAPSHOT_RECEIPT_SERVER_SET_EXTRA",
    } & set(unique_reasons):
        status = SnapshotConsistency.FOREIGN_RECEIPT
    elif "SNAPSHOT_GENERATION_MISMATCH" in unique_reasons:
        status = SnapshotConsistency.MISMATCH
    elif unique_reasons:
        status = SnapshotConsistency.MISMATCH
    else:
        status = SnapshotConsistency.CONSISTENT
    return SnapshotConsistencyResult(
        status=status,
        consistent=status is SnapshotConsistency.CONSISTENT,
        receipt_count=len(values),
        reason_codes=unique_reasons,
        provider_generations=generations,
    )
