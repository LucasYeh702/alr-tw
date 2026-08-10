"""Server-owned retry semantics for transient research provider outcomes."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import cast
import zipfile

import pytest

from alr_tw.contracts.providers import (
    DataMode,
    ProviderErrorCode,
    ProviderResult,
    ProviderResultStatus,
)
from alr_tw.contracts.research import (
    ResearchDepth,
    ResearchObligationKind,
    ResearchObligationStatus,
    ResearchRun,
    ResearchSufficiency,
)
from alr_tw.research.service import ResearchService
from alr_tw.research.provider_executor import ProviderObligationExecutor, ProviderSet
from alr_tw.providers.official.http import HttpResponse
from alr_tw.providers.official.constitutional import OfficialConstitutionalProvider
from alr_tw.providers.official.judgments import OfficialJudgmentProvider
from alr_tw.providers.official.laws import OfficialLawProvider
from alr_tw.storage.sqlite_store import SqliteStore


class RetryOnceExecutor:
    """Return one transient result, then a clean provider handoff."""

    def __init__(self, transient_code: str):
        self.transient_code = transient_code
        self.calls: list[ResearchObligationKind] = []

    def execute(self, _run, obligation):
        self.calls.append(obligation.kind)
        if self.calls.count(obligation.kind) == 1:
            return {
                "status": "completed",
                "obligation": obligation.kind.value,
                "provider_calls": [
                    {
                        "provider_id": "retry-fixture",
                        "status": "error",
                        "error_code": self.transient_code,
                    }
                ],
                "warnings": [],
                "metadata": {},
                "_run_updates": {},
            }
        return {
            "status": "completed",
            "obligation": obligation.kind.value,
            "provider_calls": [
                {
                    "provider_id": "retry-fixture",
                    "status": "found",
                    "error_code": None,
                }
            ],
            "warnings": [],
            "metadata": {},
            "_run_updates": {},
        }


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
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ChLaw.json", json.dumps(document, ensure_ascii=False))
    return payload.getvalue()


class StaticLawTransport:
    async def get(self, url: str, *, timeout: float, max_bytes: int) -> HttpResponse:
        del timeout, max_bytes
        return HttpResponse(200, _law_archive(), {}, url)


class FlakyExactLawProvider(OfficialLawProvider):
    def __init__(self) -> None:
        super().__init__(StaticLawTransport(), verify_webpage=False)
        self.exact_calls = 0

    async def exact_lookup(self, law_name: str, article_no: str, **kwargs):
        self.exact_calls += 1
        if self.exact_calls == 1:
            return (
                ProviderResult(
                    status=ProviderResultStatus.ERROR,
                    provider_id=self.provider_id,
                    error_code=ProviderErrorCode.OFFICIAL_SOURCE_UNAVAILABLE,
                    message="fixture outage",
                ),
                None,
                None,
            )
        return await super().exact_lookup(law_name, article_no, **kwargs)


class DummyConstitutionalProvider:
    @staticmethod
    def normalize_identifier(_text: str) -> None:
        return None


@pytest.mark.parametrize(
    "transient_code",
    ["OFFICIAL_SOURCE_UNAVAILABLE", "OFFICIAL_PROVIDER_TIMEOUT"],
)
def test_transient_outcome_can_be_retried_once_with_new_operation(
    tmp_path: Path,
    transient_code: str,
) -> None:
    executor = RetryOnceExecutor(transient_code)
    service = ResearchService(SqliteStore(tmp_path / "cache"), executor=executor)
    run = service.create_run(
        "民法第184條",
        mode=DataMode.OFFICIAL_ONLY,
        depth=ResearchDepth.QUICK,
        include_counter_authority=False,
    )

    first = service.continue_run(run.run_id, "operation-first")
    stored_after_first = service.get_run(run.run_id)
    assert stored_after_first is not None
    query_obligation = next(
        item
        for item in stored_after_first.obligations
        if item.kind is ResearchObligationKind.QUERY_UNDERSTANDING
    )
    assert query_obligation.status is ResearchObligationStatus.PENDING
    assert query_obligation.retryable_reason_codes == [transient_code]
    assert first["outcome"]["retryable"] is True
    assert "query_understanding" in first["remaining_obligations"]
    assert stored_after_first.research_sufficiency is ResearchSufficiency.RETRY_REQUIRED
    restored = ResearchRun.model_validate_json(stored_after_first.model_dump_json())
    assert next(
        item
        for item in restored.obligations
        if item.kind is ResearchObligationKind.QUERY_UNDERSTANDING
    ).retryable_reason_codes == [transient_code]

    replay = service.continue_run(run.run_id, "operation-first")
    assert replay == first
    assert executor.calls == [ResearchObligationKind.QUERY_UNDERSTANDING]

    second = service.continue_run(run.run_id, "operation-second")
    stored_after_second = service.get_run(run.run_id)
    assert stored_after_second is not None
    query_after_retry = next(
        item
        for item in stored_after_second.obligations
        if item.kind is ResearchObligationKind.QUERY_UNDERSTANDING
    )
    assert query_after_retry.status is ResearchObligationStatus.COMPLETED
    assert query_after_retry.retryable_reason_codes == []
    assert transient_code not in stored_after_second.coverage.error_reason_codes
    assert transient_code not in stored_after_second.coverage.timeout_reason_codes
    assert stored_after_second.research_sufficiency is not ResearchSufficiency.RETRY_REQUIRED
    assert "query_understanding" not in second["remaining_obligations"]
    assert "law_research" in second["remaining_obligations"]
    assert executor.calls == [
        ResearchObligationKind.QUERY_UNDERSTANDING,
        ResearchObligationKind.QUERY_UNDERSTANDING,
    ]


def test_real_provider_retry_clears_derived_law_limitation(tmp_path: Path) -> None:
    laws = FlakyExactLawProvider()
    store = SqliteStore(tmp_path / "cache")
    service = ResearchService(
        store,
        executor=ProviderObligationExecutor(
            store,
            ProviderSet(
                laws=laws,
                constitutional=cast(
                    OfficialConstitutionalProvider,
                    DummyConstitutionalProvider(),
                ),
                judgments=cast(OfficialJudgmentProvider, object()),
            ),
        ),
    )
    run = service.create_run(
        "依示範責任法第7條判斷責任",
        mode=DataMode.OFFICIAL_ONLY,
        depth=ResearchDepth.QUICK,
        include_counter_authority=False,
    )

    service.continue_run(run.run_id, "real-query")
    first = service.continue_run(run.run_id, "real-law-first")
    stored_first = service.get_run(run.run_id)
    assert stored_first is not None
    law_obligation = next(
        item
        for item in stored_first.obligations
        if item.kind is ResearchObligationKind.LAW_RESEARCH
    )
    assert law_obligation.status is ResearchObligationStatus.PENDING
    assert first["outcome"]["retryable"] is True
    assert "LAW_OFFICIAL_VERIFICATION_INCOMPLETE" in (
        law_obligation.retryable_reason_codes
    )
    assert "LAW_OFFICIAL_VERIFICATION_INCOMPLETE" in stored_first.coverage.limitations

    second = service.continue_run(run.run_id, "real-law-second")
    stored_second = service.get_run(run.run_id)
    assert stored_second is not None
    law_after_retry = next(
        item
        for item in stored_second.obligations
        if item.kind is ResearchObligationKind.LAW_RESEARCH
    )
    assert law_after_retry.status is ResearchObligationStatus.COMPLETED
    assert law_after_retry.retryable_reason_codes == []
    assert "OFFICIAL_SOURCE_UNAVAILABLE" not in stored_second.coverage.error_reason_codes
    assert "LAW_OFFICIAL_VERIFICATION_INCOMPLETE" not in stored_second.coverage.limitations
    assert service.store.list_evidence(run.run_id)
    assert "law_research" not in second["remaining_obligations"]
    assert laws.exact_calls == 2
