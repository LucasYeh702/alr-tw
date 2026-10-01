"""Pure synthetic query preparation and bounded provider integration."""
from datetime import date
import json
import socket

import pytest

from alr_tw.budget import charge_http_request
from alr_tw.config import Settings
from alr_tw.contracts.providers import DataMode, ProviderResult, ProviderResultStatus as Status
from alr_tw.contracts.research import ResearchDepth, ResearchObligationKind as Kind
from alr_tw.providers.official.law_aliases import LAW_ALIASES
from alr_tw.research.query_preparation import (
    MAX_EXPANSIONS, MAX_QUERY_CODE_POINTS, TERMS, prepare_query, time_hints,
)
from alr_tw.research.service import ResearchService
from alr_tw.storage.sqlite_store import SqliteStore
from tw_legal_rag_mcp.mcp_server.server import McpSession
from test_v060_provider_research_integration import _service


@pytest.mark.parametrize('query', [None, 1, True, '', '  ', '甲\x00乙', '甲\ud800',
                                  '甲\u202e乙', '甲' * (MAX_QUERY_CODE_POINTS + 1)])
def test_invalid_input_is_bounded_content_free(query):
    with pytest.raises(ValueError, match='^RESEARCH_QUERY_INVALID$'):
        prepare_query(query)


