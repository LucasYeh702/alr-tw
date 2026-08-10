from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from alr_tw.contracts.public_law import (
    PublicLawCandidate,
    PublicLawLineage,
    PublicLawLineageRelation,
    PublicLawMaterialType,
    PublicLawProcedureKind,
    PublicLawProcedureRequirement,
    PublicLawProviderResult,
    PublicLawRemedyStage,
    PublicLawResultStatus,
    PublicLawSearchRequest,
    PublicLawServerMetadata,
    PublicLawSourceRecord,
    PublicLawSourceRole,
    PublicLawValidationDecision,
    validate_public_law_result,
)
from alr_tw.contracts.sources import EvidenceSpan, SourceTier, TrustStatus
from alr_tw.providers.sdk import (
    GenericPublicLawProviderAdapter,
    PublicLawBackendResult,
    PublicLawBackendStatus,
)


NOW = datetime(2026, 8, 9, 8, 0, tzinfo=UTC)


def _metadata(
    *,
    provider_id: str = "provider-public-law",
    receipt_id: str = "receipt-public-law-1",
) -> PublicLawServerMetadata:
    return PublicLawServerMetadata(
        provider_id=provider_id,
        snapshot_id="snapshot-public-law-1",
        generation="generation-public-law-1",
        receipt_id=receipt_id,
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


def _request(
    *,
    query_id: str = "query-public-law-1",
    max_results: int = 5,
) -> PublicLawSearchRequest:
    return PublicLawSearchRequest(
        query_id=query_id,
        query="行政程序與救濟期間",
        material_types=[
            PublicLawMaterialType.ADMINISTRATIVE_RULE,
            PublicLawMaterialType.ADMINISTRATIVE_APPEAL,
        ],
        remedy_stages=[PublicLawRemedyStage.ADMINISTRATIVE_APPEAL],
        bounded_scope="synthetic-public-law-scope",
        max_results=max_results,
        as_of_date=date(2026, 8, 9),
    )


def _candidate(
    candidate_id: str = "candidate-public-law-1",
    *,
    provider_id: str = "provider-public-law",
) -> PublicLawCandidate:
    return PublicLawCandidate(
        candidate_id=candidate_id,
        provider_id=provider_id,
        material_type=PublicLawMaterialType.ADMINISTRATIVE_RULE,
        source_role=PublicLawSourceRole.NORMATIVE_RULE,
        title="Synthetic administrative rule candidate",
        excerpt="Candidate-only excerpt; it is not evidence.",
        candidate_rank=1,
    )


def _source(
    metadata: PublicLawServerMetadata,
    *,
    material_type: PublicLawMaterialType = PublicLawMaterialType.ADMINISTRATIVE_RULE,
    source_role: PublicLawSourceRole = PublicLawSourceRole.NORMATIVE_RULE,
    source_id: str = "source-public-law-1",
) -> PublicLawSourceRecord:
    text = "合成行政程序資料，僅供契約測試。"
    digest = EvidenceSpan.hash_text(text)
    return PublicLawSourceRecord(
        source_id=source_id,
        source_key=f"public-law:{source_id}",
        source_version_id=f"{source_id}:v1",
        material_type=material_type,
        source_role=source_role,
        provider_id=metadata.provider_id,
        source_tier=SourceTier.OFFICIAL,
        trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
        official_identifier=f"PUBLIC-{source_id}",
        official_url="https://example.test/public-law/source",
        citation="合成公法資料",
        title="合成公法資料",
        issued_at=datetime(2026, 1, 1, tzinfo=UTC),
        effective_from=date(2026, 1, 1),
        fetched_at=NOW,
        verified_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        content_hash=digest,
        normalized_content_hash=digest,
        normalized_text=text,
        server_metadata=metadata,
        lineage=[
            PublicLawLineage(
                lineage_id=f"lineage-{source_id}",
                relation=PublicLawLineageRelation.DERIVED_FROM,
                parent_source_id="source-parent-public-law",
                child_source_id=source_id,
                evidence_ids=[f"evidence-{source_id}"],
            )
        ],
        procedural_requirements=[
            PublicLawProcedureRequirement(
                requirement_id=f"procedure-{source_id}",
                kind=PublicLawProcedureKind.REASON_GIVING,
                description="記錄程序理由的資料定位",
                source_ids=[source_id],
                evidence_ids=[f"evidence-{source_id}"],
                remedy_stage=PublicLawRemedyStage.ADMINISTRATIVE_APPEAL,
            )
        ],
        remedy_stages=[PublicLawRemedyStage.ADMINISTRATIVE_APPEAL],
    )


def _adapter(
    backend_result: PublicLawBackendResult,
    *,
    metadata: PublicLawServerMetadata | None = None,
    source_promoter=None,
) -> GenericPublicLawProviderAdapter:
    return GenericPublicLawProviderAdapter(
        provider_id="provider-public-law",
        backend=lambda_backend(backend_result),
        material_types=(
            PublicLawMaterialType.ADMINISTRATIVE_RULE,
            PublicLawMaterialType.ADMINISTRATIVE_INTERPRETATION,
            PublicLawMaterialType.ADMINISTRATIVE_APPEAL,
            PublicLawMaterialType.LEGISLATIVE_MATERIAL,
        ),
        metadata_issuer=(
            (lambda provider_id, request: metadata)
            if metadata is not None
            else None
        ),
        source_promoter=source_promoter,
        max_results=5,
    )


class _Backend:
    def __init__(self, result: PublicLawBackendResult):
        self.result = result

    def search(self, request: PublicLawSearchRequest) -> PublicLawBackendResult:
        assert request.query_id == self.result.query_id
        return self.result


def lambda_backend(result: PublicLawBackendResult) -> _Backend:
    return _Backend(result)


def test_public_law_material_families_and_lineage_are_provider_neutral() -> None:
    metadata = _metadata()
    variants = [
        (PublicLawMaterialType.ADMINISTRATIVE_RULE, PublicLawSourceRole.NORMATIVE_RULE),
        (
            PublicLawMaterialType.ADMINISTRATIVE_INTERPRETATION,
            PublicLawSourceRole.INTERPRETIVE_GUIDANCE,
        ),
        (PublicLawMaterialType.ADMINISTRATIVE_APPEAL, PublicLawSourceRole.APPEAL_DECISION),
        (PublicLawMaterialType.LEGISLATIVE_MATERIAL, PublicLawSourceRole.LEGISLATIVE_HISTORY),
    ]
    for index, (material_type, role) in enumerate(variants):
        source = _source(
            metadata,
            material_type=material_type,
            source_role=role,
            source_id=f"source-public-law-{index}",
        )
        assert source.material_type is material_type
        assert source.source_role is role
        assert source.lineage[0].server_owned is True
        assert source.procedural_requirements[0].remedy_stage is (
            PublicLawRemedyStage.ADMINISTRATIVE_APPEAL
        )


def test_source_lineage_and_procedure_reject_ambiguous_self_or_duplicate_edges() -> None:
    with pytest.raises(ValidationError, match="cannot point a source to itself"):
        PublicLawLineage(
            lineage_id="lineage-self",
            relation=PublicLawLineageRelation.RELATED,
            parent_source_id="source-self",
            child_source_id="source-self",
        )
    with pytest.raises(ValidationError, match="evidence_ids must be unique"):
        PublicLawLineage(
            lineage_id="lineage-duplicate",
            relation=PublicLawLineageRelation.CITES,
            parent_source_id="source-a",
            child_source_id="source-b",
            evidence_ids=["evidence-1", "evidence-1"],
        )


def test_candidate_cannot_be_used_as_source_or_evidence() -> None:
    with pytest.raises(ValidationError):
        PublicLawCandidate.model_validate(
            {
                **_candidate().model_dump(),
                "source_id": "forged-source",
                "evidence_ids": ["forged-evidence"],
            }
        )


def test_scoped_miss_requires_server_metadata_and_is_not_global_absence() -> None:
    request = _request()
    metadata = _metadata()
    result = PublicLawProviderResult(
        provider_id="provider-public-law",
        query_id=request.query_id,
        status=PublicLawResultStatus.NOT_FOUND_IN_SCOPE,
        bounded_scope=request.bounded_scope,
        server_metadata=metadata,
        coverage_complete=True,
        absence_claim_allowed=True,
    )
    accepted = validate_public_law_result(result, server_metadata=metadata, now=NOW)
    assert accepted.decision is PublicLawValidationDecision.ACCEPTED
    assert accepted.absence_claim_allowed is True
    assert accepted.semantic_conclusion_performed is False

    blocked = validate_public_law_result(result, server_metadata=None, now=NOW)
    assert blocked.decision is PublicLawValidationDecision.BLOCKED
    assert "PUBLIC_LAW_SERVER_METADATA_BINDING_REQUIRED" in blocked.reason_codes


def test_generic_adapter_returns_candidate_only_and_enforces_result_bound() -> None:
    request = _request(max_results=1)
    metadata = _metadata()
    backend = PublicLawBackendResult(
        provider_id="provider-public-law",
        query_id=request.query_id,
        status=PublicLawBackendStatus.FOUND,
        candidates=[_candidate("candidate-a"), _candidate("candidate-b")],
        coverage_complete=True,
    )
    result = _adapter(backend, metadata=metadata).search(request)
    assert result.status is PublicLawResultStatus.PARTIAL
    assert result.truncated is True
    assert result.absence_claim_allowed is False
    assert len(result.candidates) == 1
    assert result.sources == []
    assert result.semantic_conclusion_performed is False
    validation = validate_public_law_result(result, server_metadata=metadata, now=NOW)
    assert validation.decision is PublicLawValidationDecision.QUALIFIED
    assert validation.eligible_source_ids == []


def test_generic_adapter_clean_miss_is_bounded_and_metadata_bound() -> None:
    request = _request()
    metadata = _metadata()
    backend = PublicLawBackendResult(
        provider_id="provider-public-law",
        query_id=request.query_id,
        status=PublicLawBackendStatus.NOT_FOUND,
        coverage_complete=True,
    )
    result = _adapter(backend, metadata=metadata).search(request)
    assert result.status is PublicLawResultStatus.NOT_FOUND_IN_SCOPE
    assert result.absence_claim_allowed is True
    validation = validate_public_law_result(result, server_metadata=metadata, now=NOW)
    assert validation.decision is PublicLawValidationDecision.ACCEPTED
    assert validation.absence_claim_allowed is True


def test_generic_adapter_without_metadata_issuer_fails_closed() -> None:
    request = _request()
    backend = PublicLawBackendResult(
        provider_id="provider-public-law",
        query_id=request.query_id,
        status=PublicLawBackendStatus.NOT_FOUND,
        coverage_complete=True,
    )
    result = _adapter(backend).search(request)
    assert result.status is PublicLawResultStatus.BLOCKED
    assert result.absence_claim_allowed is False
    assert result.server_metadata is None


def test_source_metadata_mismatch_downgrades_without_promoting_source() -> None:
    request = _request()
    metadata = _metadata()
    foreign = _metadata(receipt_id="receipt-foreign")
    backend = PublicLawBackendResult(
        provider_id="provider-public-law",
        query_id=request.query_id,
        status=PublicLawBackendStatus.FOUND,
        sources=[_source(foreign)],
        coverage_complete=True,
    )
    result = _adapter(
        backend,
        metadata=metadata,
        source_promoter=lambda item, _request, _metadata: item,
    ).search(request)
    assert result.status is PublicLawResultStatus.PARTIAL
    assert result.sources == []
    assert result.absence_claim_allowed is False
    assert "PUBLIC_LAW_SOURCE_METADATA_MISMATCH" in result.reason_codes


def test_matching_metadata_without_source_gate_cannot_promote_forged_eligible_source() -> None:
    request = _request()
    metadata = _metadata()
    source = _source(metadata)
    backend = PublicLawBackendResult(
        provider_id="provider-public-law",
        query_id=request.query_id,
        status=PublicLawBackendStatus.FOUND,
        sources=[source],
        coverage_complete=True,
    )
    result = _adapter(backend, metadata=metadata).search(request)
    assert result.status is PublicLawResultStatus.PARTIAL
    assert result.sources == []
    assert "PUBLIC_LAW_SOURCE_PROMOTION_REQUIRES_SERVER_GATE" in result.reason_codes
    validation = validate_public_law_result(
        result,
        server_metadata=metadata,
        server_source_ids=[source.source_id],
        now=NOW,
    )
    assert validation.eligible_source_ids == []


def test_source_promoter_must_preserve_server_refs_and_hashes() -> None:
    request = _request()
    metadata = _metadata()
    source = _source(metadata)
    backend = PublicLawBackendResult(
        provider_id="provider-public-law",
        query_id=request.query_id,
        status=PublicLawBackendStatus.FOUND,
        sources=[source],
        coverage_complete=True,
    )
    promoted = _adapter(
        backend,
        metadata=metadata,
        source_promoter=lambda item, _request, _metadata: item,
    ).search(request)
    assert promoted.status is PublicLawResultStatus.FOUND
    accepted = validate_public_law_result(
        promoted,
        server_metadata=metadata,
        server_source_ids={source.source_id},
        now=NOW,
    )
    assert accepted.decision is PublicLawValidationDecision.ACCEPTED
    assert accepted.eligible_source_ids == [source.source_id]

    forged_hash = EvidenceSpan.hash_text("tampered source content")
    forged_backend = PublicLawBackendResult(
        provider_id="provider-public-law",
        query_id=request.query_id,
        status=PublicLawBackendStatus.FOUND,
        sources=[source],
        coverage_complete=True,
    )
    rejected = _adapter(
        forged_backend,
        metadata=metadata,
        source_promoter=lambda item, _request, _metadata: item.model_copy(
            update={"content_hash": forged_hash}
        ),
    ).search(request)
    assert rejected.status is PublicLawResultStatus.PARTIAL
    assert rejected.sources == []
    assert "PUBLIC_LAW_SOURCE_PROMOTION_BINDING_MISMATCH" in rejected.reason_codes


def test_direct_matching_metadata_source_requires_server_source_refs() -> None:
    request = _request()
    metadata = _metadata()
    source = _source(metadata)
    result = PublicLawProviderResult(
        provider_id="provider-public-law",
        query_id=request.query_id,
        status=PublicLawResultStatus.FOUND,
        bounded_scope=request.bounded_scope,
        sources=[source],
        server_metadata=metadata,
        coverage_complete=True,
    )
    missing = validate_public_law_result(result, server_metadata=metadata, now=NOW)
    assert missing.decision is PublicLawValidationDecision.BLOCKED
    assert "PUBLIC_LAW_SERVER_SOURCE_BINDING_REQUIRED" in missing.reason_codes
    wrong = validate_public_law_result(
        result,
        server_metadata=metadata,
        server_source_ids=["different-server-source"],
        now=NOW,
    )
    assert wrong.decision is PublicLawValidationDecision.BLOCKED
    assert "PUBLIC_LAW_SOURCE_NOT_SERVER_OWNED" in wrong.reason_codes


def test_backend_error_is_retryable_not_clean_miss() -> None:
    request = _request()
    metadata = _metadata()
    backend = PublicLawBackendResult(
        provider_id="provider-public-law",
        query_id=request.query_id,
        status=PublicLawBackendStatus.ERROR,
        coverage_complete=False,
    )
    result = _adapter(backend, metadata=metadata).search(request)
    assert result.status is PublicLawResultStatus.RETRY_REQUIRED
    assert result.coverage_complete is False
    assert result.absence_claim_allowed is False
