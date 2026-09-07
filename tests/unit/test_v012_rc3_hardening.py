"""RC3 的合成快照回歸：不連線、不包含真實法規內容或案件。"""
from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path
import tomllib
import zipfile
from datetime import UTC, datetime, timedelta

import pytest

from alr_tw.contracts.providers import ProviderErrorCode, ProviderResultStatus
from alr_tw.providers.official.http import HttpResponse
from alr_tw.providers.official.laws import LAW_DATA_URL, OfficialLawProvider

T0 = datetime(2099, 1, 1, tzinfo=UTC)
TTL = timedelta(minutes=10)
NAME = "示範快照法"
TEXT_A = "合成甲版資料，僅供測試。"
TEXT_B = "合成乙版資料，僅供測試。"


class Clock:
    def __init__(self) -> None:
        self.value = T0

    def __call__(self) -> datetime:
        return self.value


def archive(text: str = TEXT_A, *, include_law: bool = True) -> bytes:
    document = {
        "UpdateDate": "2099/1/1",
        "Laws": [{
            "LawName": NAME,
            "LawURL": "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=DEMO0001",
            "LawModifiedDate": "20990101",
            "LawAbandonNote": "",
            "LawArticles": [{"ArticleNo": "第 1 條", "ArticleContent": text}],
        }] if include_law else [],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as output:
        output.writestr("ChLaw.json", json.dumps(document, ensure_ascii=False))
    return buffer.getvalue()


class Transport:
    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.payload = archive()
        self.status = 200
        self.failure: Exception | None = None
        self.page_failure: Exception | None = None
        self.page_text = TEXT_A
        self.archive_calls = 0
        self.page_calls = 0
        self.archive_delay = timedelta(0)
        self.page_delay = timedelta(0)

    async def get(self, url: str, *, timeout: float, max_bytes: int) -> HttpResponse:
        assert timeout > 0
        if url == LAW_DATA_URL:
            self.archive_calls += 1
            self.clock.value += self.archive_delay
            if self.failure:
                raise self.failure
            assert len(self.payload) <= max_bytes
            return HttpResponse(self.status, self.payload, {}, url)
        self.page_calls += 1
        self.clock.value += self.page_delay
        if self.page_failure:
            raise self.page_failure
        payload = ("<html><body>" + self.page_text + "</body></html>").encode()
        return HttpResponse(200, payload, {}, url)


def setup_provider(*, verify_webpage: bool = False):
    clock = Clock()
    transport = Transport(clock)
    provider = OfficialLawProvider(
        transport, snapshot_ttl=TTL, clock=clock, verify_webpage=verify_webpage,
    )
    return clock, transport, provider


def lookup(provider, **kwargs):
    return asyncio.run(provider.exact_lookup(NAME, "1", **kwargs))


def test_memory_hit_preserves_snapshot_age_and_expiry():
    clock, transport, provider = setup_provider()
    _, first, _ = lookup(provider)
    clock.value += TTL / 2
    _, second, _ = lookup(provider)
    assert first is not None and second is not None
    assert transport.archive_calls == 1
    assert second.fetched_at == first.fetched_at == T0
    assert second.verified_at == first.verified_at == T0
    assert second.expires_at == first.expires_at == T0 + TTL
    assert second.metadata["lookup_checked_at"] == clock.value.isoformat()
    assert second.metadata["dataset_digest"] == first.metadata["dataset_digest"]


def test_exact_expiry_refreshes_content_without_mutating_old_source():
    clock, transport, provider = setup_provider()
    _, first, _ = lookup(provider)
    clock.value = T0 + TTL
    transport.payload = archive(TEXT_B)
    result, second, evidence = lookup(provider)
    assert result.status is ProviderResultStatus.FOUND
    assert first is not None and second is not None and evidence is not None
    assert first.normalized_text == TEXT_A
    assert second.normalized_text == evidence.exact_text == TEXT_B
    assert second.fetched_at == second.verified_at == clock.value
    assert second.expires_at == clock.value + TTL
    assert second.metadata["dataset_digest"] != first.metadata["dataset_digest"]
    assert transport.archive_calls == 2


@pytest.mark.parametrize("failure", ["timeout", "http", "archive", "schema"])
def test_failed_refresh_never_revives_stale_snapshot(failure):
    clock, transport, provider = setup_provider()
    _, first, _ = lookup(provider)
    clock.value = T0 + TTL
    if failure == "timeout":
        transport.failure = TimeoutError("synthetic timeout")
    elif failure == "http":
        transport.status = 503
    elif failure == "archive":
        transport.payload = b"synthetic invalid archive"
    else:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as bundle:
            bundle.writestr("ChLaw.json", "{}")
        transport.payload = output.getvalue()
    for _ in range(2):
        result, source, evidence = lookup(provider)
        assert result.status is ProviderResultStatus.ERROR
        assert result.source_ids == result.evidence_ids == []
        assert result.coverage_complete is False
        assert source is None and evidence is None
        assert provider._laws is None
    assert first is not None and first.expires_at == T0 + TTL
    assert transport.archive_calls == 3
    transport.failure = None
    transport.status = 200
    transport.payload = archive(TEXT_B)
    result, source, _ = lookup(provider)
    assert result.status is ProviderResultStatus.FOUND
    assert source is not None and source.normalized_text == TEXT_B


def test_forced_refresh_failure_revokes_even_unexpired_memory():
    clock, transport, provider = setup_provider()
    lookup(provider)
    clock.value += timedelta(seconds=1)
    transport.failure = TimeoutError("synthetic timeout")
    assert asyncio.run(provider.load(force=True)).status is ProviderResultStatus.ERROR
    result, source, evidence = lookup(provider)
    assert result.status is ProviderResultStatus.ERROR
    assert source is None and evidence is None and provider._laws is None
    assert transport.archive_calls == 3


@pytest.mark.parametrize("operation", ["search", "resolve"])
def test_catalog_read_paths_also_refresh_and_do_not_use_deleted_laws(operation):
    clock, transport, provider = setup_provider()
    lookup(provider)
    clock.value += TTL
    transport.payload = archive(include_law=False)
    if operation == "search":
        result = asyncio.run(provider.search(NAME))
        assert result.status is ProviderResultStatus.NOT_FOUND
        assert result.metadata["matches"] == []
    else:
        assert asyncio.run(provider.resolve_citations(NAME + "第1條")) == []
    assert transport.archive_calls == 2


def test_expired_search_failure_is_error_not_absence():
    clock, transport, provider = setup_provider()
    lookup(provider)
    clock.value += TTL
    transport.failure = TimeoutError("synthetic timeout")
    result = asyncio.run(provider.search(NAME))
    assert result.status is ProviderResultStatus.ERROR
    assert result.coverage_complete is False
    assert asyncio.run(provider.resolve_citations(NAME + "第1條")) == []
    assert provider._laws is None


def test_unavailable_optional_webcheck_cannot_reset_snapshot_timestamps():
    clock, transport, provider = setup_provider(verify_webpage=True)
    transport.page_failure = TimeoutError("synthetic page timeout")
    _, first, _ = lookup(provider)
    clock.value += TTL / 2
    result, second, _ = lookup(provider)
    assert result.status is ProviderResultStatus.FOUND
    assert first is not None and second is not None
    assert any("OFFICIAL_WEB_RECHECK_UNAVAILABLE" in item for item in second.warnings)
    assert second.fetched_at == second.verified_at == T0
    assert second.expires_at == first.expires_at == T0 + TTL
    assert "webpage_verified_at" not in second.metadata
    clock.value = T0 + TTL
    transport.failure = TimeoutError("synthetic dataset timeout")
    result, source, evidence = lookup(provider)
    assert result.status is ProviderResultStatus.ERROR
    assert source is None and evidence is None
    assert transport.page_calls == 2


def test_successful_page_check_records_separate_time_without_renewal():
    clock, transport, provider = setup_provider(verify_webpage=True)
    lookup(provider)
    clock.value += TTL / 2
    _, source, _ = lookup(provider)
    assert source is not None
    assert source.fetched_at == source.verified_at == T0
    assert source.expires_at == T0 + TTL
    assert source.metadata["webpage_verified_at"] == clock.value.isoformat()
    assert transport.archive_calls == 1 and transport.page_calls == 2


@pytest.mark.parametrize("stage", ["archive", "page"])
def test_expiry_during_io_returns_no_eligible_material(stage):
    clock, transport, provider = setup_provider(verify_webpage=True)
    if stage == "archive":
        transport.archive_delay = TTL
    else:
        transport.page_delay = TTL
    result, source, evidence = lookup(provider)
    assert result.status is ProviderResultStatus.ERROR
    assert result.error_code is ProviderErrorCode.SOURCE_STALE
    assert source is None and evidence is None


def test_download_and_verification_observation_times_are_distinct():
    _, transport, provider = setup_provider()
    transport.archive_delay = timedelta(seconds=2)
    _, source, _ = lookup(provider)
    assert source is not None
    assert source.fetched_at == T0
    assert source.verified_at == T0 + timedelta(seconds=2)
    assert source.expires_at == T0 + TTL


def test_explicit_now_hook_uses_same_clock_for_loading_and_lookup():
    _, transport, provider = setup_provider()
    _, first, _ = lookup(provider, now=T0)
    _, second, _ = lookup(provider, now=T0 + TTL / 2)
    _, third, _ = lookup(provider, now=T0 + TTL)
    assert first is not None and second is not None and third is not None
    assert second.expires_at == first.expires_at
    assert third.fetched_at == T0 + TTL
    assert transport.archive_calls == 2


def test_clock_rollback_does_not_reuse_future_observation():
    clock, transport, provider = setup_provider()
    lookup(provider)
    clock.value -= timedelta(seconds=1)
    transport.failure = TimeoutError("synthetic timeout")
    result, source, _ = lookup(provider)
    assert result.status is ProviderResultStatus.ERROR
    assert source is None and provider._laws is None


def test_health_probe_does_not_renew_loaded_snapshot():
    clock, transport, provider = setup_provider()
    lookup(provider)
    clock.value += TTL / 2
    asyncio.run(provider.health_check())
    clock.value = T0 + TTL
    transport.payload = archive(TEXT_B)
    _, source, _ = lookup(provider)
    assert source is not None and source.normalized_text == TEXT_B
    assert transport.archive_calls == 3


@pytest.mark.parametrize("ttl", [timedelta(0), timedelta(seconds=-1)])
def test_nonpositive_snapshot_ttl_is_rejected(ttl):
    with pytest.raises(ValueError, match="snapshot_ttl must be positive"):
        OfficialLawProvider(snapshot_ttl=ttl)


def test_naive_clock_is_rejected():
    provider = OfficialLawProvider(clock=lambda: datetime(2099, 1, 1))
    with pytest.raises(ValueError, match="timezone-aware"):
        asyncio.run(provider.load())


def test_tlr_extra_declares_required_truststore():
    root = Path(__file__).resolve().parents[2]
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert "truststore>=0.10" in metadata["project"]["optional-dependencies"]["tlr"]
