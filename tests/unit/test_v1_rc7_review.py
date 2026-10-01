"""Synthetic regressions for the complete RC6 review batch (#35–39)."""
import asyncio
from dataclasses import replace
from datetime import date
import io
import json
import zipfile

import pytest

from alr_tw.contracts.providers import DataMode, ProviderResultStatus as Status
from alr_tw.contracts.research import ResearchDepth, ResearchObligationKind as Kind
from alr_tw.providers.official.judgments import OfficialJudgmentProvider
from alr_tw.providers.official.http import HttpResponse
from alr_tw.research.provider_executor import _FORMAL_JUDGMENT_CITATION
from alr_tw.research.query_preparation import prepare_query, time_hints
from test_v060_official_judgment_provider import (
    FixtureSiteTransport, JID, _response, _search_form, _result_frame, _result_list, _detail_page,
)
from test_v060_provider_research_integration import _service, _law_archive

ZERO = '<div>查詢結果 <span class="badge">0</span></div>'


@pytest.mark.parametrize('page,empty', [
    (ZERO, True),
    ('<p>查無您所查詢之裁判資料</p>', True),
    ('<p>查無符合條件之裁判</p>', True),
    ('<div>通知<span class="badge">0</span></div>', False),
    ('<p>查詢結果</p><span class="badge">0</span>', False),
    ('<p>未知頁面 0</p>', False),
    (ZERO + '<form><input type="password"></form>', False),
    (ZERO + '<p>請登入</p>', False),
    (ZERO + '<p>請完成驗證</p>', False),
    (ZERO + '<p>系統錯誤</p>', False),
    (ZERO.replace('>0<', '>x<'), False),
    (ZERO.replace('>0<', '>1<'), False),
    (ZERO + '<a href="data.aspx?ty=JD&amp;id=broken">合成裁判</a>', False),
])
def test_search_empty_requires_result_label_and_valid_page(page, empty):
    transport = FixtureSiteTransport([_response(_search_form()), _response(page)])
    result = asyncio.run(OfficialJudgmentProvider(transport).search('合成問題甲'))
    assert result.status == (Status.NOT_FOUND if empty else Status.ERROR)
    assert not result.candidates and not result.evidence_ids and not result.source_ids
    assert len(transport.calls) == 2


def test_nonzero_hits_and_broken_followup_page_remain_distinct():
    for page, expected in [(_result_list(JID), Status.FOUND), ('未知頁面', Status.ERROR), (ZERO, Status.NOT_FOUND)]:
        transport = FixtureSiteTransport([_response(_search_form()), _response(_result_frame()), _response(page)])
        result = asyncio.run(OfficialJudgmentProvider(transport).search('合成問題甲'))
        assert result.status == expected
        assert bool(result.candidates) == (expected == Status.FOUND)
        assert not result.evidence_ids


@pytest.mark.parametrize('query', [
    '租期三年應如何計算？', '請求權時效為10年嗎？', '一年內可以申請嗎？',
    '法院如何處理三年以下有期徒刑？', '契約成立的要件是什麼？',
    '簽約需要哪些要件？', '事故責任如何判斷？', '期限為100年',
])
def test_duration_and_generic_institution_do_not_require_historical_law(tmp_path, query):
    hints = time_hints(query)
    assert not hints['date_mentions'] and not hints['needs_time_context']
    run = _service(tmp_path).create_run(query, mode=DataMode.OFFICIAL_ONLY, depth=ResearchDepth.QUICK)
    assert Kind.LEGAL_TIME_CONTEXT not in {o.kind for o in run.obligations}


def test_actual_date_and_duration_reconcile_without_inventing_year():
    query = '2020年5月1日簽約，租期三年。'
    hints = time_hints(query, date(2020, 5, 1))
    assert [m['value'] for m in hints['date_mentions']] == ['2020-05-01']
    assert not hints['warnings'] and not hints['requires_clarification']
    assert time_hints('民國三年五月')['date_mentions'][0]['value'] == '1914-05'


