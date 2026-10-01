from datetime import UTC, datetime, timedelta

import pytest

from alr_tw.workflow_cli import call_tool
from tw_legal_rag_mcp.mcp_server.server import McpSession
from test_v101_judgment_lineage import _service, _seed_lineage_root, ROOT_JID, UPPER_JID


def setup(tmp_path, mcp):
    service, store, _, _ = _service(tmp_path)
    run_id = _seed_lineage_root(service, store)
    session = McpSession(ready=True, research_service=service)

    def invoke(jid=ROOT_JID, budget=8, operation="lineage"):
        if mcp:
            return call_tool(session, "inspect_judgment_lineage", {
                "run_id": run_id, "jid": jid, "operation_id": operation,
                "max_related_nodes": budget,
            })
        return service.inspect_judgment_lineage(run_id, jid, operation, max_related_nodes=budget)

    return service, store, run_id, invoke, session


@pytest.mark.parametrize("mcp", [False, True])
def test_lineage_replay_requires_tool_and_normalized_parameters(tmp_path, mcp):
    service, store, run_id, invoke, session = setup(tmp_path, mcp)
    first = invoke()
    assert invoke(" " + ROOT_JID + " ") == first
    for jid, budget in [(UPPER_JID, 8), (ROOT_JID, 4)]:
        with pytest.raises(ValueError, match="OPERATION_REQUEST_MISMATCH"):
            invoke(jid, budget)
    with pytest.raises(ValueError, match="OPERATION_REQUEST_MISMATCH"):
        call_tool(session, "lookup_legal_source", {
            "run_id": run_id, "text": ROOT_JID, "operation_id": "lineage",
        })
    store.purge_run(run_id)
    with pytest.raises((KeyError, ValueError)):
        invoke()


@pytest.mark.parametrize("mcp", [False, True])
@pytest.mark.parametrize("state,legacy,code", [
    ("completed", True, "OPERATION_REQUEST_MISMATCH"),
    ("in_progress", False, "OPERATION_IN_PROGRESS"),
    ("failed", False, "OPERATION_FAILED"),
])
def test_lineage_legacy_or_unfinished_operation_never_looks_complete(tmp_path, mcp, state, legacy, code):
    _, store, run_id, invoke, _ = setup(tmp_path, mcp)
    store.record_operation(run_id, "lineage", {"status": state}, request=None if legacy else {
        "tool": "inspect_judgment_lineage", "jid": ROOT_JID, "max_related_nodes": 8,
    })
    with pytest.raises(ValueError, match=code):
        invoke()


def test_lineage_replay_rejects_expired_sources_and_changed_material(tmp_path):
    service, store, run_id, invoke, _ = setup(tmp_path, False)
    invoke()
    # Keep run fresh beyond source TTL to exercise the source replay gate itself.
    run = store.get_run(run_id)
    store.save_run(run.model_copy(update={"expires_at": run.expires_at + timedelta(days=1)}))
    with pytest.raises(ValueError, match="OPERATION_RESULT_STALE"):
        service.inspect_judgment_lineage(run_id, ROOT_JID, "lineage",
                                         now=datetime.now(UTC) + timedelta(hours=25))
    store.replace_provider_snapshot_receipts(run_id, [])
    with pytest.raises(ValueError, match="OPERATION_RESULT_STALE"):
        invoke()


def test_lineage_replay_checks_receipt_expiry_even_with_fresh_sources(tmp_path, monkeypatch):
    service, store, run_id, invoke, _ = setup(tmp_path, False)
    sync = service._sync_snapshot_receipts
    now = datetime.now(UTC)

    def short_receipts(run, **kwargs):
        sync(run, **kwargs)
        receipts = store.list_provider_snapshot_receipts(run_id)
        assert receipts
        store.replace_provider_snapshot_receipts(run_id, [
            receipt.model_copy(update={"expires_at": now + timedelta(seconds=1)})
            for receipt in receipts
        ])

    monkeypatch.setattr(service, "_sync_snapshot_receipts", short_receipts)
    invoke()
    assert all(source.expires_at > now + timedelta(seconds=2)
               for source in store.list_sources(run_id))
    with pytest.raises(ValueError, match="OPERATION_RESULT_STALE"):
        service.inspect_judgment_lineage(run_id, ROOT_JID, "lineage", now=now + timedelta(seconds=2))
