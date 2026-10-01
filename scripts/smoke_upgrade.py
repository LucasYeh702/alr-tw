"""Cross-process upgrade probe using actual installed old and candidate packages.

Run write under the baseline interpreter and read under the candidate interpreter.
Only synthetic data is generated; the payload is temporary and must not be committed.
The historical fixture supplies data, while all model/storage/service code comes
from the interpreter's installed wheel.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import hashlib
import secrets
import json
from pathlib import Path
import runpy
import sys


def without_descriptions(value):
    if isinstance(value, dict):
        return {key: without_descriptions(item) for key, item in value.items()
                if key not in {"description", "title"}}
    if isinstance(value, list):
        return [without_descriptions(item) for item in value]
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["write", "read"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    import alr_tw
    from alr_tw.config import Settings
    from alr_tw.contracts.providers import DataMode
    from alr_tw.providers.synthetic import SyntheticLegalContextProvider
    from alr_tw.research.service import ResearchService
    from alr_tw.storage.sqlite_store import SqliteStore
    from tw_legal_rag_mcp.mcp_server.server import McpSession, tool_definitions

    assert alr_tw.__version__ == args.version
    assert Path(alr_tw.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    record = args.root / "upgrade.json"
    env = {"ALR_TW_DATA_MODE": "official_only", "ALR_TW_RETENTION": "24h",
           "ALR_TW_MCP_TOOL_PROFILE": "verified"}
    if args.phase == "write":
        assert args.fixture is not None
        fixture = runpy.run_path(str(args.fixture))
        service, run_id, evidence_id = fixture["_prepared_service"](
            args.root, mode=DataMode.OFFICIAL_ONLY,
        )
        now = fixture["NOW"]
        answer = "行為人應負合成責任。"
        bindings = [{"claim_id": "upgrade-claim", "claim_text": answer.rstrip("。"),
                     "claim_type": "law_rule", "evidence_ids": [evidence_id]}]
        previous = service.validate_answer(run_id, answer, "old-validation", now=now,
                                           claim_bindings=bindings)
        assert previous["safe_to_present"]
        run = service.store.get_run(run_id)
        pack_digest = None
        if args.version == "0.14.0rc1":
            from alr_tw.providers.pack_builder import build_pack
            pack_now = datetime.now(UTC)
            key = args.root / "pack-secret"
            key.write_bytes(secrets.token_bytes(32))
            export = args.root / "pack-export.json"
            export.write_text(json.dumps({
                "snapshot_id": "synthetic-upgrade", "release_id": "synthetic", "key_id": "test",
                "provenance": "synthetic_fixture",
                "issued_at": (pack_now - timedelta(minutes=1)).isoformat(),
                "expires_at": (pack_now + timedelta(hours=24)).isoformat(),
                "records": [{"jid": "DEMO,113,測,1,20990101,1", "title": "合成裁判",
                             "text": "合成測試片段。", "section_type": "court_holding"}],
            }))
            pack_digest = build_pack(export, key, args.root / "pack")["sha256"]
        record.write_text(json.dumps({
            "pack_digest": pack_digest,
            "baseline_version": args.version, "run_id": run_id, "now": now.isoformat(),
            "run_expires": run.expires_at.isoformat(),
            "sources": [s.model_dump(mode="json") for s in service.store.list_sources(run_id)],
            "evidence": [e.model_dump(mode="json") for e in service.store.list_evidence(run_id)],
            "answer": answer, "bindings": bindings, "previous": previous,
            "settings": Settings.from_env(env).model_dump(mode="json"),
            "tools": {t["name"]: without_descriptions(t["inputSchema"])
                      for t in tool_definitions()},
        }, ensure_ascii=False))
        print(f"PASS baseline {args.version}: wrote synthetic validated research")
        return

    old = json.loads(record.read_text())
    if old["pack_digest"]:
        from alr_tw.providers.pack_builder import inspect_pack
        root = args.root / "pack"
        original_manifest = (root / "manifest.json").read_bytes()
        checked = inspect_pack(root, args.root / "pack-secret")
        assert checked["sha256"] == old["pack_digest"]
        assert (root / "manifest.json").read_bytes() == original_manifest
        assert hashlib.sha256((root / "pack.sqlite").read_bytes()).hexdigest() == old["pack_digest"]
        wrong_key = args.root / "wrong-secret"
        wrong_key.write_bytes(secrets.token_bytes(32))
        try:
            inspect_pack(root, wrong_key)
        except ValueError as exc:
            assert str(exc) == "PACK_ATTESTATION_INVALID"
        else:
            raise AssertionError("old pack accepted a wrong key")
    now = datetime.fromisoformat(old["now"])
    store = SqliteStore(args.root / "cache")
    service = ResearchService(store, legal_context_provider=SyntheticLegalContextProvider({"source-1"}))
    run_id = old["run_id"]
    run = store.get_run(run_id)
    assert run.budget.deadline_at is None and run.budget.used_http_requests == 0
    assert run.expires_at.isoformat() == old["run_expires"]
    assert [s.model_dump(mode="json") for s in store.list_sources(run_id)] == old["sources"]
    assert [e.model_dump(mode="json") for e in store.list_evidence(run_id)] == old["evidence"]
    # The old persisted result is not relabelled or silently rewritten on opening.
    assert store.get_operation(run_id, "old-validation") == old["previous"]
    current_settings = Settings.from_env(env).model_dump(mode="json")
    assert all(current_settings[key] == value for key, value in old["settings"].items())
    tools = {t["name"]: without_descriptions(t["inputSchema"]) for t in tool_definitions()}
    for name, schema in old["tools"].items():
        assert name in tools
        # Known old input fields remain; new optional fields may be introduced in 0.x.
        assert set(tools[name].get("required", [])) <= set(schema.get("required", []))
        for key, value in schema.get("properties", {}).items():
            assert tools[name]["properties"][key] == value, (name, key)
    try:
        replay = service.validate_answer(run_id, old["answer"], "old-validation", now=now,
                                          claim_bindings=old["bindings"])
    except ValueError as exc:
        assert old["baseline_version"] == "0.12.0"
        assert str(exc) == "OPERATION_REQUEST_MISMATCH"
    else:
        assert old["baseline_version"] in {"0.14.0rc1", "1.0.0rc1", "1.0.0rc3", "1.0.0rc4", "1.0.0rc5", "1.0.0rc6", "1.0.0rc7"}
        assert replay == old["previous"]
    fresh = service.validate_answer(run_id, old["answer"], "new-validation", now=now,
                                    claim_bindings=old["bindings"])
    assert fresh["safe_to_present"]
    from alr_tw.research.draft_workspace import review_draft
    preview = review_draft(store, run_id, old["answer"], old["bindings"], now=now)
    assert preview["safe_to_present"] is False
    assert store.get_run(run_id).expires_at.isoformat() == old["run_expires"]
    # An old caller's wire shape still reaches the tool; unknown trust input fails.
    session = McpSession(ready=True, research_service=service)
    response = session.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "get_legal_research_capabilities", "arguments": {}}})
    assert json.loads(response["result"]["content"][0]["text"])["ok"] is True
    response = session.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "get_legal_research_state", "arguments": {
            "run_id": run_id, "safe_to_present": True}}})
    assert "error" in response or response["result"].get("isError")
    # A changed answer or material set must not replay the earlier successful decision.
    for changed_answer in [old["answer"] + "無罪。"]:
        try:
            service.validate_answer(run_id, changed_answer, "new-validation", now=now,
                                    claim_bindings=old["bindings"])
        except ValueError as exc:
            assert str(exc) == "OPERATION_REQUEST_MISMATCH"
        else:
            raise AssertionError("changed answer replayed old decision")
    extra = store.list_evidence(run_id)[0].model_copy(update={"evidence_id": "upgrade-extra"})
    store.save_evidence(run_id, extra)
    try:
        service.validate_answer(run_id, old["answer"], "new-validation", now=now,
                                claim_bindings=old["bindings"])
    except ValueError as exc:
        assert str(exc) == "OPERATION_REQUEST_MISMATCH"
    else:
        raise AssertionError("changed materials replayed old decision")
    expired = datetime.fromisoformat(old["run_expires"]) + timedelta(seconds=1)
    try:
        service.validate_answer(run_id, old["answer"], "new-validation", now=expired,
                                claim_bindings=old["bindings"])
    except ValueError as exc:
        assert str(exc) == "RESEARCH_RUN_EXPIRED"
    else:
        raise AssertionError("expired old research was replayed")
    assert store.purge_run(run_id).success
    try:
        store.save_run(run)
    except (KeyError, ValueError):
        pass
    else:
        raise AssertionError("old research resurrected after purge")
    assert store.get_run(run_id) is None
    assert SqliteStore(args.root / "cache").get_run(run_id) is None
    print(f"PASS upgrade {old['baseline_version']} -> {args.version}: settings, old inputs, "
          "storage, replay, revalidation, expiry and purge; synthetic only")


if __name__ == "__main__":
    main()