@pytest.mark.parametrize('historical', [False, True])
def test_complete_service_preserves_real_history_only(tmp_path, historical):
    service = _service(tmp_path)
    query = '示範責任法第7條，' + ('2020年5月1日簽約' if historical else '期限為三年')
    run = service.create_run(query, mode=DataMode.OFFICIAL_ONLY, depth=ResearchDepth.QUICK)
    service.execute_run_to_completion(run.run_id)
    state = service.get_state(run.run_id)
    assert ('HISTORICAL_LAW_VERSION_UNSUPPORTED' in state['run']['coverage']['limitations']) == historical
    assert state['run']['query'] == query
    if historical:
        assert state['answer_mode'] == 'refusal_only'
    else:
        assert state['evidence_count'] > 0
        assert state['answer_mode'] != 'refusal_only'


@pytest.mark.parametrize('surface,term', [('房東', '出租人'), ('押金', '押租金')])
def test_real_law_search_finds_formal_term_without_promoting_evidence(tmp_path, surface, term):
    service = _service(tmp_path)
    class CatalogTransport:
        async def get(self, url, **kwargs):
            with zipfile.ZipFile(io.BytesIO(_law_archive())) as old:
                document = json.loads(old.read('ChLaw.json'))
            document['Laws'][0]['LawArticles'][0]['ArticleContent'] = '出租人與押租金之合成規定。'
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w') as archive:
                archive.writestr('ChLaw.json', json.dumps(document))
            return HttpResponse(200, buffer.getvalue(), {}, url)
    provider = service.executor.providers.laws
    provider.transport = CatalogTransport()
    assert asyncio.run(provider.search(surface)).status == Status.NOT_FOUND
    assert asyncio.run(provider.search(surface + ' ' + term)).status == Status.NOT_FOUND
    assert asyncio.run(provider.search(term)).status == Status.FOUND
    run = service.create_run(surface, mode=DataMode.OFFICIAL_ONLY, depth=ResearchDepth.QUICK)
    service.continue_run(run.run_id, 'understand')
    result = service.continue_run(run.run_id, 'law')
    assert [c['status'] for c in result['outcome']['provider_calls']] == ['not_found', 'found']
    assert not service.store.list_evidence(run.run_id)
    assert service.get_run(run.run_id).query == surface
    suggestion = prepare_query(surface)['law_search_queries'][1]
    assert suggestion['surface'] == surface and suggestion['query'] == term
    assert suggestion['relation'] == 'approximate'


@pytest.mark.parametrize('year', ['130年度', '130年'])
@pytest.mark.parametrize('suffix', ['', '民事', '民事判決', '判決', '裁定'])
def test_formal_variants_route_exactly_without_time_obligation(tmp_path, year, suffix):
    citation = f'臺灣示範地方法院{year}測字第42號{suffix}'
    parsed = OfficialJudgmentProvider.normalize_formal_citation(citation)
    assert parsed is not None and parsed.year == '130' and parsed.case == '測'
    assert _FORMAL_JUDGMENT_CITATION.search(citation).group('citation') == citation
    prep = prepare_query(citation)
    assert prep['exact_citation'] and not prep['time_hints']['date_mentions']
    service = _service(tmp_path)
    run = service.create_run(citation, mode=DataMode.OFFICIAL_ONLY, depth=ResearchDepth.QUICK)
    assert Kind.LEGAL_TIME_CONTEXT not in {o.kind for o in run.obligations}
    kind = '裁定' if suffix == '裁定' else '判決'
    page = _result_list(JID).replace('判決', kind)
    transport = FixtureSiteTransport([_response(_result_frame()), _response(page), _response(_detail_page().replace("判決", kind))])
    result, source, _ = asyncio.run(OfficialJudgmentProvider(transport).exact_lookup(citation))
    assert result.status == Status.FOUND and source is not None


@pytest.mark.parametrize('empty', [False, True])
def test_counter_authority_distinguishes_zero_from_parse_failure(tmp_path, empty):
    from test_v060_provider_research_integration import _advance_to_counter_authority
    service = _service(tmp_path)
    page = ZERO if empty else '<p>未知頁面</p>'
    transport = FixtureSiteTransport([response for _ in range(20)
        for response in (_response(_search_form()), _response(page))])
    service.executor.providers = replace(service.executor.providers, judgments=OfficialJudgmentProvider(transport))
    run = service.create_run('示範責任法第7條', mode=DataMode.OFFICIAL_ONLY, depth=ResearchDepth.STANDARD)
    _advance_to_counter_authority(service, run.run_id, prefix='before-counter')
    before = service.store.list_evidence(run.run_id)
    outcome = service.continue_run(run.run_id, 'counter')['outcome']
    stored = service.get_run(run.run_id)
    assert stored.coverage.bounded_query_scope is not None
    assert all(call['status'] == ('not_found' if empty else 'error') for call in outcome['provider_calls'])
    assert not service.store.list_candidates(run.run_id)
    assert service.store.list_evidence(run.run_id) == before
    assert stored.coverage.counter_authority_checked == empty


