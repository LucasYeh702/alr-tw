"""Real spawned worker plus clearing process; pipes fix the interleaving."""
import multiprocessing
from datetime import UTC, datetime, timedelta

import pytest

from alr_tw.research.service import ResearchService
from alr_tw.contracts.providers import DataMode
from alr_tw.storage.sqlite_store import SqliteStore
from alr_tw.storage.purge import PurgeService


JID = "DEMO,130,測,1,20990101,1"


def worker(root, run_id, pipe, active, fail_after_save):
    try:
        store = SqliteStore(root)
        if active:
            service = ResearchService(store)
            save = store.save_run

            def paused_save(run):
                pipe.send("before-save")
                assert pipe.poll(15)
                pipe.recv()
                save(run)
                if fail_after_save:
                    raise ValueError("SYNTHETIC_WORK_FAILURE")

            store.save_run = paused_save
            service.inspect_judgment_lineage(run_id, JID, "active-lineage")
        else:
            stale = store.get_run(run_id)
            pipe.send("before-save")
            assert pipe.poll(15)
            pipe.recv()
            with store.operation_attempt():
                store.save_run(stale)
        pipe.send("saved")
    except Exception as exc:
        pipe.send(str(exc))
    finally:
        pipe.close()


def clear(store, kind, run_id):
    if kind == "expired":
        return store.cleanup_expired(now=datetime.now(UTC) + timedelta(days=2))
    return PurgeService(store).purge(kind, run_id=run_id if kind == "run" else None,
                                     confirmed=True)


def setup_store(tmp_path):
    store = SqliteStore(tmp_path / "state")
    run = ResearchService(store).create_run("合成清除競態研究", mode=DataMode.SYNTHETIC)
    return store, run


def assert_empty(store, kind, run_id):
    if kind == "all":
        assert not store.database_path.exists()
        return
    assert store.get_run(run_id) is None
    with store._connection() as db:
        for table in ["research_runs", "research_obligations", "operations", "run_sources",
                      "source_records", "evidence_spans", "provider_snapshot_receipts"]:
            assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


@pytest.mark.parametrize("kind", ["run", "all", "expired"])
@pytest.mark.parametrize("fail_after_save", [False, True])
def test_active_operation_makes_purge_busy_then_clear_is_final(tmp_path, kind, fail_after_save):
    store, run = setup_store(tmp_path)
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=worker, args=(store.root_path, run.run_id, child, True, fail_after_save))
    process.start()
    child.close()
    try:
        assert parent.poll(15) and parent.recv() == "before-save"
        with pytest.raises(ValueError, match="OPERATION_IN_PROGRESS"):
            clear(store, kind, run.run_id)
        parent.send("resume")
        assert parent.poll(15)
        assert parent.recv() == ("SYNTHETIC_WORK_FAILURE" if fail_after_save else "saved")
        process.join(15)
        assert process.exitcode == 0
        clear(store, kind, run.run_id)
        assert_empty(store, kind, run.run_id)
    finally:
        if process.is_alive():
            process.terminate()
        process.join(5)
        parent.close()


@pytest.mark.parametrize("kind", ["run", "all", "expired"])
def test_prelock_stale_object_cannot_resurrect_successful_purge(tmp_path, kind):
    store, run = setup_store(tmp_path)
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=worker, args=(store.root_path, run.run_id, child, False, False))
    process.start()
    child.close()
    try:
        assert parent.poll(15) and parent.recv() == "before-save"
        clear(store, kind, run.run_id)
        parent.send("resume")
        assert parent.poll(15)
        assert parent.recv() in {"RESEARCH_RUN_NOT_FOUND_OR_REPLACED", "STORAGE_PATH_CHANGED"}
        process.join(15)
        assert process.exitcode == 0
        assert_empty(store, kind, run.run_id)
    finally:
        if process.is_alive():
            process.terminate()
        process.join(5)
        parent.close()


def test_same_store_is_retired_after_full_purge_and_new_store_is_fresh(tmp_path):
    store, run = setup_store(tmp_path)
    assert store.purge_all().success
    with pytest.raises(ValueError, match="STORAGE_PURGED"):
        store.save_run(run)
    assert not store.database_path.exists()
    fresh = SqliteStore(store.root_path)
    with pytest.raises(ValueError, match="RESEARCH_RUN_NOT_FOUND_OR_REPLACED"):
        fresh.save_run(run)
    next_run = ResearchService(fresh).create_run("新的合成研究", mode=DataMode.SYNTHETIC)
    assert fresh.get_run(next_run.run_id) is not None
    assert fresh.get_run(run.run_id) is None


def test_stale_generation_cannot_update_explicit_replacement(tmp_path):
    store, run = setup_store(tmp_path)
    store.purge_run(run.run_id)
    replacement = run.model_copy(update={"created_at": run.created_at + timedelta(seconds=1),
                                         "updated_at": run.updated_at + timedelta(seconds=1)})
    store.create_run(replacement)
    with pytest.raises(ValueError, match="RESEARCH_RUN_NOT_FOUND_OR_REPLACED"):
        store.save_run(run)
    assert store.get_run(run.run_id) == replacement


def test_same_mcp_session_restarts_storage_lazily_after_successful_all_purge(tmp_path):
    from alr_tw.config import Settings
    from alr_tw.workflow_cli import call_tool
    from tw_legal_rag_mcp.mcp_server.server import McpSession

    session = McpSession(ready=True, settings=Settings(storage_path=tmp_path / "mcp-state"))
    old = call_tool(session, "research_legal_question", {"query": "第一個合成研究"})["run"]["run_id"]
    previous = session.research_service()
    old_run = previous.store.get_run(old)
    result = call_tool(session, "purge_research_storage", {"scope": "all", "confirm": True})
    assert result["success"]
    assert not previous.store.database_path.exists()
    new = call_tool(session, "research_legal_question", {"query": "第二個合成研究"})["run"]["run_id"]
    assert new != old
    assert session.research_service().store.root_path == previous.store.root_path
    assert session.research_service().store.get_run(old) is None
    with pytest.raises(ValueError, match="STORAGE_PURGED"):
        previous.store.save_run(old_run)
    assert session.research_service().store.get_run(new) is not None
