import test_v080_finalization_integration as finalization_fixtures
import asyncio
import hashlib
import hmac
import json
import sqlite3
import sys
from datetime import UTC, datetime, timedelta

import pytest

from alr_tw.cli import main
from alr_tw.config import Settings
from alr_tw.providers.data_pack import DataPackJudgmentProvider, PackManifest, import_pack
from alr_tw.research.draft_workspace import review_draft
from alr_tw.research.semantic_advisor import AdvisorConfig, CommandSemanticVerifier, advise_draft
from alr_tw.workflow_cli import call_tool
from tw_legal_rag_mcp.mcp_server.server import McpSession, tool_definitions
from test_v080_finalization_integration import _prepared_service

JID = "DEMO,130,測,1,20990101,1"
TEXT = "本合成裁判僅供測試。行為人應負合成責任。"


def make_pack(tmp_path, *, updates=None, row=None):
    path = tmp_path / "input.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE judgments(jid TEXT,title TEXT,text TEXT,section_type TEXT)")
        db.execute(
            "INSERT INTO judgments VALUES (?,?,?,?)",
            row or (JID, "合成裁判", TEXT, "court_holding"),
        )
    key = tmp_path / "external.key"
    key.write_bytes(bytes(range(32)))
    now = datetime.now(UTC)
    payload = dict(
        schema_version="alr-tw.judgment-pack/v1",
        snapshot_id="synthetic-1",
        release_id="synthetic-release",
        key_id="synthetic-test-key",
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        provenance="official_snapshot",
        coverage_start="2099-01-01",
        coverage_end="2099-01-02",
        courts=["DEMO"],
        record_count=1,
        issued_at=(now - timedelta(hours=1)).isoformat(),
        expires_at=(now + timedelta(hours=1)).isoformat(),
        mac="0" * 64,
    )
    payload.update(updates or {})
    manifest = PackManifest.model_validate(payload)
    payload["mac"] = hmac.new(
        key.read_bytes(), manifest.authenticated_bytes(), hashlib.sha256
    ).hexdigest()
    metadata = tmp_path / "input.json"
    metadata.write_text(json.dumps(payload))
    return path, metadata, key


def test_pack_search_candidate_exact_cache_and_immutable_image(tmp_path):
    args = make_pack(tmp_path)
    provider = DataPackJudgmentProvider(*args)
    candidate = asyncio.run(provider.search("合成", limit=1))
    assert candidate.candidates and not candidate.source_ids
    args[0].write_bytes(b"replacement")
    result, source, evidence = asyncio.run(provider.exact_lookup(JID))
    assert result.source_ids == [source.source_id]
    assert source.source_tier.value == "verified_cache"
    assert source.normalized_text == evidence[0].exact_text == TEXT
    assert not result.coverage_complete
    absent, missing, spans = asyncio.run(provider.exact_lookup("unknown"))
    assert absent.status.value == "not_found" and missing is None and spans == []


@pytest.mark.parametrize(
    "change,code",
    [
        ({"courts": ["OTHER"]}, "PACK_COVERAGE_MISMATCH"),
        ({"record_count": 2}, "PACK_COUNT_MISMATCH"),
        (
            {"expires_at": "2001-01-02T00:00:00Z", "issued_at": "2001-01-01T00:00:00Z"},
            "PACK_EXPIRED_OR_NOT_YET_VALID",
        ),
    ],
)
def test_signed_but_inconsistent_pack_rejected(tmp_path, change, code):
    with pytest.raises(ValueError, match=code):
        DataPackJudgmentProvider(*make_pack(tmp_path, updates=change))


@pytest.mark.parametrize("target", ["database", "manifest", "key"])
def test_pack_tamper_fails_closed(tmp_path, target):
    args = make_pack(tmp_path)
    if target == "database":
        with sqlite3.connect(args[0]) as db:
            db.execute("UPDATE judgments SET text='tampered'")
    elif target == "manifest":
        data = json.loads(args[1].read_text())
        data["snapshot_id"] = "forged"
        args[1].write_text(json.dumps(data))
    else:
        args[2].write_bytes(b"x" * 32)
    with pytest.raises(ValueError, match="PACK_(DIGEST_MISMATCH|ATTESTATION_INVALID)"):
        DataPackJudgmentProvider(*args)


