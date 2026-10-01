"""Persisted limits must survive retry, restart and alternate research entrypoints."""
import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from alr_tw.budget import charge_http_request
from alr_tw.config.settings import Settings
from alr_tw.contracts.providers import DataMode
from alr_tw.providers.official.http import HttpxAllowlistedTransport
from alr_tw.research.provider_executor import _run
from alr_tw.research.service import ResearchService
from alr_tw.storage.sqlite_store import SqliteStore


class RequestExecutor:
    def execute(self, run, obligation):
        charge_http_request()
        return {'status': 'completed', 'obligation': obligation.kind.value}

    def lookup(self, text, *, run_id):
        charge_http_request()
        return {'status': 'not_found'}


def test_count_persists_across_replay_restart_and_lookup(tmp_path):
    service = ResearchService(SqliteStore(tmp_path), RequestExecutor(), research_max_http_requests=1)
    run = service.create_run('合成研究', mode=DataMode.SYNTHETIC)
    first = service.continue_run(run.run_id, 'one')
    assert service.continue_run(run.run_id, 'one') == first
    assert service.get_run(run.run_id).budget.used_http_requests == 1
    restarted = ResearchService(SqliteStore(tmp_path), RequestExecutor())
    result = restarted.lookup_source('合成定位', run_id=run.run_id, operation_id='lookup')
    assert result['error_code'] == 'HTTP_BUDGET_EXHAUSTED'
    stopped = restarted.execute_run_to_completion(run.run_id)
    assert stopped['stop_reason'] == 'budget_exhausted'
    assert stopped['step_count'] == 1
    saved = restarted.get_run(run.run_id)
    assert saved.budget.max_http_requests == 1
    assert saved.budget.used_http_requests == 1
    assert saved.budget.used_total_tokens is None
    assert not saved.workflow_complete
    assert saved.answer_mode.value == 'refusal_only'


def test_deadline_persists_across_calls_and_restart(tmp_path):
    start = datetime.now(UTC)
    service = ResearchService(SqliteStore(tmp_path), RequestExecutor(), research_max_seconds=1)
    run = service.create_run('合成研究', mode=DataMode.SYNTHETIC, now=start)
    service.continue_run(run.run_id, 'one', now=start)
    saved = service.get_run(run.run_id).budget
    assert saved.deadline_at == start + timedelta(seconds=1)
    restarted = ResearchService(SqliteStore(tmp_path), RequestExecutor())
    result = restarted.continue_run(run.run_id, 'two', now=start + timedelta(seconds=2))
    assert result['outcome']['warnings'] == ['TIMEOUT_BUDGET_EXHAUSTED']
    assert restarted.get_run(run.run_id).budget.used_http_requests == 1


def test_slow_async_provider_is_cancelled_not_just_checked_after_return(tmp_path):
    events = []

    class Slow:
        def execute(self, run, obligation):
            async def wait():
                try:
                    events.append('started')
                    await asyncio.sleep(10)
                    events.append('unexpected completion')
                finally:
                    events.append('cancelled')
            return _run(wait())

    service = ResearchService(SqliteStore(tmp_path), Slow(), research_max_seconds=0.01)
    run = service.create_run('合成研究', mode=DataMode.SYNTHETIC)
    result = service.execute_run_to_completion(run.run_id)
    assert result['stop_reason'] == 'budget_exhausted'
    assert events == ['started', 'cancelled']
    assert service.get_run(run.run_id).budget.exhausted_reason == 'TIMEOUT_BUDGET_EXHAUSTED'


def test_real_transport_counts_redirects_before_dispatch(tmp_path, monkeypatch):
    calls = []

    def response(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={'location': '/next'})

    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(
        **{**kwargs, 'verify': True, 'transport': httpx.MockTransport(response)},
    ))
    monkeypatch.setattr('alr_tw.providers.official.http.system_truststore_context', lambda: True)

    class Redirecting:
        def execute(self, run, obligation):
            # Deliberately mimic a provider that catches transport exceptions.
            try:
                _run(HttpxAllowlistedTransport({'example.test'}).get(
                    'https://example.test/start', timeout=5, max_bytes=1000,
                ))
            except RuntimeError:
                return {'status': 'not_found'}
            raise AssertionError('redirect chain unexpectedly completed')

    service = ResearchService(SqliteStore(tmp_path), Redirecting(), research_max_http_requests=2)
    run = service.create_run('合成研究', mode=DataMode.SYNTHETIC)
    result = service.continue_run(run.run_id, 'one')
    assert len(calls) == 2
    assert result['outcome']['warnings'] == ['HTTP_BUDGET_EXHAUSTED']
    assert service.get_run(run.run_id).budget.used_http_requests == 2
    assert not service.get_run(run.run_id).workflow_complete


@pytest.mark.parametrize('value', ['0', '-1', 'nan', 'inf', '3601'])
def test_invalid_deadline_configuration_rejected(value):
    with pytest.raises(ValueError):
        Settings.from_env({'ALR_TW_RESEARCH_MAX_SECONDS': value})


def test_environment_budget_configuration():
    settings = Settings.from_env({'ALR_TW_RESEARCH_MAX_SECONDS': '30',
                                  'ALR_TW_RESEARCH_MAX_HTTP_REQUESTS': '4'})
    assert settings.research_max_seconds == 30
    assert settings.research_max_http_requests == 4
