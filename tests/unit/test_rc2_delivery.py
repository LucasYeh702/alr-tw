"""RC2 behavioral acceptance: delivery, revocation, draft repair and process death."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest

from alr_tw.cli import main
from alr_tw.contracts.providers import DataMode
from alr_tw.providers.data_pack import DataPackJudgmentProvider
from alr_tw.providers.pack_builder import build_pack, inspect_pack
from alr_tw.research.draft_workspace import review_draft
from alr_tw.research.service import ResearchService
from alr_tw.storage.sqlite_store import SqliteStore
from test_v013_rc_workflows import draft, make_pack
from test_v080_finalization_integration import _prepared_service


def export_file(tmp_path, records=None):
    now = datetime.now(UTC)
    value = {
        "snapshot_id": "synthetic-domain-1", "release_id": "synthetic-release",
        "key_id": "test-key", "provenance": "synthetic_fixture",
        "issued_at": (now-timedelta(minutes=1)).isoformat(),
        "expires_at": (now+timedelta(days=1)).isoformat(),
        "records": records or [{"jid": "DEMO,130,測,1,20990101,1", "title": "合成責任",
                                "text": "合成規則：限於合成案例。", "section_type": "court_holding"}],
    }
    path = tmp_path / "export.json"
    path.write_text(json.dumps(value))
    key = tmp_path / "key"
    key.write_bytes(os.urandom(32))
    return path, key


def test_delivery_reproducible_inspect_import_and_cli(tmp_path, capsys):
    source, key = export_file(tmp_path)
    first = build_pack(source, key, tmp_path / "one")
    second = build_pack(source, key, tmp_path / "two")
    assert first["sha256"] == second["sha256"]
    assert first["quality"]["legal_accuracy_verified"] is False
    assert inspect_pack(tmp_path / "one", key)["record_count"] == 1
    provider = DataPackJudgmentProvider(tmp_path / "one/pack.sqlite", tmp_path / "one/manifest.json", key)
    _, record, _ = asyncio.run(provider.exact_lookup("DEMO,130,測,1,20990101,1"))
    assert record.source_tier.value == "synthetic"
    assert main(["inspect-pack", str(tmp_path / "one"), "--key-file", str(key)]) == 0
    assert str(tmp_path) not in capsys.readouterr().out
    assert main(["build-pack", str(source), "--key-file", str(key), "--destination", str(tmp_path / "three")]) == 0
    assert sorted(p.name for p in (tmp_path / "three").iterdir()) == ["manifest.json", "pack.sqlite"]


def test_duplicate_export_fails_before_destination_created(tmp_path):
    source, key = export_file(tmp_path)
    value = json.loads(source.read_text())
    value["records"] *= 2
    source.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="PACK_IDENTITY_INVALID"):
        build_pack(source, key, tmp_path / "out")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("action", ["delete", "rotate"])
def test_open_pack_revoked_without_restart(tmp_path, action):
    args = make_pack(tmp_path)
    provider = DataPackJudgmentProvider(*args)
    if action == "delete":
        args[2].unlink()
    else:
        args[2].write_bytes(os.urandom(32))
    with pytest.raises(ValueError, match="PACK_TRUST_REVOKED"):
        asyncio.run(provider.search("合成"))
    with pytest.raises(ValueError, match="PACK_TRUST_REVOKED"):
        asyncio.run(provider.exact_lookup("DEMO,130,測,1,20990101,1"))
    assert asyncio.run(provider.health_check()).error_code == "PACK_TRUST_REVOKED"


def test_draft_support_and_repair_without_authorizing_or_mutating(tmp_path):
    service, run_id, evidence = _prepared_service(tmp_path)
    original = service.store.get_run(run_id)
    good = review_draft(service.store, run_id, **draft(evidence))
    annotation = good["annotations"][0]
    assert annotation["support_status"] == "supported"
    assert annotation["support_label"] == "support_candidate"
    assert annotation["text_ranges"][0]["start"] == 0
    bad = draft("foreign-evidence")
    result = review_draft(service.store, run_id, **bad)
    assert result["annotations"][0]["support_status"] != "supported"
    assert result["revision_steps"]
    assert not result["safe_to_present"] and not good["final_answer_authorized"]
    assert service.store.get_run(run_id) == original


def test_process_kill_recovery_preserves_receipt_and_blocks_live_worker(tmp_path):
    root = tmp_path / "state"
    service = ResearchService(SqliteStore(root))
    run = service.create_run("合成研究", mode=DataMode.SYNTHETIC)
    completed = service.continue_run(run.run_id, "completed")
    script = '''
import sys, time
from alr_tw.storage.sqlite_store import SqliteStore
store = SqliteStore(sys.argv[1])
with store.operation_attempt():
    store.record_operation(sys.argv[2], "killed", {"status": "in_progress"}, request={"tool": "continue_run"})
    print("ready", flush=True)
    time.sleep(60)
'''
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(root), run.run_id],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src")},
    )
    try:
        assert process.stdout.readline().strip() == "ready"
        with pytest.raises(ValueError, match="OPERATION_IN_PROGRESS"):
            service.continue_run(run.run_id, "blocked-live")
        with pytest.raises(ValueError, match="OPERATION_IN_PROGRESS"):
            service.store.get_operation(run.run_id, "killed")
        process.kill()
        process.wait(timeout=10)
        with pytest.raises(ValueError, match="OPERATION_FAILED"):
            service.continue_run(run.run_id, "killed")
        interrupted = service.store.get_operation(run.run_id, "killed")
        assert interrupted["error_code"] == "OPERATION_INTERRUPTED"
        assert service.continue_run(run.run_id, "recovered")["run_id"] == run.run_id
        assert service.store.get_operation(run.run_id, "completed") == completed
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)


def test_synthetic_pack_cannot_activate_as_live_data(tmp_path):
    from alr_tw.config import Settings
    from alr_tw.providers.data_pack import configured_pack_provider

    source, key = export_file(tmp_path)
    build_pack(source, key, tmp_path / "out")
    settings = Settings(data_pack_root=tmp_path / "out", data_pack_key_file=key)
    with pytest.raises(ValueError, match="PACK_SYNTHETIC_NOT_LIVE"):
        configured_pack_provider(settings)


def test_repeated_draft_ranges_are_bounded():
    from alr_tw.research.draft_workspace import _text_ranges

    ranges, truncated = _text_ranges("甲" * 100000, "甲")
    assert len(ranges) == 32 and truncated
    assert _text_ranges("甲乙甲", "甲") == ([{"start": 0, "end": 1}, {"start": 2, "end": 3}], False)
