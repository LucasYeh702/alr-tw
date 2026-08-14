from __future__ import annotations

from datetime import UTC, datetime, timedelta

from alr_tw.contracts.provider_conformance import (
    ProviderConformanceRequest,
    ProviderConformanceStatus,
    ProviderRole,
    validate_provider_conformance,
)
from alr_tw.contracts.provider_snapshot import ProviderSnapshotReceipt
from alr_tw.contracts.providers import (
    CandidateIdentity,
    ProviderCandidate,
    ProviderResult,
    ProviderResultStatus,
)
from alr_tw.contracts.sources import (
    EvidenceSpan,
    MaterialType,
    SourceRecord,
    SourceTier,
    TrustStatus,
)
from alr_tw.providers.receipt_adapter import ReceiptAwareProviderAdapter


NOW = datetime(2026, 8, 14, 9, 0, tzinfo=UTC)
PROVIDER = "official-law-provider"
SOURCE_ID = "source-law-1"
EVIDENCE_ID = "evidence-law-1"
DIGEST = "sha256:" + ("a" * 64)


def _source(*, expires_at: datetime | None = None, trust: TrustStatus = TrustStatus.EVIDENCE_ELIGIBLE):
    return SourceRecord(
        source_id=SOURCE_ID,
        source_key="law:184",
        source_version_id="law:184:v1",
        material_type=MaterialType.LAW,
        provider_id=PROVIDER,
        source_tier=SourceTier.OFFICIAL,
        trust_status=trust,
        official_identifier="民法第184條",
        official_url="https://example.test/law/184",
        citation="民法第184條",
        fetched_at=NOW - timedelta(minutes=2),
        verified_at=NOW - timedelta(minutes=1),
        expires_at=expires_at or NOW + timedelta(hours=1),
        content_hash=DIGEST,
        normalized_content_hash=DIGEST,
        normalized_text="因故意或過失，不法侵害他人之權利者，負損害賠償責任。",
    )


def _evidence() -> EvidenceSpan:
    return EvidenceSpan.from_exact_text(
        evidence_id=EVIDENCE_ID,
        source_id=SOURCE_ID,
        section_id="section-1",
        section_type="law_text",
        exact_text="因故意或過失，不法侵害他人之權利者，負損害賠償責任。",
        eligible_for_claim_support=True,
    )


def _receipt() -> ProviderSnapshotReceipt:
    return ProviderSnapshotReceipt(
        receipt_id="receipt-law-1",
        provider_id=PROVIDER,
        snapshot_id="snapshot-law-1",
        generation="generation-law-1",
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
        content_digest=DIGEST,
    )


def _request(
    *,
    role: ProviderRole = ProviderRole.OFFICIAL_VERIFIER,
    scope: str | None = "official-law-scope",
    require_receipt: bool = False,
) -> ProviderConformanceRequest:
    return ProviderConformanceRequest(
        provider_id=PROVIDER,
        role=role,
        bounded_scope=scope,
        expected_material_types=["law"],
        require_snapshot_receipt=require_receipt,
    )


def _found(*, source_ids: list[str] | None = None, evidence_ids: list[str] | None = None):
    return ProviderResult(
        status=ProviderResultStatus.FOUND,
        provider_id=PROVIDER,
        source_ids=source_ids or [],
        evidence_ids=evidence_ids or [],
        coverage_complete=True,
    )


def test_official_result_with_server_receipt_is_conforming() -> None:
    source = _source()
    evidence = _evidence()
    receipt = _receipt()
    result = _found(source_ids=[SOURCE_ID], evidence_ids=[EVIDENCE_ID])
    decision = validate_provider_conformance(
        result,
        request=_request(require_receipt=True),
        server_source_ids=[SOURCE_ID],
        server_evidence_ids=[EVIDENCE_ID],
        server_sources={SOURCE_ID: source},
        server_evidence={EVIDENCE_ID: evidence},
        receipts=[receipt],
        server_receipts=[receipt],
        now=NOW,
    )
    assert decision.decision is ProviderConformanceStatus.CONFORMING
    assert decision.ordinary_eligible is True
    assert decision.eligible_source_ids == [SOURCE_ID]


def test_live_source_without_receipt_is_qualified_not_ordinary() -> None:
    decision = validate_provider_conformance(
        _found(source_ids=[SOURCE_ID]),
        request=_request(),
        server_source_ids=[SOURCE_ID],
        server_evidence_ids=[],
        server_sources={SOURCE_ID: _source()},
        server_evidence={},
        now=NOW,
    )
    assert decision.decision is ProviderConformanceStatus.QUALIFIED
    assert decision.ordinary_eligible is False
    assert "PROVIDER_SNAPSHOT_RECEIPT_MISSING" in decision.reason_codes