def test_formal_kind_conflict_and_unknown_resolution_fail_closed():
    citation = '臺灣示範地方法院130年測字第42號裁定'
    # Even a matching search title cannot override contradictory official text.
    transport = FixtureSiteTransport([_response(_result_frame()),
        _response(_result_list(JID).replace('判決', '裁定')), _response(_detail_page())])
    result, source, evidence = asyncio.run(OfficialJudgmentProvider(transport).exact_lookup(citation))
    assert result.status == Status.ERROR and result.message == 'JUDGMENT_KIND_MISMATCH'
    assert source is None and not evidence
    transport = FixtureSiteTransport([_response('<p>未知頁面</p>')])
    result, source, evidence = asyncio.run(OfficialJudgmentProvider(transport).exact_lookup(citation))
    assert result.status == Status.ERROR and source is None and not evidence
    transport = FixtureSiteTransport([_response(_result_frame()), _response('<p>未知頁面</p>')])
    result, source, evidence = asyncio.run(OfficialJudgmentProvider(transport).exact_lookup(citation))
    assert result.status == Status.ERROR and source is None and not evidence


@pytest.mark.parametrize('location', ['registered_id', 'unknown_id', 'draft', 'claim', 'citation', 'claim_id'])
def test_registered_law_digest_is_not_phone_but_prose_stays_screened(tmp_path, monkeypatch, location):
    from alr_tw.research.draft_workspace import review_draft
    from alr_tw.verification.output_privacy import screen_answer_output
    from test_v014_drafting import draft
    service = _service(tmp_path)
    run = service.create_run('示範責任法第7條', mode=DataMode.OFFICIAL_ONLY, depth=ResearchDepth.QUICK)
    service.execute_run_to_completion(run.run_id)
    evidence = service.store.list_evidence(run.run_id)[0]
    source = service.store.list_sources(run.run_id)[0]
    # Synthetic digest with a phone-shaped substring; never an actual contact.
    digits = '0' + '2' * 9
    source_id = 'src_law_' + 'a' * 7 + digits + 'b' * 7
    evidence_id = 'ev_' + source_id + '_7902699be42c'
    assert not screen_answer_output(evidence_id).allowed
    if location != 'unknown_id':
        service.store.save_source(run.run_id, source.model_copy(update={'source_id': source_id}))
        service.store.save_evidence(run.run_id, evidence.model_copy(update={
            'source_id': source_id, 'evidence_id': evidence_id}))
    answer, bindings = draft(evidence_id)
    if location == 'draft':
        answer += digits
    elif location == 'claim':
        bindings[0]['claim_text'] += digits
    elif location == 'citation':
        bindings[0]['citation_occurrences'][0]['citation_text'] += digits
    elif location == 'claim_id':
        bindings[0]['claim_id'] = digits
    original = json.dumps(bindings)
    result = review_draft(service.store, run.run_id, answer, bindings)
    assert (result['privacy_status'] == 'safe') == (location == 'registered_id')
    assert not result['safe_to_present'] and not result['final_answer_authorized']
    assert json.dumps(bindings) == original
    if location == 'registered_id':
        import sys
        from alr_tw.contracts.semantic_verifier import SemanticVerifierResult
        from alr_tw.research.semantic_advisor import AdvisorConfig, CommandSemanticVerifier, advise_draft
        def verify(self, request):
            return SemanticVerifierResult(request_id=request.request_id, run_id=request.run_id,
                plugin_id=self.plugin_id, plugin_version=self.plugin_version, status='completed',
                findings=[{'target_id': request.targets[0].target_id, 'outcome': 'uncertain',
                    'referenced_source_ids': [source_id], 'referenced_evidence_ids': [evidence_id]}])
        monkeypatch.setattr(CommandSemanticVerifier, 'verify', verify)
        advice = advise_draft(service.store, run.run_id,
            {'answer_text': answer, 'claim_bindings': bindings},
            AdvisorConfig(command=[sys.executable], model='gpt-5.6-luna'))
        assert advice['review']['decision'] in {'accepted', 'partial'}
        assert not advice['final_answer_authorized']
