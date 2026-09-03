from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, cast

from alr_tw.contracts.providers import (
    CandidateIdentity,
    DataMode,
    ProviderCandidate,
    ProviderResult,
    ProviderResultStatus,
)
from alr_tw.contracts.research import ResearchDepth
from alr_tw.contracts.sources import (
    EvidenceSectionType,
    EvidenceSpan,
    MaterialType,
    SourceRecord,
    SourceTier,
    TrustStatus,
)
from alr_tw.providers.official import (
    OfficialConstitutionalProvider,
    OfficialJudgmentProvider,
    OfficialLawProvider,
)
from alr_tw.providers.tlr import TlrSemanticRecallProvider
from alr_tw.providers.tlr.provider import TlrHttpResponse
from alr_tw.research.provider_executor import ProviderObligationExecutor, ProviderSet
from alr_tw.research.service import ResearchService
from alr_tw.storage.sqlite_store import SqliteStore


ROOT_JID = "DEMO,130,測上,1,20990102,1"
UPPER_JID = "DEMO,131,測上,2,21000102,1"
LOWER_JID = "DEMO,129,測,3,20980102,1"


class LineageTlrTransport:
    def __init__(self) -> None:
        self.posts: list[tuple[str, Mapping[str, Any]]] = []

    async def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout: float,
        max_bytes: int,
    ) -> TlrHttpResponse:
        del url, headers, timeout, max_bytes
        return TlrHttpResponse(200, {"openapi": "3.1.0"})

    async def post_json(
        self,
        url: str,
        body: Mapping[str, Any],
        *,
        headers: Mapping[str, str],
        timeout: float,
        max_bytes: int,
    ) -> TlrHttpResponse:
        del headers, timeout, max_bytes
        self.posts.append((url, body))
        assert url.endswith("/v1/fulltext")
        return _history_response()


class RefreshingLineageTlrTransport(LineageTlrTransport):
    async def post_json(
        self,
        url: str,
        body: Mapping[str, Any],
        *,
        headers: Mapping[str, str],
        timeout: float,
        max_bytes: int,
    ) -> TlrHttpResponse:
        del headers, timeout, max_bytes
        self.posts.append((url, body))
        if len(self.posts) == 1:
            assert url.endswith("/v1/fulltext")
            return TlrHttpResponse(
                400,
                {"detail": "result_token_invalid_or_expired; rerun search once"},
            )
        if len(self.posts) == 2:
            assert url.endswith("/v1/search")
            return TlrHttpResponse(
                200,
                {
                    "results": [
                        {
                            "rank": 1,
                            "doc_id": ROOT_JID,
                            "citation_text": ("臺灣高等法院130年度測上字第1號民事判決"),
                            "result_token": "refreshed-result-token",
                        }
                    ]
                },
            )
        assert len(self.posts) == 3 and url.endswith("/v1/fulltext")
        return _history_response()


def _history_response() -> TlrHttpResponse:
    return TlrHttpResponse(
        200,
        {
            "doc_id": ROOT_JID,
            "citation_text": "臺灣高等法院130年度測上字第1號民事判決",
            "full_text": "This TLR text must not become server evidence.",
            "case_history": {
                "upper": [
                    {
                        "citation_text": "最高法院131年度測上字第2號民事判決",
                        "doc_id": UPPER_JID,
                        "doc_type": "判決",
                        "jdate": "2100-01-02",
                        "main_flag": "主文含「廢棄」",
                    }
                ],
                "lower": [
                    {
                        "citation_text": "臺灣臺北地方法院129年度測字第3號民事判決",
                        "doc_id": LOWER_JID,
                        "doc_type": "判決",
                        "jdate": "2098-01-02",
                        "main_flag": None,
                    }
                ],
                "note": "Database-recorded history only.",
            },
        },
    )


class LineageJudgmentProvider(OfficialJudgmentProvider):
    def __init__(self, timestamp: datetime) -> None:
        self.exact_calls: list[str] = []
        self.records = {
            UPPER_JID: _official_record(
                source_id="source-upper",
                evidence_id="evidence-upper-disposition",
                identifier=UPPER_JID,
                citation="最高法院131年度測上字第2號民事判決",
                exact_text="原判決廢棄，發回臺灣高等法院。",
                timestamp=timestamp,
            ),
            LOWER_JID: _official_record(
                source_id="source-lower",
                evidence_id="evidence-lower-disposition",
                identifier=LOWER_JID,
                citation="臺灣臺北地方法院129年度測字第3號民事判決",
                exact_text="原告之訴駁回。",
                timestamp=timestamp,
            ),
        }

    async def exact_lookup(
        self,
        identifier: str,
        *,
        now: datetime | None = None,
    ) -> tuple[ProviderResult, SourceRecord | None, list[EvidenceSpan]]:
        del now
        self.exact_calls.append(identifier)
        source, evidence = self.records[identifier]
        return (
            ProviderResult(
                status=ProviderResultStatus.FOUND,
                provider_id=self.provider_id,
                source_ids=[source.source_id],
                evidence_ids=[evidence.evidence_id],
                coverage_complete=True,
            ),
            source,
            [evidence],
        )