def test_foreign_source_reference_is_blocked_even_if_payload_is_forged() -> None:
    result = _found(source_ids=["foreign-source"])
    decision = validate_provider_conformance(
        result,
        request=_request(),
        server_source_ids=[SOURCE_ID],
        server_evidence_ids=[],
        server_sources={SOURCE_ID: _source()},
        server_evidence={},
        now=NOW,
    )
    assert decision.decision is ProviderConformanceStatus.BLOCKED
    assert "PROVIDER_SOURCE_NOT_SERVER_BOUND" in decision.reason_codes


def test_stale_or_untrusted_server_source_is_blocked() -> None:
    stale = _source(expires_at=NOW - timedelta(seconds=1))
    decision = validate_provider_conformance(
        _found(source_ids=[SOURCE_ID]),
        request=_request(),
        server_source_ids=[SOURCE_ID],
        server_evidence_ids=[],
        server_sources={SOURCE_ID: stale},
        server_evidence={},
        now=NOW,
    )
    assert decision.decision is ProviderConformanceStatus.BLOCKED
    assert "PROVIDER_SOURCE_STALE" in decision.reason_codes


def test_future_server_source_timestamp_is_blocked() -> None:
    future = _source()
    future = future.model_copy(
        update={
            "fetched_at": NOW + timedelta(minutes=1),
            "verified_at": NOW + timedelta(minutes=1),
        }
    )
    decision = validate_provider_conformance(
        _found(source_ids=[SOURCE_ID]),
        request=_request(),
        server_source_ids=[SOURCE_ID],
        server_evidence_ids=[],
        server_sources={SOURCE_ID: future},
        server_evidence={},
        now=NOW,
    )
    assert decision.decision is ProviderConformanceStatus.BLOCKED
    assert "PROVIDER_SOURCE_TIMESTAMP_FUTURE" in decision.reason_codes


def test_candidate_only_provider_never_becomes_conforming() -> None:
    candidate = ProviderCandidate(
        candidate_id="candidate-1",
        provider_id="candidate-provider",
        official_identifier="TPAA,100,判,1,2026,1",
        identity=CandidateIdentity(formal_citation="最高行政法院判決"),
    )
    result = ProviderResult(
        status=ProviderResultStatus.FOUND,
        provider_id="candidate-provider",
        candidates=[candidate],
        coverage_complete=True,
    )
    request = ProviderConformanceRequest(
        provider_id="candidate-provider",
        role=ProviderRole.CANDIDATE_ONLY,
        bounded_scope="candidate scope",
    )
    decision = validate_provider_conformance(
        result,
        request=request,
        server_source_ids=[],
        server_evidence_ids=[],
        now=NOW,
    )
    assert decision.decision is ProviderConformanceStatus.QUALIFIED
    assert decision.ordinary_eligible is False


def test_candidate_role_cannot_submit_source_ids() -> None:
    decision = validate_provider_conformance(
        _found(source_ids=[SOURCE_ID]),
        request=ProviderConformanceRequest(
            provider_id=PROVIDER,
            role=ProviderRole.CANDIDATE_ONLY,
            bounded_scope="candidate scope",
        ),
        server_source_ids=[SOURCE_ID],
        server_evidence_ids=[],
        server_sources={SOURCE_ID: _source()},
        server_evidence={},
        now=NOW,
    )
    assert decision.decision is ProviderConformanceStatus.BLOCKED
    assert "PROVIDER_CANDIDATE_PROMOTION_FORBIDDEN" in decision.reason_codes


def test_clean_bounded_not_found_allows_only_scoped_absence() -> None:
    result = ProviderResult(
        status=ProviderResultStatus.NOT_FOUND,
        provider_id=PROVIDER,
        coverage_complete=True,
    )
    decision = validate_provider_conformance(
        result,
        request=_request(),
        server_source_ids=[],
        server_evidence_ids=[],
        now=NOW,
    )
    assert decision.decision is ProviderConformanceStatus.CONFORMING
    assert decision.absence_claim_allowed is True
    assert decision.ordinary_eligible is True


def test_not_found_without_bounded_scope_is_qualified() -> None:
    result = ProviderResult(
        status=ProviderResultStatus.NOT_FOUND,
        provider_id=PROVIDER,
        coverage_complete=True,
    )
    decision = validate_provider_conformance(
        result,
        request=_request(scope=None),
        server_source_ids=[],
        server_evidence_ids=[],
        now=NOW,
    )
    assert decision.decision is ProviderConformanceStatus.QUALIFIED
    assert decision.absence_claim_allowed is False


