"""Verify installed workflow CLI across processes using synthetic provider transports."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
from unittest.mock import patch


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", choices=["quick", "status", "validate", "review", "complete"])
    parser.add_argument("--state")
    parser.add_argument("--run")
    parser.add_argument("--draft")
    args = parser.parse_args()
    import alr_tw
    from alr_tw.cli import main as cli
    import alr_tw.workflow_cli as workflow
    from alr_tw.evaluation.research_tasks import default_manifest, export_agent_inputs

    assert Path(alr_tw.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    assert len(export_agent_inputs(default_manifest())) == 36
    fixture = runpy.run_path(str(
        Path(__file__).resolve().parents[1] / "tests/integration/test_v012_release_gates.py"
    ))
    if args.step:
        session = fixture["_mcp_session"](Path(args.state))
        commands = {
            "quick": ["quick-research", "--query", "示範責任法第7條"],
            "status": ["research-status", "--run", args.run],
            "validate": ["validate-draft", "--run", args.run, "--input", args.draft],
            "review": ["review-draft", "--run", args.run, "--input", args.draft],
            "complete": ["complete-research", "--run", args.run, "--input", args.draft,
                         "--operation-id", "installed-complete"],
        }
        commands[args.step].extend(["--storage-path", str(Path(args.state) / "cache")])

        def injected_session(**kwargs):
            assert kwargs["settings"].storage_path == session.research_service().store.root_path
            return session

        with patch.object(workflow, "McpSession", injected_session):
            raise SystemExit(cli(commands[args.step]))
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("ALR_TW_", "TLR_")) and k not in {"PYTHONPATH", "PYTHONHOME"}}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)

        # Exercise the actual installed executable and storage arguments without session patching.
        env["ALR_TW_DATA_MODE"] = "synthetic"
        env["ALR_TW_MCP_TOOL_PROFILE"] = "verified"
        console = Path(sys.prefix) / "bin" / "alr-tw"

        def console_call(*arguments: str, expected: int = 0) -> dict:
            storage_args = [] if arguments[0] in {"build-pack", "inspect-pack"} else [
                "--storage-path", str(root / "console-state")]
            result = subprocess.run(
                [str(console), *arguments, *storage_args],
                cwd=root, env=env, capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == expected, (result.stderr, result.stdout)
            return json.loads(result.stdout)["data"]

        synthetic = console_call("quick-research", "--query", "合成測試")
        console_run = synthetic["run_id"]
        console_call("research-status", "--run", console_run)
        console_draft = root / "console-draft.json"
        console_draft.write_text(json.dumps({"answer_text": "合成測試不是法律證據。", "claim_bindings": []}))
        refused = console_call("validate-draft", "--run", console_run,
                               "--input", str(console_draft), expected=1)
        assert refused["safe_to_present"] is False and refused["answer_text"] is None

        from alr_tw.providers.data_pack import PackManifest, DataPackJudgmentProvider

        pack_file = root / "input.sqlite"
        jid = "DEMO,130,測,1,20990101,1"
        with sqlite3.connect(pack_file) as db:
            db.execute("CREATE TABLE judgments(jid TEXT,title TEXT,text TEXT,section_type TEXT)")
            db.execute("INSERT INTO judgments VALUES (?,?,?,?)",
                       (jid, "合成裁判", "合成測試片段。", "court_holding"))
        key_file = root / "external-key"
        key_file.write_bytes(os.urandom(32))
        now = datetime.now(UTC)
        manifest = PackManifest(schema_version="alr-tw.judgment-pack/v1",
            snapshot_id="installed-synthetic", release_id="synthetic", key_id="test",
            sha256=hashlib.sha256(pack_file.read_bytes()).hexdigest(),
            provenance="official_snapshot", coverage_start="2099-01-01",
            coverage_end="2099-01-01", courts=["DEMO"], record_count=1,
            issued_at=now-timedelta(minutes=1), expires_at=now+timedelta(hours=1), mac="0"*64)
        manifest = manifest.model_copy(update={"mac": hmac.new(
            key_file.read_bytes(), manifest.authenticated_bytes(), hashlib.sha256).hexdigest()})
        manifest_file = root / "manifest.json"
        manifest_file.write_text(manifest.model_dump_json())
        pack_root = root / "installed-pack"
        imported = subprocess.run([str(console), "import-pack", str(pack_file),
            "--manifest", str(manifest_file), "--key-file", str(key_file),
            "--destination", str(pack_root)], cwd=root, env=env,
            capture_output=True, text=True, timeout=30)
        assert imported.returncode == 0, imported.stderr
        provider = DataPackJudgmentProvider(pack_root / "pack.sqlite",
                                           pack_root / "manifest.json", key_file)
        import asyncio

        _, source, evidence = asyncio.run(provider.exact_lookup(jid))
        assert source.source_tier.value == "verified_cache" and evidence
        pack_env = {**env, "ALR_TW_DATA_MODE": "official_only",
                    "ALR_TW_DATA_PACK_ROOT": str(pack_root),
                    "ALR_TW_DATA_PACK_KEY_FILE": str(key_file)}
        doctor = subprocess.run([str(console), "doctor"], cwd=root, env=pack_env,
                                capture_output=True, text=True, timeout=30)
        assert doctor.returncode == 0
        assert json.loads(doctor.stdout)["data"]["data_pack"]["active"] is True

        export = root / "export.json"
        export.write_text(json.dumps({
            "snapshot_id": "synthetic-built", "release_id": "synthetic", "key_id": "test",
            "provenance": "synthetic_fixture", "issued_at": (now-timedelta(minutes=1)).isoformat(),
            "expires_at": (now+timedelta(hours=1)).isoformat(),
            "records": [{"jid": jid, "title": "合成裁判", "text": "合成測試片段。",
                         "section_type": "court_holding"}],
        }))
        built = console_call("build-pack", str(export), "--key-file", str(key_file),
                             "--destination", str(root / "built-pack"))
        checked = console_call("inspect-pack", str(root / "built-pack"), "--key-file", str(key_file))
        assert checked["sha256"] == built["sha256"] and checked["provenance"] == "synthetic_fixture"

        def call(step: str, *extra: str, expected: int = 0) -> dict:
            result = subprocess.run(
                [sys.executable, "-I", str(Path(__file__).resolve()), "--step", step,
                 "--state", str(root / "state"), *extra],
                cwd=root, env=env, capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == expected, (result.stderr, result.stdout)
            return json.loads(result.stdout)["data"]

        quick = call("quick")
        assert quick["workflow_guidance"]["drafting"]["rule_version"] == "alr-tw.drafting-rules/v2"
        run_id = quick["run_id"]
        status = call("status", "--run", run_id)
        assert status["workflow_guidance"]["answer_authorized"] is False
        assert status["workflow_guidance"]["verified_source_count"] == 1
        evidence_id = quick["evidence_bundle"]["items"][0]["evidence"][0]["evidence_id"]
        draft = root / "draft.json"
        claim = fixture["_LAW_TEXTS"]["7"].rstrip("。")
        citation = "示範責任法第7條"
        text = claim + "（" + citation + "）。"
        payload = {"answer_text": text, "claim_bindings": [{
            "claim_id": "claim-7", "claim_text": claim, "claim_type": "law_rule",
            "evidence_ids": [evidence_id], "citation_occurrences": [{
                "evidence_id": evidence_id, "citation_text": citation,
                "start_offset": text.index(citation) + 1,
                "end_offset": text.index(citation) + len(citation) + 1,
            }],
        }]}
        draft.write_text(json.dumps(payload))
        workspace = call("review", "--run", run_id, "--draft", str(draft))
        assert workspace["draft_text"] == text and workspace["safe_to_present"] is False
        assert workspace["annotations"][0]["support_label"] == "support_candidate"
        assert not workspace["citation_preparation"]["answer_authorized"]
        assert workspace["workflow_guidance"]["drafting"]["rules"]
        proposal = workspace["citation_preparation"]["proposals"][0]
        assert proposal["status"] == "proposed"
        assert workspace["citation_preparation"]["draft_sha256"] == hashlib.sha256(text.encode()).hexdigest()
        payload["claim_bindings"][0]["citation_occurrences"] = [proposal["proposed"]]
        draft.write_text(json.dumps(payload))
        completed = call("complete", "--run", run_id, "--draft", str(draft))
        assert completed["safe_to_present"] is True
        passed = call("validate", "--run", run_id, "--draft", str(draft))
        assert passed["safe_to_present"] is True
        draft.write_text(json.dumps({"answer_text": text, "claim_bindings": []}))
        blocked = call("validate", "--run", run_id, "--draft", str(draft), expected=1)
        assert blocked["safe_to_present"] is False and blocked["answer_text"] is None
    print("PASS: real console synthetic flow; injected-provider explore/complete/bound/unbound flow across processes; 36-task export")


if __name__ == "__main__":
    main()