def _official_record(
    *,
    source_id: str,
    evidence_id: str,
    identifier: str,
    citation: str,
    exact_text: str,
    timestamp: datetime,
) -> tuple[SourceRecord, EvidenceSpan]:
    digest = EvidenceSpan.hash_text(exact_text)
    source = SourceRecord(
        source_id=source_id,
        source_key=f"judgment:{identifier}",
        source_version_id=f"judgment:{identifier}:v1",
        material_type=MaterialType.JUDGMENT,
        provider_id=OfficialJudgmentProvider.provider_id,
        source_tier=SourceTier.OFFICIAL,
        trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
        official_identifier=identifier,
        official_url=OfficialJudgmentProvider.official_document_url(identifier),
        citation=citation,
        fetched_at=timestamp,
        verified_at=timestamp,
        expires_at=timestamp + timedelta(hours=24),
        content_hash=digest,
        normalized_content_hash=digest,
        normalized_text=exact_text,
    )
    evidence = EvidenceSpan.from_exact_text(
        evidence_id=evidence_id,
        source_id=source.source_id,
        section_id="disposition-1",
        section_type=EvidenceSectionType.DISPOSITION,
        exact_text=exact_text,
        eligible_for_claim_support=True,
    )
    return source, evidence


def _service(
    tmp_path: Path,
    *,
    transport: LineageTlrTransport | None = None,
) -> tuple[
    ResearchService,
    SqliteStore,
    LineageJudgmentProvider,
    LineageTlrTransport,
]:
    timestamp = datetime.now(UTC)
    store = SqliteStore(tmp_path / "cache")
    judgments = LineageJudgmentProvider(timestamp)
    transport = transport or LineageTlrTransport()
    providers = ProviderSet(
        laws=cast(OfficialLawProvider, object()),
        constitutional=cast(OfficialConstitutionalProvider, object()),
        judgments=judgments,
        tlr=TlrSemanticRecallProvider(transport=transport),
    )
    service = ResearchService(store, ProviderObligationExecutor(store, providers))
    return service, store, judgments, transport


def _seed_lineage_root(service: ResearchService, store: SqliteStore) -> str:
    run = service.create_run(
        "示範裁判歷審檢查",
        mode=DataMode.HYBRID_VERIFIED,
        depth=ResearchDepth.QUICK,
    )
    timestamp = datetime.now(UTC)
    root, root_evidence = _official_record(
        source_id="source-root",
        evidence_id="evidence-root-disposition",
        identifier=ROOT_JID,
        citation="臺灣高等法院130年度測上字第1號民事判決",
        exact_text="上訴駁回。",
        timestamp=timestamp,
    )
    candidate = ProviderCandidate(
        candidate_id="tlr-root-candidate",
        provider_id=TlrSemanticRecallProvider.provider_id,
        title=root.citation,
        official_identifier=root.citation,
        identity=CandidateIdentity(
            canonical_jid=ROOT_JID,
            provider_document_id=ROOT_JID,
            formal_citation=root.citation,
        ),
        candidate_rank=1,
        metadata={"doc_id": ROOT_JID, "result_token": "bounded-result-token"},
    )
    store.save_source(run.run_id, root)
    store.save_evidence(run.run_id, root_evidence)
    store.save_candidate(run.run_id, candidate, expires_at=run.expires_at)
    return run.run_id