def test_error_is_retry_blocker_and_sensitive_metadata_is_blocked() -> None:
    result = ProviderResult(
        status=ProviderResultStatus.ERROR,
        provider_id=PROVIDER,
        metadata={"api_key": "redacted"},
    )
    decision = validate_provider_conformance(
        result,
        request=_request(),
        server_source_ids=[],
        server_evidence_ids=[],
        now=NOW,
    )
    assert decision.decision is ProviderConformanceStatus.BLOCKED
    assert "PROVIDER_ERROR_RETRY_REQUIRED" in decision.reason_codes
    assert "PROVIDER_METADATA_SENSITIVE_FIELD" in decision.reason_codes


def test_sensitive_scalar_metadata_is_also_blocked() -> None:
    result = ProviderResult(
        status=ProviderResultStatus.NOT_FOUND,
        provider_id=PROVIDER,
        coverage_complete=True,
        metadata={"api_key": 123456},
    )
    decision = validate_provider_conformance(
        result,
        request=_request(),
        server_source_ids=[],
        server_evidence_ids=[],
        now=NOW,
    )
    assert decision.decision is ProviderConformanceStatus.BLOCKED
    assert "PROVIDER_METADATA_SENSITIVE_FIELD" in decision.reason_codes


def test_receipt_aware_adapter_does_not_self_certify_without_server_receipts() -> None:
    source = _source()
    receipt = _receipt()
    adapter = ReceiptAwareProviderAdapter(
        request=_request(require_receipt=True),
        receipt_issuer=lambda *_: [receipt],
    )
    envelope = adapter.adapt(
        _found(source_ids=[SOURCE_ID]),
        server_source_ids=[SOURCE_ID],
        server_evidence_ids=[],
        server_sources={SOURCE_ID: source},
        server_evidence={},
        now=NOW,
    )
    assert envelope.receipt_issuance_attempted is True
    assert envelope.conformance.decision is ProviderConformanceStatus.BLOCKED
    assert envelope.ordinary_eligible is False


def test_receipt_aware_adapter_accepts_only_matching_server_receipt_set() -> None:
    source = _source()
    receipt = _receipt()
    adapter = ReceiptAwareProviderAdapter(
        request=_request(require_receipt=True),
        receipt_issuer=lambda *_: [receipt],
    )
    envelope = adapter.adapt(
        _found(source_ids=[SOURCE_ID]),
        server_source_ids=[SOURCE_ID],
        server_evidence_ids=[],
        server_sources={SOURCE_ID: source},
        server_evidence={},
        server_receipts=[receipt],
        now=NOW,
    )
    assert envelope.conformance.decision is ProviderConformanceStatus.CONFORMING
    assert envelope.ordinary_eligible is True


def test_receipt_issuer_failure_never_upgrades_a_blocked_result() -> None:
    adapter = ReceiptAwareProviderAdapter(
        request=_request(require_receipt=True),
        receipt_issuer=lambda *_: (_ for _ in ()).throw(RuntimeError("issuer down")),
    )
    envelope = adapter.adapt(
        _found(source_ids=[SOURCE_ID]),
        server_source_ids=[SOURCE_ID],
        server_evidence_ids=[],
        server_sources={SOURCE_ID: _source()},
        server_evidence={},
        now=NOW,
    )
    assert envelope.conformance.decision is ProviderConformanceStatus.BLOCKED
    assert envelope.ordinary_eligible is False
    assert any(
        code.startswith("PROVIDER_SNAPSHOT_RECEIPT_ISSUANCE_FAILED")
        for code in envelope.conformance.reason_codes
    )


def test_malformed_receipt_issuer_payload_is_blocked_not_raised() -> None:
    adapter = ReceiptAwareProviderAdapter(
        request=_request(require_receipt=True),
        receipt_issuer=lambda *_: [{"receipt_id": "malformed"}],
    )
    envelope = adapter.adapt(
        _found(source_ids=[SOURCE_ID]),
        server_source_ids=[SOURCE_ID],
        server_evidence_ids=[],
        server_sources={SOURCE_ID: _source()},
        server_evidence={},
        now=NOW,
    )
    assert envelope.conformance.decision is ProviderConformanceStatus.BLOCKED
    assert any(
        code.startswith("PROVIDER_SNAPSHOT_RECEIPT_ISSUANCE_FAILED")
        for code in envelope.conformance.reason_codes
    )