def test_preparation_preserves_facts_and_never_connects(monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError('pure preparation attempted network')
    monkeypatch.setattr(socket, 'socket', forbidden)
    query = '房東甲不得向房客乙收30元押金，示範責任法第7條尚待查證。'
    result = prepare_query(query)
    assert result['original_query'] == query
    assert result['search_queries'] == [{'query': query, 'relation': 'original', 'weight': 1.0}]
    assert result['exact_citation']
    assert not result['answer_authorized']
    query = '房東甲不得向房客乙收30元押金'
    result = prepare_query(query)
    assert 1 < len(result['search_queries']) <= MAX_EXPANSIONS
    assert all(item['query'].startswith(query) for item in result['search_queries'])
    assert {item['relation'] for item in result['term_candidates']} == {'approximate', 'related'}
    assert result['requires_clarification']


def test_lexicon_aliases_and_relations_do_not_conflate():
    assert len(TERMS) == len(set(TERMS)) == 14
    assert not {row[0] for row in TERMS} & set(LAW_ALIASES)
    result = prepare_query('違建與監護權探視押金')
    assert {t['relation'] for t in result['term_candidates']} == {'equivalent', 'approximate', 'related'}
    assert 'EXPANSION_LIMIT' in result['warnings']
    assert len(result['search_queries']) == 6
    assert len({q['query'] for q in result['search_queries']}) == 6
    assert prepare_query('甲詞有兩種法律解釋')['requires_clarification']
    assert len(prepare_query('甲詞有兩種法律解釋')['search_queries']) == 1


def test_long_query_is_preserved_but_not_expanded():
    query = '甲' * 2050 + '房東'
    result = prepare_query(query)
    assert result['search_queries'][0]['query'] == query
    assert len(result['search_queries']) == 1
    assert 'EXPANSION_LIMIT' in result['warnings']


@pytest.mark.parametrize('query', ['示範責任法第七條房東', '示範責任法第7條押金',
                                  '示範法院113年度測字第1號違建', 'DEMO,113,測,1,20990101,1 房東'])
def test_precise_citations_never_expand(query):
    assert len(prepare_query(query)['search_queries']) == 1


@pytest.mark.parametrize('query,value,precision', [
    ('民國一百零九年五月發生事件，但引用一百一十四年度裁判', '2020-05', 'month'),
    ('民國109年5月1日發生事件', '2020-05-01', 'day'),
    ('一〇九年五月一日發生事件', '2020-05-01', 'day'),
    ('西元2020年5月1日發生事件', '2020-05-01', 'day'),
    ('2020-05-01發生事件', '2020-05-01', 'day'),
    ('2020/5/1發生事件', '2020-05-01', 'day'),
    ('２０２０年５月１日發生事件', '2020-05-01', 'day'),
    ('民國109年發生事件', '2020', 'year'),
])
def test_dates_retain_precision_without_defaults(query, value, precision):
    hints = prepare_query(query)['time_hints']
    assert len(hints['date_mentions']) == 1
    assert hints['date_mentions'][0]['value'] == value
    assert hints['date_mentions'][0]['precision'] == precision
    assert hints['suggested_as_of_date'] == (value if precision == 'day' else None)
    assert hints['explicit_as_of_date'] is None and not hints['automatically_applied']
    assert hints['requires_clarification']


@pytest.mark.parametrize('query', ['113年度測字第1號', '第109條', 'DEMO,113,測,1,20990101,1', '第109年條'])
def test_identifiers_are_not_event_dates(query):
    assert not time_hints(query)['date_mentions']


@pytest.mark.parametrize('query,warning', [
    ('2020年2月30日發生', 'INVALID_DATE_MENTION'),
    ('民國109年13月發生', 'INVALID_DATE_MENTION'),
    ('2020年5月發生', 'INCOMPLETE_DATE_PRECISION'),
    ('2020年5月1日或2021年5月1日發生', 'MULTIPLE_DATE_MENTIONS'),
    ('行為時法如何適用', 'EVENT_DATE_MISSING'),
    ('2020年5月1日發生' * 20, 'DATE_MENTION_LIMIT'),
])
def test_ambiguous_dates_are_not_silently_resolved(query, warning):
    hints = time_hints(query)
    assert warning in hints['warnings']
    assert hints['requires_clarification']
    assert hints['suggested_as_of_date'] is None
    assert len(hints['date_mentions']) <= 16


def test_explicit_date_is_never_overwritten():
    explicit = date(2022, 2, 2)
    hints = prepare_query('2020年5月1日發生事件', as_of_date=explicit)['time_hints']
    assert hints['explicit_as_of_date'] == '2022-02-02'
    assert 'EXPLICIT_DATE_REQUIRES_RECONCILIATION' in hints['warnings']
    assert not hints['automatically_applied']


def test_mcp_and_restart_expose_identical_advisory_preparation(tmp_path):
    service = ResearchService(SqliteStore(tmp_path / 'cache'))
    session = McpSession(ready=True, settings=Settings(), research_service=service)
    query = '民國一百零九年五月房東甲未退30元押金'
    response = session.handle_message({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
        'params': {'name': 'research_legal_question', 'arguments': {'query': query,
            'constraints': {'research_depth': 'quick', 'as_of_date': '2021-01-01'}}}})
    data = json.loads(response['result']['content'][0]['text'])['data']
    run_id = data['run']['run_id']
    assert data['run']['query'] == query
    assert data['run']['as_of_date'] == '2021-01-01'
    assert Kind.LEGAL_TIME_CONTEXT.value in {o['kind'] for o in data['run']['obligations']}
    restarted = ResearchService(SqliteStore(tmp_path / 'cache'))
    state = restarted.get_state(run_id)
    assert state['query_preparation'] == data['query_preparation']
    assert not state['query_preparation']['answer_authorized']


@pytest.mark.parametrize('kind', ['law', 'judgment'])
@pytest.mark.parametrize('terminal,expected', [('found', 2), ('error', 1), ('empty', 4)])
def test_provider_executes_original_then_bounded_official_fallback(tmp_path, monkeypatch, kind, terminal, expected):
    service = _service(tmp_path)
    provider = service.executor.providers.laws if kind == 'law' else service.executor.providers.judgments
    calls = []
    async def search(query, **kwargs):
        calls.append(query)
        status = Status.ERROR if terminal == 'error' else (
            Status.FOUND if terminal == 'found' and len(calls) == 2 else Status.NOT_FOUND)
        return ProviderResult(status=status, provider_id=provider.provider_id)
    monkeypatch.setattr(provider, 'search', search)
    query = '房東押金' if kind == 'law' else '法院如何處理房東押金'
    run = service.create_run(query, mode=DataMode.OFFICIAL_ONLY, depth=ResearchDepth.QUICK)
    service.continue_run(run.run_id, 'understand')
    service.continue_run(run.run_id, 'research')
    assert len(calls) == expected
    assert calls[0] == query
    key = 'law_search_queries' if kind == 'law' else 'search_queries'
    assert calls == [item['query'] for item in prepare_query(query)[key]][:expected]
    assert not service.store.list_evidence(run.run_id)


@pytest.mark.parametrize('kind', ['law', 'judgment'])
def test_expansion_uses_persistent_http_budget(tmp_path, monkeypatch, kind):
    service = _service(tmp_path)
    service.budget_defaults = service.budget_defaults.model_copy(update={'max_http_requests': 2})
    provider = service.executor.providers.laws if kind == "law" else service.executor.providers.judgments
    calls = []
    async def search(query, **kwargs):
        charge_http_request()
        calls.append(query)
        return ProviderResult(status=Status.NOT_FOUND, provider_id=provider.provider_id)
    monkeypatch.setattr(provider, 'search', search)
    query = '房東押金' if kind == 'law' else '法院如何處理房東押金'
    run = service.create_run(query, mode=DataMode.OFFICIAL_ONLY, depth=ResearchDepth.QUICK)
    service.continue_run(run.run_id, 'understand')
    result = service.continue_run(run.run_id, 'recall')
    assert result['outcome']['warnings'] == ['HTTP_BUDGET_EXHAUSTED']
    assert len(calls) == 2
    assert service.get_run(run.run_id).budget.used_http_requests == 2
    assert service.get_run(run.run_id).budget.exhausted_reason == 'HTTP_BUDGET_EXHAUSTED'
    assert not service.store.list_evidence(run.run_id)


def test_time_suggestions_cannot_satisfy_historical_verification(tmp_path):
    service = _service(tmp_path)
    run = service.create_run('行為時法：民國109年5月發生事件', mode=DataMode.OFFICIAL_ONLY,
                             depth=ResearchDepth.QUICK)
    assert run.as_of_date is None
    service.execute_run_to_completion(run.run_id)
    state = service.get_state(run.run_id)
    assert 'HISTORICAL_LAW_VERSION_UNSUPPORTED' in state['run']['coverage']['limitations']
    assert state['answer_mode'] == 'refusal_only'
    assert not state['query_preparation']['time_hints']['automatically_applied']


def test_expansion_stops_at_deadline(tmp_path, monkeypatch):
    import asyncio
    service = _service(tmp_path)
    service.budget_defaults = service.budget_defaults.model_copy(update={'max_seconds': 0.05})
    calls = []
    async def search(query, **kwargs):
        calls.append(query)
        if len(calls) > 1:
            await asyncio.sleep(1)
        return ProviderResult(status=Status.NOT_FOUND, provider_id=service.executor.providers.judgments.provider_id)
    monkeypatch.setattr(service.executor.providers.judgments, 'search', search)
    run = service.create_run('法院如何處理房東押金', mode=DataMode.OFFICIAL_ONLY, depth=ResearchDepth.QUICK)
    service.continue_run(run.run_id, 'understand')
    result = service.continue_run(run.run_id, 'recall')
    assert result['outcome']['warnings'] == ['TIMEOUT_BUDGET_EXHAUSTED']
    assert len(calls) <= 2


def test_external_provider_receives_original_only(tmp_path, monkeypatch):
    from dataclasses import replace
    from alr_tw.providers.tlr import screen_external_query
    service = _service(tmp_path)
    calls = []
    class External:
        provider_id = 'synthetic-external'
        async def search(self, query, **kwargs):
            calls.append(query)
            return ProviderResult(status=Status.NOT_FOUND, provider_id=self.provider_id), [], screen_external_query(query)
    service.executor.providers = replace(service.executor.providers, candidate_recall=External())
    async def official(query, **kwargs):
        return ProviderResult(status=Status.NOT_FOUND, provider_id=service.executor.providers.judgments.provider_id)
    monkeypatch.setattr(service.executor.providers.judgments, 'search', official)
    query = '法院如何處理房東押金'
    run = service.create_run(query, mode=DataMode.HYBRID_VERIFIED, depth=ResearchDepth.QUICK)
    service.continue_run(run.run_id, 'understand')
    service.continue_run(run.run_id, 'privacy')
    service.continue_run(run.run_id, 'recall')
    assert calls == [query]


def test_exact_law_lookup_does_not_execute_search_suggestions(tmp_path, monkeypatch):
    service = _service(tmp_path)
    async def forbidden(*args, **kwargs):
        raise AssertionError('precise lookup must not execute expansion search')
    monkeypatch.setattr(service.executor.providers.laws, 'search', forbidden)
    monkeypatch.setattr(service.executor.providers.judgments, 'search', forbidden)
    run = service.create_run('示範責任法第7條房東', mode=DataMode.OFFICIAL_ONLY, depth=ResearchDepth.QUICK)
    service.continue_run(run.run_id, 'understand')
    service.continue_run(run.run_id, 'law')
    assert service.store.list_evidence(run.run_id)


def test_explicit_confirmed_current_date_is_not_mislabeled_historical():
    from alr_tw.research.service import _plan_obligations
    current = date(2099, 1, 1)
    query = '2099年1月1日發生事件'
    kinds = {item.kind for item in _plan_obligations(query, mode=DataMode.SYNTHETIC,
        depth=ResearchDepth.QUICK, as_of_date=current, include_counter_authority=False,
        current_date=current)}
    assert Kind.LEGAL_TIME_CONTEXT not in kinds
    assert not prepare_query(query, as_of_date=current)['time_hints']['requires_clarification']