def test_lineage_inspection_verifies_related_decisions_and_confirms_remand(
    tmp_path: Path,
) -> None:
    service, store, judgments, transport = _service(tmp_path)
    run_id = _seed_lineage_root(service, store)

    result = service.inspect_judgment_lineage(
        run_id,
        ROOT_JID,
        "inspect-lineage-once",
    )

    assert result["status"] == "qualified"
    assert result["history_entry_count"] == 2
    assert result["official_verified_related_count"] == 2
    assert result["official_verification_failed_count"] == 0
    assert result["treatment_summary"]["officially_confirmed_reversal"] is True
    assert result["treatment_summary"]["establishes_finality"] is False
    assert result["current_holding_use"] == "do_not_rely_as_current_holding"
    assert result["establishes_finality"] is False
    assert result["semantic_opinion_comparison_performed"] is False
    assert result["authority_lineage"]["coverage_status"] == "partial"
    assert result["authority_lineage_validation"]["structurally_valid"] is True
    assert result["authority_lineage_validation"]["valid"] is False
    assert result["authority_lineage_validation"]["safe_for_citation"] is False
    assert result["authority_lineage"]["negative_treatments"][0]["status"] == "reversed"
    assert result["related_nodes"][0]["disposition_codes"] == ["vacated_remanded"]
    assert "full_text" not in result["provider_history"]
    assert {item.source_id for item in store.list_sources(run_id)} == {
        "source-root",
        "source-upper",
        "source-lower",
    }
    persisted = service.get_run(run_id)
    assert persisted is not None
    assert "JUDGMENT_LINEAGE_CONFIRMED_REVERSAL" in persisted.coverage.limitations

    replay = service.inspect_judgment_lineage(
        run_id,
        ROOT_JID,
        "inspect-lineage-once",
    )

    assert replay == result
    assert judgments.exact_calls == [UPPER_JID, LOWER_JID]
    assert len(transport.posts) == 1


def test_lineage_inspection_refreshes_one_expired_tlr_result_token(
    tmp_path: Path,
) -> None:
    refreshing_transport = RefreshingLineageTlrTransport()
    service, store, judgments, transport = _service(
        tmp_path,
        transport=refreshing_transport,
    )
    run_id = _seed_lineage_root(service, store)

    result = service.inspect_judgment_lineage(
        run_id,
        ROOT_JID,
        "inspect-lineage-after-token-refresh",
    )

    assert result["status"] == "qualified"
    assert [url.rsplit("/", 1)[-1] for url, _body in transport.posts] == [
        "fulltext",
        "search",
        "fulltext",
    ]
    assert transport.posts[2][1]["result_token"] == "refreshed-result-token"
    assert transport.posts[1][1]["query"] == ("臺灣高等法院130年度測上字第1號民事判決")
    assert judgments.exact_calls == [UPPER_JID, LOWER_JID]


def test_lineage_inspection_rejects_non_official_related_source(tmp_path: Path) -> None:
    service, store, judgments, _transport = _service(tmp_path)
    run_id = _seed_lineage_root(service, store)
    source, evidence = judgments.records[UPPER_JID]
    judgments.records[UPPER_JID] = (
        source.model_copy(update={"source_tier": SourceTier.STAGING}),
        evidence,
    )

    result = service.inspect_judgment_lineage(
        run_id,
        ROOT_JID,
        "inspect-lineage-with-untrusted-related-source",
    )

    assert result["official_verified_related_count"] == 1
    assert result["official_verification_failed_count"] == 1
    assert result["treatment_summary"]["officially_confirmed_reversal"] is False
    assert result["related_nodes"][0]["error_code"] == (
        "JUDGMENT_LINEAGE_SOURCE_NOT_OFFICIALLY_VERIFIED"
    )
    assert "source-upper" not in {item.source_id for item in store.list_sources(run_id)}


def test_lineage_inspection_reports_official_upper_appeal_dismissal(
    tmp_path: Path,
) -> None:
    service, store, judgments, _transport = _service(tmp_path)
    timestamp = datetime.now(UTC)
    judgments.records[UPPER_JID] = _official_record(
        source_id="source-upper-dismissed",
        evidence_id="evidence-upper-dismissed",
        identifier=UPPER_JID,
        citation="最高法院131年度測上字第2號民事判決",
        exact_text="上訴駁回。",
        timestamp=timestamp,
    )
    run_id = _seed_lineage_root(service, store)

    result = service.inspect_judgment_lineage(
        run_id,
        ROOT_JID,
        "inspect-lineage-with-dismissed-appeal",
    )

    treatment = result["treatment_summary"]
    assert treatment["official_upper_disposition_codes"] == ["appeal_dismissed"]
    assert treatment["officially_verified_appeal_dismissal"] is True
    assert treatment["officially_confirmed_reversal"] is False
    assert result["current_holding_use"] == "qualified_pending_substantive_review"


def test_lineage_inspection_requires_verified_root_in_same_run(tmp_path: Path) -> None:
    service, _store, judgments, transport = _service(tmp_path)
    run = service.create_run(
        "示範裁判歷審檢查",
        mode=DataMode.HYBRID_VERIFIED,
        depth=ResearchDepth.QUICK,
    )

    result = service.inspect_judgment_lineage(
        run.run_id,
        ROOT_JID,
        "inspect-lineage-without-root",
    )

    assert result["status"] == "blocked"
    assert result["reason_codes"] == ["JUDGMENT_LINEAGE_ROOT_SOURCE_NOT_IN_RUN"]
    assert result["current_holding_use"] == "qualified_pending_substantive_review"
    assert judgments.exact_calls == [] and transport.posts == []
