from __future__ import annotations

import io
import json
import zipfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from alr_tw.contracts.providers import (
    DataMode,
    ProviderErrorCode,
    ProviderResult,
    ProviderResultStatus,
)
from alr_tw.contracts.research import ResearchDepth, ResearchState
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
        assert form["jud_kw"] == "合成侵權裁判舉證責任"
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


def test_official_law_run_promotes_evidence_and_validates(tmp_path: Path) -> None:
    service = _service(tmp_path)
    run = service.create_run(
        "依示範責任法第7條應負何種責任？",
        mode=DataMode.OFFICIAL_ONLY,
        depth=ResearchDepth.QUICK,
    )

    _advance(service, run.run_id)
    state = service.get_state(run.run_id)
    validation = service.validate_answer(
        run.run_id,
        "行為人違反示範義務時，應負合成測試責任。",
        "validate-1",
    )

    assert state["source_count"] == 1
    assert state["evidence_count"] == 1
    assert validation["decision"] == "validated"
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
    assert [method for method, _ in judgments.calls] == ["GET", "POST", "GET", "GET"]


def _tlr_promotion_service(
    tmp_path: Path,
    *,
    doc_id: str,
    citation_url: str,
) -> tuple[ResearchService, TlrPromotionJudgmentTransport]:
    store = SqliteStore(tmp_path / "cache")
    judgment_transport = TlrPromotionJudgmentTransport()
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
    assert [method for method, _ in judgments.calls] == ["GET", "POST", "GET"]


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


def test_unavailable_historical_law_version_blocks_final_answer(tmp_path: Path) -> None:
    service = _service(tmp_path)
    run = service.create_run(
        "依示範責任法第7條應負何種責任？",
        mode=DataMode.OFFICIAL_ONLY,
        depth=ResearchDepth.QUICK,
        as_of_date=date(2030, 1, 1),
    )

    _advance(service, run.run_id)
    validation = service.validate_answer(
        run.run_id,
        "行為人違反示範義務時，應負合成測試責任。",
        "validate-history",
    )

    assert validation["decision"] == "blocked"
    assert "HISTORICAL_LAW_VERSION_UNSUPPORTED" in validation["blockers"]


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


def test_tlr_degradation_with_sufficient_official_law_evidence_is_qualified(
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

    validation = service.validate_answer(
        run.run_id,
        "行為人違反示範義務時，應負合成測試責任。",
        "validate-qualified",
    )

    assert validation["decision"] == "qualified"
    assert validation["decision_code"] == "ANSWER_QUALIFIED"
    assert validation["safe_to_present"] is True
    assert validation["required_qualification"]


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