def test_import_reopen_no_key_copy_and_no_overwrite(tmp_path):
    args = make_pack(tmp_path)
    destination = tmp_path / "installed"
    assert import_pack(*args, destination)["installed"] is True
    assert sorted(p.name for p in destination.iterdir()) == ["manifest.json", "pack.sqlite"]
    DataPackJudgmentProvider(destination / "pack.sqlite", destination / "manifest.json", args[2])
    with pytest.raises(ValueError, match="PACK_DESTINATION_EXISTS"):
        import_pack(*args, destination)


def test_cli_import_failure_redacts_input_path(tmp_path, capsys):
    assert (
        main(
            [
                "import-pack",
                str(tmp_path / "missing"),
                "--manifest",
                str(tmp_path / "missing"),
                "--key-file",
                str(tmp_path / "key"),
                "--destination",
                str(tmp_path / "output"),
            ]
        )
        == 2
    )
    assert str(tmp_path) not in capsys.readouterr().out


def draft(evidence):
    text = "合成責任法第1條：行為人應負合成責任。"
    return {
        "answer_text": text,
        "claim_bindings": [
            {
                "claim_id": "claim-1",
                "claim_text": text,
                "claim_type": "law_rule",
                "evidence_ids": [evidence],
            }
        ],
    }


def test_exploration_read_only_no_final_permission_or_trust_injection(tmp_path):
    service, run_id, evidence = _prepared_service(tmp_path)
    before = service.store.get_run(run_id)
    payload = draft(evidence)
    result = review_draft(service.store, run_id, **payload)
    assert result["draft_text"] == payload["answer_text"]
    assert result["annotations"][0]["references"][0]["status"] == "source_verified"
    assert result["safe_to_present"] is False
    assert result["annotations"][0]["label"] == "unverified_inference"
    assert service.store.get_run(run_id) == before
    payload["claim_bindings"][0]["verified"] = True
    with pytest.raises(ValueError, match="DRAFT_INPUT_INVALID"):
        review_draft(service.store, run_id, **payload)


def test_exploration_missing_cross_run_references_stay_unverified(tmp_path):
    service, run_id, _ = _prepared_service(tmp_path)
    result = review_draft(service.store, run_id, **draft("other-run-evidence"))
    assert result["annotations"][0]["references"][0]["status"] == "unverified"


def test_exploration_privacy_not_bypassed(tmp_path):
    service, run_id, _ = _prepared_service(tmp_path)
    result = review_draft(service.store, run_id, "公司內部機密", [])
    assert result["draft_text"] is None and result["annotations"] == []


def test_macro_uses_strict_gate_and_rejects_changed_replay(tmp_path, monkeypatch):
    monkeypatch.setattr(finalization_fixtures, "NOW", datetime.now(UTC))
    service, run_id, evidence = _prepared_service(tmp_path)
    session = McpSession(ready=True)
    session._research_service = service
    args = {"run_id": run_id, "operation_id": "completion-1", **draft(evidence)}
    result = call_tool(session, "complete_legal_research", args)
    assert result["safe_to_present"] == result["validation"]["safe_to_present"]
    replay = call_tool(session, "complete_legal_research", args)
    assert replay["replayed"] is True and replay["validation"] == result["validation"]
    with pytest.raises(ValueError, match="OPERATION_REQUEST_MISMATCH"):
        call_tool(session, "complete_legal_research", {**args, "answer_text": "變更後合成草稿"})


def test_new_tool_schemas_have_no_unresolved_nested_refs():
    definitions = {item["name"]: item for item in tool_definitions("verified")}
    for name in ("review_legal_draft", "complete_legal_research"):
        assert "$ref" not in json.dumps(definitions[name])


def test_pack_selected_in_live_session(tmp_path):
    args = make_pack(tmp_path)
    root = tmp_path / "installed"
    import_pack(*args, root)
    session = McpSession(
        ready=True,
        settings=Settings(
            data_mode="official_only",
            storage_path=tmp_path / "run",
            data_pack_root=root,
            data_pack_key_file=args[2],
        ),
    )
    assert (
        session.research_service().executor.providers.judgments.provider_id
        == "attested_judgment_pack"
    )


