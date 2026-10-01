from datetime import UTC, datetime, timedelta

import pytest

from alr_tw.contracts.providers import DataMode
from alr_tw.research.service import ResearchService
from alr_tw.storage.sqlite_store import SqliteStore


def test_operation_id_cannot_be_reused_for_another_tool(tmp_path):
    service = ResearchService(SqliteStore(tmp_path / "state"))
    run = service.create_run("合成研究", mode=DataMode.SYNTHETIC)
    service.continue_run(run.run_id, "same")
    with pytest.raises(ValueError, match="OPERATION_REQUEST_MISMATCH"):
        service.validate_answer(run.run_id, "合成草稿", "same")


def test_changed_draft_cannot_replay_previous_result(tmp_path):
    service = ResearchService(SqliteStore(tmp_path / "state"))
    run = service.create_run("合成研究", mode=DataMode.SYNTHETIC)
    service.validate_answer(run.run_id, "第一份合成草稿", "same")
    with pytest.raises(ValueError, match="OPERATION_REQUEST_MISMATCH"):
        service.validate_answer(run.run_id, "第二份合成草稿", "same")


def test_completed_operation_cannot_be_overwritten(tmp_path):
    service = ResearchService(SqliteStore(tmp_path / "state"))
    run = service.create_run("合成研究", mode=DataMode.SYNTHETIC, now=datetime.now(UTC))
    result = service.continue_run(run.run_id, "same")
    with pytest.raises(ValueError, match="OPERATION_ALREADY_COMPLETED"):
        service.store.complete_operation(run.run_id, "same", {"stale": True})
    assert service.store.get_operation(run.run_id, "same") == result


def test_same_request_replays_after_store_reopen(tmp_path):
    root = tmp_path / "state"
    service = ResearchService(SqliteStore(root))
    run = service.create_run("合成研究", mode=DataMode.SYNTHETIC)
    result = service.continue_run(run.run_id, "same")
    reopened = ResearchService(SqliteStore(root))
    assert reopened.continue_run(run.run_id, "same") == result


def test_incomplete_run_blocks_replay_and_overlapping_work_but_can_be_purged(tmp_path):
    root = tmp_path / "state"
    service = ResearchService(SqliteStore(root))
    run = service.create_run("合成研究", mode=DataMode.SYNTHETIC)
    service.store.record_operation(
        run.run_id, "interrupted", {"status": "in_progress"},
        request={"tool": "continue_run"},
    )
    reopened = ResearchService(SqliteStore(root))
    for operation_id in ("interrupted", "another"):
        with pytest.raises(ValueError, match="OPERATION_IN_PROGRESS"):
            reopened.continue_run(run.run_id, operation_id)
    assert reopened.store.get_operation(run.run_id, "interrupted") == {"status": "in_progress"}
    assert reopened.store.purge_run(run.run_id).success
    fresh = reopened.create_run("合成研究", mode=DataMode.SYNTHETIC)
    assert reopened.continue_run(fresh.run_id, "fresh")["run_id"] == fresh.run_id


def test_legacy_unbound_receipt_is_not_treated_as_matching(tmp_path):
    service = ResearchService(SqliteStore(tmp_path / "state"))
    run = service.create_run("合成研究", mode=DataMode.SYNTHETIC)
    service.store.record_operation(run.run_id, "old", {"safe_to_present": True})
    with pytest.raises(ValueError, match="OPERATION_REQUEST_MISMATCH"):
        service.validate_answer(run.run_id, "合成草稿", "old")


def test_catchable_executor_failure_closes_claim_and_allows_new_operation(tmp_path, monkeypatch):
    service = ResearchService(SqliteStore(tmp_path / "state"))
    run = service.create_run("合成研究", mode=DataMode.SYNTHETIC)
    original = service.executor.execute

    def fail(*args):
        raise RuntimeError("synthetic transport interruption")

    monkeypatch.setattr(service.executor, "execute", fail)
    with pytest.raises(RuntimeError):
        service.continue_run(run.run_id, "failed")
    with pytest.raises(ValueError, match="OPERATION_FAILED"):
        service.continue_run(run.run_id, "failed")
    monkeypatch.setattr(service.executor, "execute", original)
    assert service.continue_run(run.run_id, "retry")["run_id"] == run.run_id


def test_auto_id_lookup_failure_does_not_lock_run(tmp_path, monkeypatch):
    service = ResearchService(SqliteStore(tmp_path / "state"))
    run = service.create_run("合成研究", mode=DataMode.SYNTHETIC)

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic lookup failure")

    monkeypatch.setattr(service.executor, "lookup", fail, raising=False)
    with pytest.raises(RuntimeError):
        service.lookup_source("合成查詢", run_id=run.run_id)
    assert service.continue_run(run.run_id, "next")["run_id"] == run.run_id


def test_expired_lookup_does_not_call_provider(tmp_path, monkeypatch):
    service = ResearchService(SqliteStore(tmp_path / "state"))
    run = service.create_run(
        "合成研究", mode=DataMode.SYNTHETIC, now=datetime.now(UTC) - timedelta(days=3),
    )
    calls = []
    monkeypatch.setattr(service.executor, "lookup", lambda *a, **k: calls.append(1), raising=False)
    with pytest.raises(ValueError, match="RESEARCH_RUN_EXPIRED"):
        service.lookup_source("合成查詢", run_id=run.run_id)
    assert calls == []


def test_later_scope_failure_does_not_change_completed_claim(tmp_path):
    service = ResearchService(SqliteStore(tmp_path / "state"))
    run = service.create_run("合成研究", mode=DataMode.SYNTHETIC)
    store = service.store
    with pytest.raises(RuntimeError):
        with store.operation_attempt():
            store.record_operation(run.run_id, "done", {"status": "in_progress"})
            store.complete_operation(run.run_id, "done", {"status": "completed"})
            with store.operation_attempt():
                store.record_operation(run.run_id, "failed", {"status": "in_progress"})
                raise RuntimeError("synthetic later failure")
    assert store.get_operation(run.run_id, "done") == {"status": "completed"}
    assert store.get_operation(run.run_id, "failed")["status"] == "failed"


def test_base_exception_resets_context_without_inventing_completion(tmp_path):
    from alr_tw.storage.sqlite_store import _ACTIVE_CLAIMS

    service = ResearchService(SqliteStore(tmp_path / "state"))
    run = service.create_run("合成研究", mode=DataMode.SYNTHETIC)
    with pytest.raises(KeyboardInterrupt):
        with service.store.operation_attempt():
            service.store.record_operation(run.run_id, "killed", {"status": "in_progress"})
            raise KeyboardInterrupt
    assert _ACTIVE_CLAIMS.get() is None
    assert service.store.get_operation(run.run_id, "killed") == {"status": "in_progress"}
