from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from alr_tw.contracts.providers import (
    CandidateIdentity,
    DataMode,
    ProviderCandidate,
    ProviderErrorCode,
    ProviderResult,
    ProviderResultStatus,
)
from alr_tw.contracts.interop import DiscoveryMode, ResearchPlanProposal
from alr_tw.contracts.research import (
    ResearchDepth,
    ResearchObligationKind,
    ResearchObligationStatus,
    ResearchState,
)
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
from alr_tw.providers.official.http import HttpResponse
from alr_tw.providers.official.judicial_site import JudicialSiteResponse
from alr_tw.providers.tlr import TlrSemanticRecallProvider
from alr_tw.providers.tlr.provider import TlrHttpResponse
from alr_tw.research.provider_executor import ProviderObligationExecutor, ProviderSet
from alr_tw.research.service import ResearchService
from alr_tw.storage.sqlite_store import SqliteStore


def _law_archive() -> bytes:
    document = {
        "UpdateDate": "2099/1/1",
        "Laws": [
            {
                "LawName": "示範責任法",
                "LawURL": "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=DEMO0099",
                "LawModifiedDate": "20990101",
                "LawEffectiveDate": "20990101",
                "LawAbandonNote": "",
                "LawArticles": [
                    {
                        "ArticleType": "A",
                        "ArticleNo": "第 7 條",
                        "ArticleContent": "行為人違反示範義務時，應負合成測試責任。",
                    }
                ],
            }
        ],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ChLaw.json", json.dumps(document, ensure_ascii=False))
    return buffer.getvalue()


class LawTransport:
    async def get(self, url: str, *, timeout: float, max_bytes: int) -> HttpResponse:
        del timeout, max_bytes
        return HttpResponse(200, _law_archive(), {}, url)


class CountingLawProvider(OfficialLawProvider):
    def __init__(self, *, snapshot_ttl: timedelta = timedelta(hours=24)) -> None:
        super().__init__(
            LawTransport(),
            verify_webpage=False,
            snapshot_ttl=snapshot_ttl,
        )
        self.exact_calls = 0

    async def exact_lookup(self, law_name: str, article_no: str, **kwargs: Any):
        self.exact_calls += 1
        return await super().exact_lookup(law_name, article_no, **kwargs)


class FailingRevalidationLawProvider(OfficialLawProvider):
    def __init__(self) -> None:
        super().__init__(
            LawTransport(),
            verify_webpage=False,
            snapshot_ttl=timedelta(microseconds=1),
        )
        self.exact_calls = 0

    async def exact_lookup(self, law_name: str, article_no: str, **kwargs: Any):
        self.exact_calls += 1
        if self.exact_calls > 1:
            return (
                ProviderResult(
                    status=ProviderResultStatus.ERROR,
                    provider_id=self.provider_id,
                    error_code=ProviderErrorCode.OFFICIAL_SOURCE_UNAVAILABLE,
                    message="synthetic outage",
                ),
                None,
                None,
            )
        return await super().exact_lookup(law_name, article_no, **kwargs)


class UnusedHttpTransport:
    async def get(self, url: str, *, timeout: float, max_bytes: int) -> HttpResponse:
        del timeout, max_bytes
        return HttpResponse(503, b"", {}, url)


class EmptyJudgmentSearchTransport:
    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def get(
        self,
        url: str,
        *,
        timeout: float,
        max_bytes: int,
    ) -> JudicialSiteResponse:
        del timeout, max_bytes
        form = (
            '<form id="form1" action="./Default_AD.aspx">'
            '<input type="hidden" name="__VIEWSTATE" value="state">'
            '<input type="hidden" name="__EVENTVALIDATION" value="validation">'
            "</form>"
        )
        return JudicialSiteResponse(200, form.encode(), {}, url)

    async def post_form(
        self,
        url: str,
        form: Mapping[str, str],
        *,
        timeout: float,
        max_bytes: int,
    ) -> JudicialSiteResponse:
        del form, timeout, max_bytes
        return JudicialSiteResponse(200, "查無符合條件".encode(), {}, url)


def _empty_judgments() -> OfficialJudgmentProvider:
    return OfficialJudgmentProvider(EmptyJudgmentSearchTransport())


class CounterRetryJudgmentProvider(OfficialJudgmentProvider):
    """Synthetic official provider for resumable counter-authority coverage."""

    success_jid = "DEMO,130,民,101,20990101,1"
    retry_jid = "DEMO,130,民,102,20990101,1"

    def __init__(self) -> None:
        super().__init__(EmptyJudgmentSearchTransport())
        self.search_calls = 0
        self.exact_calls = 0

    async def search(self, query: str = "", *, limit: int = 10, **kwargs: Any) -> ProviderResult:
        del kwargs
        self.search_calls += 1
        if "相反見解" not in query and "不同見解" not in query:
            return ProviderResult(
                status=ProviderResultStatus.NOT_FOUND,
                provider_id=self.provider_id,
                coverage_complete=True,
            )
        candidates = [
            ProviderCandidate(
                candidate_id=f"counter-candidate-{identifier}",
                provider_id=self.provider_id,
                title="合成相反見解候選",
                official_identifier=identifier,
                identity=CandidateIdentity(canonical_jid=identifier),
                candidate_rank=index,
                metadata={"candidate_only": True},
            )
            for index, identifier in enumerate(
                (self.success_jid, self.retry_jid),
                start=1,
            )
        ]
        return ProviderResult(
            status=ProviderResultStatus.FOUND,
            provider_id=self.provider_id,
            candidates=candidates[:limit],
            coverage_complete=True,
        )

    async def exact_lookup(
        self,
        identifier: str,
        *,
        now: datetime | None = None,
    ) -> tuple[ProviderResult, SourceRecord | None, list[EvidenceSpan]]:
        del now
        self.exact_calls += 1
        if self.exact_calls == 2:
            raise TimeoutError("synthetic counter exact timeout")
        text = f"合成官方裁判全文：{identifier}。"
        timestamp = datetime.now(UTC)
        digest = EvidenceSpan.hash_text(text)
        source = SourceRecord(
            source_id=f"counter-source-{identifier}",
            source_key=f"judgment:{identifier}",
            source_version_id=f"judgment:{identifier}:v1",
            material_type=MaterialType.JUDGMENT,
            provider_id=self.provider_id,
            source_tier=SourceTier.OFFICIAL,
            trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
            official_identifier=identifier,
            official_url=OfficialJudgmentProvider.official_document_url(identifier),
            citation=f"合成法院130年度民字第{identifier.split(',')[3]}號判決",
            fetched_at=timestamp,
            verified_at=timestamp,
            expires_at=timestamp + timedelta(hours=1),
            content_hash=digest,
            normalized_content_hash=digest,
            normalized_text=text,
        )
        evidence = EvidenceSpan.from_exact_text(
            evidence_id=f"counter-evidence-{identifier}",
            source_id=source.source_id,
            section_id="reasoning-1",
            section_type=EvidenceSectionType.COURT_REASONING,
            exact_text=text,
            eligible_for_claim_support=True,
        )
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


class CleanCounterJudgmentProvider(CounterRetryJudgmentProvider):
    """Return one recall candidate, then a clean bounded counter miss."""

    async def search(
        self,
        query: str = "",
        *,
        limit: int = 10,
        **kwargs: Any,
    ) -> ProviderResult:
        del query, kwargs
        self.search_calls += 1
        if self.search_calls > 1:
            return ProviderResult(
                status=ProviderResultStatus.NOT_FOUND,
                provider_id=self.provider_id,
                coverage_complete=True,
            )
        candidates = [
            ProviderCandidate(
                candidate_id=f"counter-candidate-{self.success_jid}",
                provider_id=self.provider_id,
                title="合成官方裁判候選",
                official_identifier=self.success_jid,
                identity=CandidateIdentity(canonical_jid=self.success_jid),
                candidate_rank=1,
                metadata={"candidate_only": True},
            )
        ]
        return ProviderResult(
            status=ProviderResultStatus.FOUND,
            provider_id=self.provider_id,
            candidates=candidates[:limit],
            coverage_complete=True,
        )


class ForgedAbsenceExecutor:
    """Attempts to inject an impossible empty provider scope into a run."""

    def execute(self, run, obligation):
        forged_coverage = run.coverage.model_copy(
            update={
                "counter_authority_checked": True,
                "coverage_complete": True,
                "absence_claim_allowed": True,
                "bounded_query_scope": "   ",
                "selected_provider_scope": [],
                "successful_provider_scope": [],
            }
        )
        return {
            "status": "completed",
            "obligation": obligation.kind.value,
            "provider_calls": [],
            "warnings": [],
            "metadata": {},
            "_run_updates": {"coverage": forged_coverage},
        }


class JudgmentFlowTransport:
    jid = "DEMO,130,測,42,20990102,1"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def get(
        self,
        url: str,
        *,
        timeout: float,
        max_bytes: int,
    ) -> JudicialSiteResponse:
        del timeout, max_bytes
        self.calls.append(("GET", url))
        encoded = quote(self.jid, safe="")
        if "Default_AD.aspx" in url:
            body = (
                '<form id="form1" action="./Default_AD.aspx">'
                '<input type="hidden" name="__VIEWSTATE" value="state">'
                '<input type="hidden" name="__EVENTVALIDATION" value="validation">'
                "</form>"
            )
        elif "qryresultlst.aspx" in url:
            body = (
                f'<table><tr><td><a href="data.aspx?ty=JD&amp;id={encoded}">'
                "臺灣示範地方法院130年度測訴字第42號刑事判決</a></td></tr>"
                '<tr><td><span class="tdCut">合成侵權裁判摘要</span></td></tr></table>'
            )
        elif "data.aspx" in url:
            body = f"""
            <a id="hlPrint" href="/FJUD/printData.aspx?id={encoded}">列印</a>
            <div id="jud">
              <div class="row"><div class="col-th">裁判字號：</div>
                <div class="col-td">臺灣示範地方法院130年度測訴字第42號刑事判決</div></div>
              <div class="row"><div class="col-th">裁判日期：</div>
                <div class="col-td">民國130年1月2日</div></div>
              <div class="row"><div class="col-th">裁判案由：</div>
                <div class="col-td">合成侵權事件</div></div>
              <div class="jud_content"><div class="htmlcontent">
                <div>主 文</div><div>合成裁判結果。</div><div>理 由</div>
                <div>一、原告主張：合成權利受侵害。</div>
                <div>二、本院認定合成測試責任成立。</div>
              </div></div>
            </div>
            """
        else:
            raise AssertionError(url)
        return JudicialSiteResponse(200, body.encode(), {}, url)

    async def post_form(
        self,
        url: str,
        form: Mapping[str, str],
        *,
        timeout: float,
        max_bytes: int,
    ) -> JudicialSiteResponse:
        del timeout, max_bytes
        self.calls.append(("POST", url))
        assert form["jud_kw"] in {
            "合成侵權裁判舉證責任",
            "合成侵權裁判舉證責任 相反見解",
            "合成侵權裁判舉證責任 不同見解",
        }
        body = (
            '<a href="qryresultlst.aspx?ty=JUDBOOK&amp;q=flow">'
            '查詢結果<span class="badge">1</span></a>'
            '<iframe name="iframe-data" src="qryresultlst.aspx?ty=JUDBOOK&amp;q=flow"></iframe>'
        )
        return JudicialSiteResponse(200, body.encode(), {}, url)


class TlrPromotionJudgmentTransport(JudgmentFlowTransport):
    """Official recall returns none, while exact JID lookup remains available."""

    async def post_form(
        self,
        url: str,
        form: Mapping[str, str],
        *,
        timeout: float,
        max_bytes: int,
    ) -> JudicialSiteResponse:
        del form, timeout, max_bytes
        self.calls.append(("POST", url))
        return JudicialSiteResponse(200, "查無符合條件".encode(), {}, url)


class UnavailableSearchTlrPromotionTransport(TlrPromotionJudgmentTransport):
    async def post_form(
        self,
        url: str,
        form: Mapping[str, str],
        *,
        timeout: float,
        max_bytes: int,
    ) -> JudicialSiteResponse:
        del form, timeout, max_bytes
        self.calls.append(("POST", url))
        return JudicialSiteResponse(503, b"", {}, url)


class TlrLegacyPromotionJudgmentTransport(TlrPromotionJudgmentTransport):
    jid = "DEMO,130,測,42,20990102"


class TlrFixtureTransport:
    def __init__(self, response: TlrHttpResponse):
        self.response = response
        self.calls = 0

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
        del url, body, headers, timeout, max_bytes
        self.calls += 1
        return self.response


def _service(tmp_path: Path, *, tlr: TlrSemanticRecallProvider | None = None) -> ResearchService:
    store = SqliteStore(tmp_path / "cache")
    providers = ProviderSet(
        laws=OfficialLawProvider(LawTransport(), verify_webpage=False),
        constitutional=OfficialConstitutionalProvider(UnusedHttpTransport()),
        judgments=_empty_judgments(),
        tlr=tlr,
    )
    return ResearchService(store, ProviderObligationExecutor(store, providers))


def _advance(service: ResearchService, run_id: str) -> None:
    for index in range(20):
        run = service.get_run(run_id)
        assert run is not None
        if run.state is ResearchState.READY_FOR_DRAFT:
            return
        service.continue_run(run_id, f"step-{index}")
    raise AssertionError("run did not become ready")


def _advance_to_counter_authority(
    service: ResearchService,
    run_id: str,
    *,
    prefix: str,
) -> None:
    for index in range(20):
        run = service.get_run(run_id)
        assert run is not None
        pending = next(
            (
                item
                for item in run.obligations
                if item.status.value == "pending"
                and item.kind.value != "final_answer_validation"
            ),
            None,
        )
        assert pending is not None
        if pending.kind.value == "counter_authority":
            return
        service.continue_run(run_id, f"{prefix}-{index}")
    raise AssertionError("counter-authority obligation did not become pending")


def test_official_law_run_promotes_evidence_and_validates(tmp_path: Path) -> None:
    service = _service(tmp_path)
    run = service.create_run(
        "依示範責任法第7條應負何種責任？",
        mode=DataMode.OFFICIAL_ONLY,
        depth=ResearchDepth.QUICK,
    )

    _advance(service, run.run_id)
    state = service.get_state(run.run_id)
    evidence_id = service.store.list_evidence(run.run_id)[0].evidence_id
    validation = service.validate_answer(
        run.run_id,
        "行為人違反示範義務時，應負合成測試責任。",
        "validate-1",
        claim_bindings=[
            {
                "claim_id": "claim-law-7",
                "claim_text": "行為人違反示範義務時，應負合成測試責任。",
                "claim_type": "law_rule",
                "evidence_ids": [evidence_id],
            }
        ],
    )

    assert state["source_count"] == 1
    assert state["evidence_count"] == 1
    assert validation["decision"] == "qualified"
    assert validation["safe_to_present"] is True


def test_tlr_unavailable_downgrades_to_official_only(tmp_path: Path) -> None:
    transport = TlrFixtureTransport(TlrHttpResponse(503, {"detail": "busy"}))
    service = _service(
        tmp_path,
        tlr=TlrSemanticRecallProvider(transport=transport, max_retries=1),
    )
    run = service.create_run(
        "侵權行為裁判的舉證責任",
        mode=DataMode.HYBRID_VERIFIED,
        depth=ResearchDepth.STANDARD,
    )

    _advance(service, run.run_id)
    stored = service.get_run(run.run_id)

    assert stored is not None
    assert transport.calls == 2
    assert stored.effective_mode is DataMode.OFFICIAL_ONLY
    assert stored.semantic_recall_degraded is True
    assert stored.judgment_recall_incomplete is True


def test_tlr_candidate_alone_can_never_validate_answer(tmp_path: Path) -> None:
    transport = TlrFixtureTransport(
        TlrHttpResponse(
            200,
            {
                "results": [
                    {
                        "doc_id": "candidate-only",
                        "citation_text": "臺灣示範法院130年度測字第9號",
                        "snippet": "候選摘要不是法院理由。",
                        "citation_url": "https://judgment.judicial.gov.tw/synthetic",
                        "result_token": "temporary-handle",
                    }
                ]
            },
        )
    )
    service = _service(tmp_path, tlr=TlrSemanticRecallProvider(transport=transport))
    run = service.create_run(
        "侵權行為裁判的舉證責任",
        mode=DataMode.HYBRID_VERIFIED,
        depth=ResearchDepth.STANDARD,
    )

    _advance(service, run.run_id)
    validation = service.validate_answer(run.run_id, "候選裁判支持本項結論。", "validate-1")

    assert len(service.store.list_candidates(run.run_id)) == 1
    assert service.get_state(run.run_id)["evidence_count"] == 0
    assert validation["decision"] == "blocked"
    assert validation["answer_text"] is None


def test_official_website_search_candidate_is_downloaded_and_promoted(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "cache")
    judgments = JudgmentFlowTransport()
    providers = ProviderSet(
        laws=OfficialLawProvider(LawTransport(), verify_webpage=False),
        constitutional=OfficialConstitutionalProvider(UnusedHttpTransport()),
        judgments=OfficialJudgmentProvider(judgments),
    )
    service = ResearchService(store, ProviderObligationExecutor(store, providers))
    run = service.create_run(
        "合成侵權裁判舉證責任",
        mode=DataMode.OFFICIAL_ONLY,
        depth=ResearchDepth.STANDARD,
    )

    _advance(service, run.run_id)
    state = service.get_state(run.run_id)
    stored = service.get_run(run.run_id)

    assert state["source_count"] == 1
    assert state["evidence_count"] == 3
    assert stored is not None and stored.judgment_recall_incomplete is False
    assert stored.coverage.counter_authority_checked is False
    assert stored.coverage.bounded_query_scope is not None
    assert "COUNTER_AUTHORITY_RELATION_UNCLASSIFIED" in stored.coverage.limitations
    assert len(judgments.calls) >= 4


def test_counter_authority_progress_resumes_across_sqlite_without_resetting_budget(
    tmp_path: Path,
) -> None:
    store = SqliteStore(tmp_path / "cache")
    first_provider = CounterRetryJudgmentProvider()
    providers = ProviderSet(
        laws=OfficialLawProvider(LawTransport(), verify_webpage=False),
        constitutional=OfficialConstitutionalProvider(UnusedHttpTransport()),
        judgments=first_provider,
    )
    service = ResearchService(store, ProviderObligationExecutor(store, providers))
    run = service.create_run(
        "合成反向見解舉證責任",
        mode=DataMode.OFFICIAL_ONLY,
        depth=ResearchDepth.STANDARD,
    )
    _advance_to_counter_authority(service, run.run_id, prefix="counter-prep")

    first = service.continue_run(run.run_id, "counter-first")
    first_run = service.get_run(run.run_id)
    assert first_run is not None
    counter_obligation = next(
        item
        for item in first_run.obligations
        if item.kind.value == "counter_authority"
    )
    assert counter_obligation.status.value == "pending"
    assert counter_obligation.counter_authority_progress is not None
    first_progress = counter_obligation.counter_authority_progress
    assert first_progress["verification_attempts"] == 2
    assert first_provider.exact_calls == 2
    assert first["outcome"]["retryable"] is True

    # A fresh service instance proves the continuation state survived the
    # SQLite JSON roundtrip.  Replaying the old operation is idempotent and
    # must not issue another search or exact lookup.
    second_provider = CounterRetryJudgmentProvider()
    second_store = SqliteStore(tmp_path / "cache")
    second_service = ResearchService(
        second_store,
        ProviderObligationExecutor(
            second_store,
            ProviderSet(
                laws=OfficialLawProvider(LawTransport(), verify_webpage=False),
                constitutional=OfficialConstitutionalProvider(UnusedHttpTransport()),
                judgments=second_provider,
            ),
        ),
    )
    replay = second_service.continue_run(run.run_id, "counter-first")
    assert replay == first
    assert second_provider.search_calls == 0
    assert second_provider.exact_calls == 0

    resumed = second_service.continue_run(run.run_id, "counter-second")
    assert resumed["outcome"]["retryable"] is False
    assert second_provider.exact_calls == 1
    assert second_provider.search_calls == 1
    persisted = second_service.get_run(run.run_id)
    assert persisted is not None
    counter_after = next(
        item
        for item in persisted.obligations
        if item.kind.value == "counter_authority"
    )
    assert counter_after.status.value == "completed"
    assert counter_after.counter_authority_progress is None
    assert counter_after.counter_authority_diagnostic_codes == []
    assert (
        "COUNTER_AUTHORITY_VERIFICATION_TIMEOUT"
        not in persisted.coverage.timeout_reason_codes
    )
    assert persisted.coverage.partial_reason_codes.count("COUNTER_AUTHORITY_PARTIAL") == 1
    assert (
        persisted.coverage.counter_authority_checked is False
    )  # relation remains unclassified in the current preview
    assert first_progress["verification_attempts"] == 2


def test_clean_counter_scope_persists_bounded_absence_capability(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "cache")
    judgments = CleanCounterJudgmentProvider()
    providers = ProviderSet(
        laws=OfficialLawProvider(LawTransport(), verify_webpage=False),
        constitutional=OfficialConstitutionalProvider(UnusedHttpTransport()),
        judgments=judgments,
    )
    service = ResearchService(store, ProviderObligationExecutor(store, providers))
    run = service.create_run(
        "依示範責任法第7條判斷合成責任",
        mode=DataMode.OFFICIAL_ONLY,
        depth=ResearchDepth.STANDARD,
    )

    _advance(service, run.run_id)
    persisted = service.get_run(run.run_id)
    assert persisted is not None
    assert persisted.coverage.counter_authority_checked is True
    assert persisted.coverage.coverage_complete is True
    assert persisted.coverage.absence_claim_allowed is True
    assert persisted.coverage.bounded_query_scope is not None
    assert persisted.coverage.bounded_query_scope.strip()
    assert persisted.coverage.selected_provider_scope
    assert set(persisted.coverage.selected_provider_scope).issubset(
        set(persisted.coverage.successful_provider_scope)
    )

    finalization = service.get_finalization_contract(run.run_id)
    assert finalization["absence_claim"]["allowed"] is True
    assert finalization["absence_claim"]["scope"] == persisted.coverage.bounded_query_scope
    assert finalization["counter_authority"]["coverage_complete"] is True


def test_server_rejects_forged_empty_or_whitespace_counter_absence_scope(
    tmp_path: Path,
) -> None:
    service = ResearchService(
        SqliteStore(tmp_path / "cache"),
        ForgedAbsenceExecutor(),
    )
    run = service.create_run(
        "反向見解範圍防偽測試",
        mode=DataMode.OFFICIAL_ONLY,
        depth=ResearchDepth.STANDARD,
    )
    service.continue_run(run.run_id, "forged-absence")
    persisted = service.get_run(run.run_id)
    assert persisted is not None
    assert persisted.coverage.absence_claim_allowed is False
    assert persisted.coverage.coverage_complete is False
    finalization = service.get_finalization_contract(run.run_id)
    assert finalization["absence_claim"]["allowed"] is False


def test_direct_jid_recall_handoff_is_informational_before_official_verification(
    tmp_path: Path,
) -> None:
    store = SqliteStore(tmp_path / "cache")
    judgments = JudgmentFlowTransport()
    providers = ProviderSet(
        laws=OfficialLawProvider(LawTransport(), verify_webpage=False),
        constitutional=OfficialConstitutionalProvider(UnusedHttpTransport()),
        judgments=OfficialJudgmentProvider(judgments),
    )
    service = ResearchService(store, ProviderObligationExecutor(store, providers))
    jid = JudgmentFlowTransport.jid
    run = service.create_run(
        f"依示範責任法第7條及 {jid} 判斷責任？",
        mode=DataMode.OFFICIAL_ONLY,
        depth=ResearchDepth.STANDARD,
        include_counter_authority=False,
    )

    recall_run = None
    for index in range(20):
        current = service.get_run(run.run_id)
        assert current is not None
        if current.state is ResearchState.READY_FOR_DRAFT:
            break
        outcome = service.continue_run(run.run_id, f"direct-jid-{index}")["outcome"]
        if outcome.get("obligation") == "judgment_recall":
            recall_run = service.get_run(run.run_id)
            assert recall_run is not None
            assert recall_run.coverage.error_reason_codes == []
            assert recall_run.coverage.partial_reason_codes == []
            assert "EXACT_JUDGMENT_IDENTIFIER_WILL_USE_OFFICIAL_PROVIDER" in outcome[
                "warnings"
            ]
    assert recall_run is not None

    stored = service.get_run(run.run_id)
    assert stored is not None
    assert stored.coverage.judgment_checked is True
    assert stored.coverage.error_reason_codes == []
    assert stored.coverage.partial_reason_codes == []
    assert any(source.official_identifier == jid for source in store.list_sources(run.run_id))


def test_client_assisted_plan_skips_duplicate_judgment_search_and_verifies_exactly(
    tmp_path: Path,
) -> None:
    store = SqliteStore(tmp_path / "cache")
    judgments = JudgmentFlowTransport()
    providers = ProviderSet(
        laws=OfficialLawProvider(LawTransport(), verify_webpage=False),
        constitutional=OfficialConstitutionalProvider(UnusedHttpTransport()),
        judgments=OfficialJudgmentProvider(judgments),
    )
    service = ResearchService(store, ProviderObligationExecutor(store, providers))
    run = service.create_run(
        "請依指定法源分析本案",
        mode=DataMode.OFFICIAL_ONLY,
        depth=ResearchDepth.QUICK,
        include_counter_authority=False,
        discovery_mode=DiscoveryMode.CLIENT_ASSISTED,
    )
    plan = ResearchPlanProposal.model_validate(
        {
            "plan_id": "plan-exact-only",
            "issues": [
                {
                    "issue_id": "issue-liability",
                    "label": "責任成立",
                    "proposition": "是否成立法律責任？",
                    "category": "claim_basis",
                }
            ],
            "authority_locators": [
                {
                    "locator_id": "law-7",
                    "material_type": "law",
                    "citation": "示範責任法第7條",
                    "issue_ids": ["issue-liability"],
                },
                {
                    "locator_id": "judgment-42",
                    "material_type": "judgment",
                    "citation": "臺灣示範地方法院130年度測訴字第42號刑事判決",
                    "identifier": JudgmentFlowTransport.jid,
                    "purpose": "interpretation",
                    "issue_ids": ["issue-liability"],
                },
            ],
        }
    )
    service.register_research_plan(run.run_id, "register-plan", plan)

    _advance(service, run.run_id)
    stored = service.get_run(run.run_id)
    candidates = service.store.list_candidates(run.run_id)

    assert stored is not None
    assert stored.coverage.law_checked is True
    assert stored.coverage.judgment_checked is True
    assert stored.judgment_recall_incomplete is False
    assert len(candidates) == 1
    assert candidates[0].provider_id == "external_research_plan"
    assert all(method != "POST" for method, _ in judgments.calls)


def test_keyword_only_law_and_constitutional_handlers_do_not_claim_verified_coverage(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    run = service.create_run(
        "基本權保障的一般法律問題",
        mode=DataMode.OFFICIAL_ONLY,
        depth=ResearchDepth.QUICK,
    )

    # The constitutional transport is deliberately unavailable.  The current preview keeps
    # that required transient obligation pending for a later operation rather
    # than claiming workflow completion.
    for index in range(3):
        service.continue_run(run.run_id, f"keyword-step-{index}")
    stored = service.get_run(run.run_id)

    assert stored is not None
    assert stored.coverage.law_checked is False
    assert stored.coverage.constitutional_checked is False
    assert "LAW_KEYWORD_RESULTS_REQUIRE_EXACT_LOOKUP" in stored.coverage.limitations
    assert (
        "CONSTITUTIONAL_KEYWORD_RESULTS_REQUIRE_EXACT_LOOKUP"
        in stored.coverage.limitations
    )
    constitutional = next(
        item
        for item in stored.obligations
        if item.kind.value == "constitutional_research"
    )
    assert constitutional.status.value == "pending"
    assert stored.research_sufficiency.value == "retry_required"


def _tlr_promotion_service(
    tmp_path: Path,
    *,
    doc_id: str,
    citation_url: str,
    judgment_transport: TlrPromotionJudgmentTransport | None = None,
) -> tuple[ResearchService, TlrPromotionJudgmentTransport]:
    store = SqliteStore(tmp_path / "cache")
    judgment_transport = judgment_transport or TlrPromotionJudgmentTransport()
    tlr_transport = TlrFixtureTransport(
        TlrHttpResponse(
            200,
            {
                "results": [
                    {
                        "rank": 1,
                        "doc_id": doc_id,
                        "citation_text": "臺灣示範地方法院130年度測訴字第42號刑事判決",
                        "snippet": "外部候選摘要，不是法院理由。",
                        "citation_url": citation_url,
                    }
                ]
            },
        )
    )
    providers = ProviderSet(
        laws=OfficialLawProvider(LawTransport(), verify_webpage=False),
        constitutional=OfficialConstitutionalProvider(UnusedHttpTransport()),
        judgments=OfficialJudgmentProvider(judgment_transport),
        tlr=TlrSemanticRecallProvider(transport=tlr_transport),
    )
    return ResearchService(store, ProviderObligationExecutor(store, providers)), judgment_transport


def test_tlr_canonical_doc_id_is_promoted_through_official_exact_lookup(tmp_path: Path) -> None:
    jid = TlrPromotionJudgmentTransport.jid
    service, judgments = _tlr_promotion_service(
        tmp_path,
        doc_id=jid,
        citation_url=OfficialJudgmentProvider.official_document_url(jid),
    )
    run = service.create_run(
        "合成侵權裁判舉證責任",
        mode=DataMode.HYBRID_VERIFIED,
        depth=ResearchDepth.STANDARD,
    )

    _advance(service, run.run_id)
    official = [
        source
        for source in service.store.list_sources(run.run_id)
        if source.provider_id == OfficialJudgmentProvider.provider_id
    ]

    assert len(official) == 1
    assert official[0].official_identifier == jid
    assert official[0].metadata["origin_provider_id"] == "tlr_semantic_recall"
    assert official[0].metadata["identity_resolution_method"] == "typed_canonical_jid"
    assert service.get_state(run.run_id)["evidence_count"] == 3
    assert [method for method, _ in judgments.calls[:3]] == ["GET", "POST", "GET"]
    assert sum("data.aspx" in url for _, url in judgments.calls) == 1


def test_tlr_five_part_doc_id_is_completed_by_official_canonical_page(tmp_path: Path) -> None:
    jid = TlrPromotionJudgmentTransport.jid
    partial_jid = jid.rsplit(",", 1)[0]
    service, judgments = _tlr_promotion_service(
        tmp_path,
        doc_id=partial_jid,
        citation_url=OfficialJudgmentProvider.official_document_url(partial_jid),
    )
    run = service.create_run(
        "合成侵權裁判舉證責任",
        mode=DataMode.HYBRID_VERIFIED,
        depth=ResearchDepth.STANDARD,
    )

    _advance(service, run.run_id)
    official = [
        source
        for source in service.store.list_sources(run.run_id)
        if source.provider_id == OfficialJudgmentProvider.provider_id
    ]

    assert len(official) == 1
    assert official[0].official_identifier == jid
    assert official[0].metadata["identity_resolution_method"] == "provider_partial_jid"
    assert any(
        f"id={quote(partial_jid, safe='')}" in url for _, url in judgments.calls
    )


def test_tlr_five_part_doc_id_is_promoted_from_matching_legacy_page(tmp_path: Path) -> None:
    legacy_transport = TlrLegacyPromotionJudgmentTransport()
    jid = legacy_transport.jid
    service, judgments = _tlr_promotion_service(
        tmp_path,
        doc_id=jid,
        citation_url=OfficialJudgmentProvider.official_document_url(jid),
        judgment_transport=legacy_transport,
    )
    run = service.create_run(
        "合成侵權裁判舉證責任",
        mode=DataMode.HYBRID_VERIFIED,
        depth=ResearchDepth.STANDARD,
    )

    _advance(service, run.run_id)
    official = [
        source
        for source in service.store.list_sources(run.run_id)
        if source.provider_id == OfficialJudgmentProvider.provider_id
    ]

    assert len(official) == 1
    assert official[0].official_identifier == jid
    assert official[0].metadata["identifier_kind"] == "legacy_five_part_jid"
    assert official[0].metadata["resolved_official_identifier"] == jid
    assert official[0].metadata["resolved_canonical_jid"] is None
    assert official[0].metadata["identity_resolution_method"] == "provider_partial_jid"
    assert any(f"id={quote(jid, safe='')}" in url for _, url in judgments.calls)


def test_tlr_citation_url_jid_is_promoted_when_doc_id_is_opaque(tmp_path: Path) -> None:
    jid = TlrPromotionJudgmentTransport.jid
    service, _ = _tlr_promotion_service(
        tmp_path,
        doc_id="opaque-provider-document",
        citation_url=OfficialJudgmentProvider.official_document_url(jid),
    )
    run = service.create_run(
        "合成侵權裁判舉證責任",
        mode=DataMode.HYBRID_VERIFIED,
        depth=ResearchDepth.STANDARD,
    )

    _advance(service, run.run_id)
    official = [
        source
        for source in service.store.list_sources(run.run_id)
        if source.provider_id == OfficialJudgmentProvider.provider_id
    ]

    assert len(official) == 1
    assert official[0].metadata["identity_resolution_method"] == "typed_canonical_jid"
    assert official[0].metadata["provider_document_id"] == "opaque-provider-document"


def test_tlr_identity_mismatch_is_not_promoted(tmp_path: Path) -> None:
    wrong_jid = "DEMO,130,測,99,20990102,1"
    service, _ = _tlr_promotion_service(
        tmp_path,
        doc_id=wrong_jid,
        citation_url=OfficialJudgmentProvider.official_document_url(wrong_jid),
    )
    run = service.create_run(
        "合成侵權裁判舉證責任",
        mode=DataMode.HYBRID_VERIFIED,
        depth=ResearchDepth.STANDARD,
    )

    _advance(service, run.run_id)
    verification = service.continue_run(run.run_id, "step-4")
    official = [
        source
        for source in service.store.list_sources(run.run_id)
        if source.provider_id == OfficialJudgmentProvider.provider_id
    ]

    assert official == []
    assert "CANDIDATE_OFFICIAL_ID_MISMATCH" in verification["outcome"]["warnings"]


def test_tlr_candidate_keeps_recall_progress_when_official_search_is_unavailable(
    tmp_path: Path,
) -> None:
    judgments = UnavailableSearchTlrPromotionTransport()
    service, _ = _tlr_promotion_service(
        tmp_path,
        doc_id=judgments.jid,
        citation_url=OfficialJudgmentProvider.official_document_url(judgments.jid),
        judgment_transport=judgments,
    )
    run = service.create_run(
        "合成侵權裁判舉證責任",
        mode=DataMode.HYBRID_VERIFIED,
        depth=ResearchDepth.STANDARD,
        include_counter_authority=False,
    )

    # query understanding, privacy screen, law research, then judgment recall.
    for index in range(4):
        service.continue_run(run.run_id, f"recall-step-{index}")
    after_recall = service.get_run(run.run_id)
    assert after_recall is not None
    recall = next(
        item
        for item in after_recall.obligations
        if item.kind is ResearchObligationKind.JUDGMENT_RECALL
    )
    assert recall.status is ResearchObligationStatus.COMPLETED
    assert after_recall.judgment_recall_incomplete is False
    assert "OFFICIAL_SOURCE_UNAVAILABLE" in after_recall.coverage.partial_reason_codes
    assert "OFFICIAL_SOURCE_UNAVAILABLE" not in after_recall.coverage.error_reason_codes

    verification = service.continue_run(run.run_id, "official-verification")
    assert verification["outcome"]["added_eligible_evidence_count"] > 0


def test_unavailable_historical_law_version_blocks_final_answer(tmp_path: Path) -> None:
    service = _service(tmp_path)
    run = service.create_run(
        "依示範責任法第7條應負何種責任？",
        mode=DataMode.OFFICIAL_ONLY,
        depth=ResearchDepth.QUICK,
        as_of_date=date(2020, 1, 1),
    )

    _advance(service, run.run_id)
    validation = service.validate_answer(
        run.run_id,
        "行為人違反示範義務時，應負合成測試責任。",
        "validate-history",
    )

    assert validation["decision"] == "blocked"
    assert "RESEARCH_INSUFFICIENT" in validation["blockers"]


def test_fresh_official_snapshot_is_reused_across_runs(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "cache")
    laws = CountingLawProvider()
    providers = ProviderSet(
        laws=laws,
        constitutional=OfficialConstitutionalProvider(UnusedHttpTransport()),
        judgments=_empty_judgments(),
    )
    service = ResearchService(store, ProviderObligationExecutor(store, providers))

    for index in range(2):
        run = service.create_run(
            "依示範責任法第7條應負何種責任？",
            mode=DataMode.OFFICIAL_ONLY,
            depth=ResearchDepth.QUICK,
        )
        _advance(service, run.run_id)
        assert service.get_state(run.run_id)["evidence_count"] == 1
        assert store.get_evidence(store.list_evidence(run.run_id)[0].evidence_id, run_id=run.run_id)

    assert laws.exact_calls == 1


def test_tlr_degradation_without_judgment_recall_stays_insufficient(
    tmp_path: Path,
) -> None:
    transport = TlrFixtureTransport(TlrHttpResponse(503, {"detail": "busy"}))
    service = _service(
        tmp_path,
        tlr=TlrSemanticRecallProvider(transport=transport, max_retries=0),
    )
    run = service.create_run(
        "依示範責任法第7條應負何種責任？",
        mode=DataMode.HYBRID_VERIFIED,
        depth=ResearchDepth.STANDARD,
    )
    _advance(service, run.run_id)
    evidence_id = service.store.list_evidence(run.run_id)[0].evidence_id

    validation = service.validate_answer(
        run.run_id,
        "行為人違反示範義務時，應負合成測試責任。",
        "validate-qualified",
        claim_bindings=[
            {
                "claim_id": "claim-law-7",
                "claim_text": "行為人違反示範義務時，應負合成測試責任。",
                "claim_type": "law_rule",
                "evidence_ids": [evidence_id],
            }
        ],
    )

    assert validation["decision"] == "blocked"
    assert validation["safe_to_present"] is False
    # TLR is an optional recall enhancer and is not re-run after the
    # server-owned hybrid-to-official downgrade.  With no official judgment
    # candidate, the run remains fail-closed rather than being qualified from
    # law evidence alone.
    assert "RESEARCH_INSUFFICIENT" in validation["blockers"]


def test_expired_cache_revalidation_failure_is_explicit_and_not_reused(
    tmp_path: Path,
) -> None:
    store = SqliteStore(tmp_path / "cache")
    laws = FailingRevalidationLawProvider()
    service = ResearchService(
        store,
        ProviderObligationExecutor(
            store,
            ProviderSet(
                laws=laws,
                constitutional=OfficialConstitutionalProvider(UnusedHttpTransport()),
                judgments=_empty_judgments(),
            ),
        ),
    )
    first = service.create_run(
        "依示範責任法第7條應負何種責任？",
        mode=DataMode.OFFICIAL_ONLY,
        depth=ResearchDepth.QUICK,
    )
    _advance(service, first.run_id)

    second = service.create_run(
        "依示範責任法第7條應負何種責任？",
        mode=DataMode.OFFICIAL_ONLY,
        depth=ResearchDepth.QUICK,
    )
    warnings: list[str] = []
    for index in range(10):
        run = service.get_run(second.run_id)
        assert run is not None
        if run.state is ResearchState.READY_FOR_DRAFT:
            break
        step = service.continue_run(second.run_id, f"revalidate-{index}")
        warnings.extend((step.get("outcome") or {}).get("warnings", []))

    assert laws.exact_calls == 2
    assert "SOURCE_REVALIDATION_FAILED" in warnings
    assert service.get_state(second.run_id)["evidence_count"] == 0


def test_expired_cache_is_replaced_after_successful_revalidation(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "cache")
    laws = CountingLawProvider(snapshot_ttl=timedelta(microseconds=1))
    service = ResearchService(
        store,
        ProviderObligationExecutor(
            store,
            ProviderSet(
                laws=laws,
                constitutional=OfficialConstitutionalProvider(UnusedHttpTransport()),
                judgments=_empty_judgments(),
            ),
        ),
    )

    source_ids: list[str] = []
    for index in range(2):
        run = service.create_run(
            "依示範責任法第7條應負何種責任？",
            mode=DataMode.OFFICIAL_ONLY,
            depth=ResearchDepth.QUICK,
        )
        _advance(service, run.run_id)
        sources = store.list_sources(run.run_id)
        assert len(sources) == 1
        assert service.get_state(run.run_id)["evidence_count"] == 1
        source_ids.append(sources[0].source_id)

    assert laws.exact_calls == 2
    assert source_ids[0] != source_ids[1]
