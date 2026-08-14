from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from alr_tw.contracts.historical_law import (
    HistoricalLawQuery,
    HistoricalLawResolution,
    validate_historical_law_resolution,
)
from alr_tw.contracts.public_law import (
    PublicLawMaterialType,
    PublicLawProviderResult,
    PublicLawResultStatus,
    PublicLawServerMetadata,
    PublicLawSourceRecord,
    PublicLawSourceRole,
    PublicLawValidationDecision,
)
from alr_tw.contracts.sources import EvidenceSpan, SourceTier, TrustStatus
from alr_tw.providers.legislative_history import LegislativeHistoryProviderAdapter
from alr_tw.providers.sdk import PublicLawBackendResult, PublicLawBackendStatus


NOW = datetime(2026, 8, 14, 8, 0, tzinfo=UTC)


def _metadata() -> PublicLawServerMetadata:
    return PublicLawServerMetadata(
        provider_id="legislative-yuan",
        snapshot_id="snapshot-legislative-1",
        generation="generation-legislative-1",
        receipt_id="receipt-legislative-1",
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


def _source(
    metadata: PublicLawServerMetadata,
    *,
    source_id: str,
    material_type: PublicLawMaterialType,
    role: PublicLawSourceRole,
) -> PublicLawSourceRecord:
    text = (
        "民法歷史法條合成內容。"
        if material_type is PublicLawMaterialType.HISTORICAL_STATUTE
        else "立法理由合成內容，不能直接視為法條。"
    )
    digest = EvidenceSpan.hash_text(text)
    return PublicLawSourceRecord(
        source_id=source_id,
        source_key=f"legislative:{source_id}",
        source_version_id=f"{source_id}:v1",
        material_type=material_type,
        source_role=role,
        provider_id=metadata.provider_id,
        source_tier=SourceTier.OFFICIAL,
        trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
        official_identifier=f"LY-{source_id}",
        official_url="https://example.test/legislative/source",
        citation="合成歷史法規資料",
        title="合成歷史法規資料",
        issued_at=datetime(2020, 1, 1, tzinfo=UTC),
        fetched_at=NOW,
        verified_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        content_hash=digest,
        normalized_content_hash=digest,
        normalized_text=text,
        server_metadata=metadata,
    )


def _query(*, include_history: bool = True) -> HistoricalLawQuery:
    return HistoricalLawQuery(
        query_id="historical-query-1",
        law_identifier="civil-code-184",
        as_of_date=date(2019, 1, 1),
        bounded_scope="synthetic-legislative-scope",
        include_legislative_history=include_history,
    )


def _provider_result(
    metadata: PublicLawServerMetadata,
    sources: list[PublicLawSourceRecord],
) -> PublicLawProviderResult:
    return PublicLawProviderResult(
        provider_id=metadata.provider_id,
        query_id="historical-query-1",
        status=PublicLawResultStatus.FOUND,
        bounded_scope="synthetic-legislative-scope",
        sources=sources,
        server_metadata=metadata,
        coverage_complete=True,
    )


def _resolution(
    metadata: PublicLawServerMetadata,
    *,
    sources: list[PublicLawSourceRecord],
    normative: list[str],
    legislative: list[str],
) -> HistoricalLawResolution:
    return HistoricalLawResolution(
        query_id="historical-query-1",
        provider_id=metadata.provider_id,
        law_identifier="civil-code-184",
        as_of_date=date(2019, 1, 1),
        bounded_scope="synthetic-legislative-scope",
        provider_result=_provider_result(metadata, sources),
        normative_source_ids=normative,
        legislative_material_source_ids=legislative,
    )


def test_historical_query_requires_explicit_law_locator_and_date() -> None:
    with pytest.raises(ValidationError, match="IDENTIFIER_OR_NAME_REQUIRED"):
        HistoricalLawQuery(
            query_id="historical-query-invalid",
            as_of_date=date(2019, 1, 1),
            bounded_scope="scope",
        )


def test_resolution_keeps_normative_text_separate_from_legislative_history() -> None:
    metadata = _metadata()
    statute = _source(
        metadata,
        source_id="statute-1",
        material_type=PublicLawMaterialType.HISTORICAL_STATUTE,
        role=PublicLawSourceRole.NORMATIVE_RULE,
    )
    history = _source(
        metadata,
        source_id="history-1",
        material_type=PublicLawMaterialType.LEGISLATIVE_MATERIAL,
        role=PublicLawSourceRole.LEGISLATIVE_HISTORY,
    )
    resolution = _resolution(
        metadata,
        sources=[statute, history],
        normative=["statute-1"],
        legislative=["history-1"],
    )
    result = validate_historical_law_resolution(
        resolution,
        server_metadata=metadata,
        server_source_ids=["statute-1", "history-1"],
        now=NOW,
    )
    assert result.decision is PublicLawValidationDecision.ACCEPTED
    assert result.applicability_source_ids == ["statute-1"]
    assert result.legislative_material_source_ids == ["history-1"]


def test_legislative_history_alone_is_qualified_not_applicability_source() -> None:
    metadata = _metadata()
    history = _source(
        metadata,
        source_id="history-only",
        material_type=PublicLawMaterialType.LEGISLATIVE_MATERIAL,
        role=PublicLawSourceRole.LEGISLATIVE_HISTORY,
    )
    resolution = _resolution(
        metadata,
        sources=[history],
        normative=[],
        legislative=["history-only"],
    )
    result = validate_historical_law_resolution(
        resolution,
        server_metadata=metadata,
        server_source_ids=["history-only"],
        now=NOW,
    )
    assert result.decision is PublicLawValidationDecision.QUALIFIED
    assert "HISTORICAL_LAW_NORMATIVE_SOURCE_MISSING" in result.reason_codes


def test_qualified_history_preserves_provider_reason_codes() -> None:
    metadata = _metadata()
    history = _source(
        metadata,
        source_id="history-partial",
        material_type=PublicLawMaterialType.LEGISLATIVE_MATERIAL,
        role=PublicLawSourceRole.LEGISLATIVE_HISTORY,
    )
    provider_result = _provider_result(metadata, [history]).model_copy(
        update={
            "status": PublicLawResultStatus.PARTIAL,
            "coverage_complete": False,
            "reason_codes": ["PUBLIC_LAW_RESULT_TRUNCATED"],
        }
    )
    resolution = _resolution(
        metadata,
        sources=[history],
        normative=[],
        legislative=["history-partial"],
    ).model_copy(update={"provider_result": provider_result})
    result = validate_historical_law_resolution(
        resolution,
        server_metadata=metadata,
        server_source_ids=["history-partial"],
        now=NOW,
    )
    assert result.decision is PublicLawValidationDecision.QUALIFIED
    assert "PUBLIC_LAW_RESULT_TRUNCATED" in result.reason_codes


def test_legislative_role_mismatch_is_blocked_even_if_source_model_was_forged() -> None:
    metadata = _metadata()
    original = _source(
        metadata,
        source_id="history-role-forged",
        material_type=PublicLawMaterialType.LEGISLATIVE_MATERIAL,
        role=PublicLawSourceRole.LEGISLATIVE_HISTORY,
    )
    history = original.model_copy(update={"source_role": PublicLawSourceRole.NORMATIVE_RULE})
    forged_provider_result = _provider_result(metadata, [original]).model_copy(
        update={"sources": [history]}
    )
    resolution = HistoricalLawResolution(
        query_id="historical-query-1",
        provider_id=metadata.provider_id,
        law_identifier="civil-code-184",
        as_of_date=date(2019, 1, 1),
        bounded_scope="synthetic-legislative-scope",
        provider_result=forged_provider_result,
        normative_source_ids=[],
        legislative_material_source_ids=["history-role-forged"],
    )
    result = validate_historical_law_resolution(
        resolution,
        server_metadata=metadata,
        server_source_ids=["history-role-forged"],
        now=NOW,
    )
    assert result.decision is PublicLawValidationDecision.BLOCKED
    assert "HISTORICAL_LAW_LEGISLATIVE_ROLE_MISMATCH" in result.reason_codes


def test_resolution_rejects_role_overlap() -> None:
    metadata = _metadata()
    statute = _source(
        metadata,
        source_id="statute-overlap",
        material_type=PublicLawMaterialType.HISTORICAL_STATUTE,
        role=PublicLawSourceRole.NORMATIVE_RULE,
    )
    with pytest.raises(ValidationError, match="SOURCE_ROLE_OVERLAP"):
        _resolution(
            metadata,
            sources=[statute],
            normative=["statute-overlap"],
            legislative=["statute-overlap"],
        )


class _Backend:
    def __init__(self, result: PublicLawBackendResult):
        self.result = result

    def search(self, request: HistoricalLawQuery) -> PublicLawBackendResult:
        assert request.as_of_date == date(2019, 1, 1)
        return self.result


def test_legislative_history_adapter_uses_common_server_promotion_gate() -> None:
    metadata = _metadata()
    statute = _source(
        metadata,
        source_id="adapter-statute",
        material_type=PublicLawMaterialType.HISTORICAL_STATUTE,
        role=PublicLawSourceRole.NORMATIVE_RULE,
    )
    backend = _Backend(
        PublicLawBackendResult(
            provider_id="legislative-yuan",
            query_id="historical-query-1",
            status=PublicLawBackendStatus.FOUND,
            sources=[statute],
            coverage_complete=True,
        )
    )
    adapter = LegislativeHistoryProviderAdapter(
        provider_id="legislative-yuan",
        backend=backend,
        metadata_issuer=lambda _provider_id, _request: metadata,
        source_promoter=lambda source, _request, _metadata: source,
    )
    resolution = adapter.search(_query(include_history=False))
    assert resolution.normative_source_ids == ["adapter-statute"]
    result = validate_historical_law_resolution(
        resolution,
        server_metadata=metadata,
        server_source_ids=["adapter-statute"],
        now=NOW,
    )
    assert result.decision is PublicLawValidationDecision.ACCEPTED


def test_adapter_without_metadata_issuer_is_blocked() -> None:
    adapter = LegislativeHistoryProviderAdapter(
        provider_id="legislative-yuan",
        backend=_Backend(
            PublicLawBackendResult(
                provider_id="legislative-yuan",
                query_id="historical-query-1",
                status=PublicLawBackendStatus.NOT_FOUND,
                coverage_complete=True,
            )
        ),
    )
    resolution = adapter.search(_query())
    assert resolution.provider_result.status is PublicLawResultStatus.BLOCKED