def test_advisor_rejects_old_model_without_execution():
    with pytest.raises(ValueError, match="ADVISOR_MODEL_NOT_APPROVED"):
        CommandSemanticVerifier(AdvisorConfig(command=[sys.executable], model="gpt-5.5"), [])


@pytest.mark.parametrize("privacy_case", ["normal", "opaque_request", "private_rationale"])
def test_advisor_gateway_protocol_and_no_approval(tmp_path, monkeypatch, privacy_case):
    from types import SimpleNamespace
    import alr_tw.research.semantic_advisor as advisor
    digits = "0" + "2" * 9
    if privacy_case != "normal":
        monkeypatch.setattr(advisor, "uuid4", lambda: SimpleNamespace(hex="a" * 7 + digits + "b" * 15))
    service, run_id, evidence = _prepared_service(tmp_path)
    script = tmp_path / "gateway.py"
    script.write_text("""import json,sys
from pathlib import Path
p=json.load(sys.stdin)
r={"request_id":p["request"]["request_id"],"run_id":p["request"]["run_id"],
"plugin_id":p["plugin_id"],"plugin_version":p["plugin_version"],"status":"completed",
"findings":[{"target_id":p["request"]["targets"][0]["target_id"],"outcome":"uncertain"}]}
Path(sys.argv[2]).write_text(json.dumps(r))
""")
    if privacy_case == "private_rationale":
        script.write_text(script.read_text().replace('"outcome":"uncertain"',
            '"outcome":"uncertain","rationale":"' + digits + '"'))
        with pytest.raises(ValueError, match="ADVISOR_PRIVACY_BLOCKED"):
            advise_draft(service.store, run_id, draft(evidence),
                AdvisorConfig(command=[sys.executable, str(script)], model="gpt-5.6-luna"))
        return
    result = advise_draft(
        service.store,
        run_id,
        draft(evidence),
        AdvisorConfig(command=[sys.executable, str(script)], model="gpt-5.6-luna"),
    )
    assert result["advisory_only"] and not result["final_answer_authorized"]
    assert result["review"]["decision"] in {"accepted", "partial"}
    assert not result["model_identity_independently_verified"]


def test_pack_lookup_through_mcp_mints_same_run_receipt_offline(tmp_path, monkeypatch):
    import socket

    def deny_network(*args, **kwargs):
        raise AssertionError("network forbidden for pack lookup")

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    args = make_pack(tmp_path)
    root = tmp_path / "installed"
    import_pack(*args, root)
    session = McpSession(
        ready=True,
        settings=Settings(
            data_mode="official_only",
            storage_path=tmp_path / "run",
            data_pack_root=root,
            data_pack_key_file=args[2],
        ),
    )
    created = call_tool(
        session,
        "research_legal_question",
        {
            "query": "查詢合成裁判",
            "constraints": {"research_depth": "quick"},
        },
    )
    run_id = created["run"]["run_id"]
    result = call_tool(
        session,
        "lookup_legal_source",
        {
            "run_id": run_id,
            "text": JID,
            "operation_id": "pack-lookup",
        },
    )
    assert result["source"]["source_tier"] == "verified_cache"
    store = session.research_service().store
    assert len(store.list_provider_snapshot_receipts(run_id)) == 1
    other = call_tool(session, "research_legal_question", {"query": "另一個合成研究"})["run"][
        "run_id"
    ]
    assert store.list_sources(other) == []
    assert store.list_provider_snapshot_receipts(other) == []


def test_pack_expires_after_provider_creation(tmp_path):
    provider = DataPackJudgmentProvider(*make_pack(tmp_path))
    with pytest.raises(ValueError, match="PACK_EXPIRED_OR_NOT_YET_VALID"):
        asyncio.run(provider.exact_lookup(JID, now=provider.manifest.expires_at))


def test_gateway_failure_is_blocked_and_does_not_invent_advice(tmp_path):
    service, run_id, evidence = _prepared_service(tmp_path)
    result = advise_draft(
        service.store,
        run_id,
        draft(evidence),
        AdvisorConfig(command=[sys.executable, "-c", "raise SystemExit(3)"], model="gpt-5.6-luna"),
    )
    assert result["review"]["decision"] == "blocked"
    assert result["review"]["findings"] == []
    assert not result["final_answer_authorized"]
