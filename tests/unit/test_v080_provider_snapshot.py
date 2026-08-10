from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from alr_tw.contracts.provider_snapshot import (
    ProviderSnapshotReceipt,
    SnapshotReceiptStatus,
    SnapshotConsistency,
    assess_snapshot_consistency,
)


NOW = datetime(2026, 8, 8, 8, 0, tzinfo=UTC)


def _receipt(
    receipt_id: str = "receipt-1",
    *,
    provider_id: str = "official-law",
    snapshot_id: str = "snapshot-1",
    generation: str = "generation-1",
    issued_at: datetime = NOW,
    expires_at: datetime | None = None,
) -> ProviderSnapshotReceipt:
    return ProviderSnapshotReceipt(
        receipt_id=receipt_id,
        provider_id=provider_id,
        snapshot_id=snapshot_id,
        generation=generation,
        issued_at=issued_at,
        expires_at=expires_at or NOW + timedelta(hours=1),
    )


def test_receipt_is_opaque_and_does_not_allow_private_layout_markers():
    with pytest.raises(ValidationError):
        _receipt(snapshot_id="private-sqlite-manifest")


def test_consistency_requires_server_owned_receipt_binding():
    receipt = _receipt()
    result = assess_snapshot_consistency([receipt], now=NOW)
    assert not result.consistent
    assert result.status is SnapshotConsistency.FOREIGN_RECEIPT
    assert "SNAPSHOT_RECEIPT_SERVER_BINDING_REQUIRED" in result.reason_codes

    bound = assess_snapshot_consistency([receipt], server_receipts=[receipt], now=NOW)
    assert bound.consistent
    assert bound.status is SnapshotConsistency.CONSISTENT


def test_receipt_sets_must_match_exactly_and_order_is_irrelevant():
    first = _receipt()
    second = _receipt("receipt-2", provider_id="official-judgment")

    equal_reordered = assess_snapshot_consistency(
        [second, first], server_receipts=[first, second], now=NOW
    )
    assert equal_reordered.consistent
    assert equal_reordered.status is SnapshotConsistency.CONSISTENT

    missing_server_receipt = assess_snapshot_consistency(
        [first], server_receipts=[first, second], now=NOW
    )
    assert not missing_server_receipt.consistent
    assert "SNAPSHOT_RECEIPT_SET_MISMATCH" in missing_server_receipt.reason_codes
    assert "SNAPSHOT_RECEIPT_SERVER_SET_MISSING" in missing_server_receipt.reason_codes

    server_only_extra = assess_snapshot_consistency(
        [first, second], server_receipts=[first], now=NOW
    )
    assert not server_only_extra.consistent
    assert "SNAPSHOT_RECEIPT_SERVER_SET_EXTRA" in server_only_extra.reason_codes


def test_server_receipt_set_integrity_is_checked_independently():
    first = _receipt()
    mixed = _receipt("receipt-2", snapshot_id="snapshot-2", generation="generation-2")
    mixed_result = assess_snapshot_consistency(
        [first, mixed], server_receipts=[first, mixed], now=NOW
    )
    assert not mixed_result.consistent
    assert "SNAPSHOT_SERVER_GENERATION_MISMATCH" in mixed_result.reason_codes

    duplicate_result = assess_snapshot_consistency(
        [first, first], server_receipts=[first, first], now=NOW
    )
    assert not duplicate_result.consistent
    assert "SNAPSHOT_SERVER_RECEIPT_ID_DUPLICATED" in duplicate_result.reason_codes

    stale = _receipt().model_copy(update={"status": SnapshotReceiptStatus.STALE})
    stale_result = assess_snapshot_consistency(
        [stale], server_receipts=[stale], now=NOW
    )
    assert not stale_result.consistent
    assert "SNAPSHOT_SERVER_RECEIPT_NOT_CURRENT" in stale_result.reason_codes


def test_same_provider_generation_mismatch_is_fail_closed():
    first = _receipt()
    second = _receipt("receipt-2", snapshot_id="snapshot-2", generation="generation-2")
    result = assess_snapshot_consistency(
        [first, second], server_receipts=[first, second], now=NOW
    )
    assert not result.consistent
    assert result.status is SnapshotConsistency.MISMATCH
    assert "SNAPSHOT_GENERATION_MISMATCH" in result.reason_codes


def test_legacy_missing_receipt_is_explicitly_unknown():
    result = assess_snapshot_consistency([], server_receipts=[], now=NOW)
    assert not result.consistent
    assert result.status is SnapshotConsistency.LEGACY_NO_RECEIPT
    assert result.reason_codes == ["SNAPSHOT_RECEIPT_MISSING_LEGACY"]


def test_expired_receipt_is_not_current():
    receipt = _receipt(
        issued_at=NOW - timedelta(hours=2),
        expires_at=NOW - timedelta(seconds=1),
    )
    result = assess_snapshot_consistency([receipt], server_receipts=[receipt], now=NOW)
    assert not result.consistent
    assert "SNAPSHOT_RECEIPT_NOT_CURRENT" in result.reason_codes


def test_future_issued_receipt_is_not_current():
    receipt = _receipt(issued_at=NOW + timedelta(seconds=1))
    result = assess_snapshot_consistency(
        [receipt], server_receipts=[receipt], now=NOW
    )
    assert not result.consistent
    assert "SNAPSHOT_RECEIPT_NOT_CURRENT" in result.reason_codes
    assert "SNAPSHOT_SERVER_RECEIPT_NOT_CURRENT" in result.reason_codes
