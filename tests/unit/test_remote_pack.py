import asyncio
import io
import json
from datetime import UTC, datetime, timedelta

import pytest

from alr_tw.providers.data_pack import DataPackJudgmentProvider, import_pack
from alr_tw.providers.remote_pack import (
    RemotePackProvider,
    HttpsPackTransport,
    serve_request,
    _mac,
    canonical,
    publisher_app,
)
from test_v013_rc_workflows import make_pack, JID


def providers(tmp_path, mutate=None):
    args = make_pack(tmp_path)
    root = tmp_path / "pack"
    import_pack(*args, root)

    def transport(raw):
        response = serve_request(raw, root, args[2])
        return mutate(response, args[2].read_bytes()) if mutate else response

    return (
        DataPackJudgmentProvider(*args),
        RemotePackProvider(
            "https://cache.example.test/exact", "synthetic-1", args[2], transport=transport
        ),
        root,
        args[2],
    )


@pytest.mark.parametrize("identifier", [JID, "DEMO,130,測,2,20990102,1"])
def test_common_local_remote_conformance(tmp_path, identifier):
    local, remote, _, _ = providers(tmp_path)
    now = datetime.now(UTC)
    first = asyncio.run(local.exact_lookup(identifier, now=now))
    second = asyncio.run(remote.exact_lookup(identifier, run_id="synthetic-run-a", now=now))
    assert first == second
    if second[1]:
        assert second[1].source_tier.value == "verified_cache"
    assert not second[0].coverage_complete


@pytest.mark.parametrize(
    "change", ["run", "nonce", "identifier", "snapshot", "text", "expiry", "mac"]
)
def test_authenticated_response_bindings_fail_closed(tmp_path, change):
    def mutate(raw, key):
        body = json.loads(raw)
        if change in {"run", "nonce", "identifier", "snapshot"}:
            name = {"run": "run_id", "snapshot": "snapshot_id"}.get(change, change)
            body["request"][name] = "other"
        elif change == "text":
            body["image"] = "dGFtcGVyZWQ="
        elif change == "expiry":
            body["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        body.pop("mac")
        body["mac"] = _mac(key, body) if change != "mac" else "0" * 64
        return canonical(body)

    _, remote, _, _ = providers(tmp_path, mutate)
    with pytest.raises(ValueError, match="PACK_"):
        asyncio.run(remote.exact_lookup(JID, run_id="synthetic-run-a"))


def test_replayed_response_rejected_for_new_request_and_run(tmp_path):
    local, remote, _, _ = providers(tmp_path)
    responses = []
    original = remote.transport

    def transport(raw):
        if not responses:
            responses.append(original(raw))
        return responses[0]

    remote.transport = transport
    asyncio.run(remote.exact_lookup(JID, run_id="synthetic-run-a"))
    for run in ["synthetic-run-a", "synthetic-run-b"]:
        with pytest.raises(ValueError, match="PACK_REQUEST_BINDING_MISMATCH"):
            asyncio.run(remote.exact_lookup(JID, run_id=run))


@pytest.mark.parametrize(
    "url",
    [
        "http://cache.example.test/",
        "https://user:password@cache.example.test/",
        "https://cache.example.test/?key=x",
        "https://cache.example.test:444/",
    ],
)
def test_insecure_endpoint_rejected(url):
    with pytest.raises(ValueError):
        HttpsPackTransport(url)


def test_failure_no_fallback_and_wsgi_redaction(tmp_path):
    _, remote, root, key = providers(tmp_path)

    def fail(raw):
        raise ValueError("PACK_TRANSPORT_FAILED")

    remote.transport = fail
    with pytest.raises(ValueError, match="PACK_TRANSPORT_FAILED"):
        asyncio.run(remote.exact_lookup(JID, run_id="synthetic-run"))
    statuses = []
    result = publisher_app(root, key)(
        {"REQUEST_METHOD": "POST", "CONTENT_LENGTH": "2", "wsgi.input": io.BytesIO(b"{}")},
        lambda status, headers: statuses.append(status),
    )
    assert statuses == ["400 Bad Request"]
    assert result == [b'{"error":"PACK_REQUEST_REJECTED"}']


def test_pack_shared_cache_cannot_bypass_reauthentication(tmp_path):
    from alr_tw.research.provider_executor import ProviderObligationExecutor
    from test_v080_finalization_integration import _prepared_service

    local, _, _, key = providers(tmp_path)
    service, run_id, _ = _prepared_service(tmp_path)
    executor = ProviderObligationExecutor(service.store, None)
    def fetch():
        return asyncio.run(local.exact_lookup(JID))
    # Even an entry written by an older runtime must not bypass authentication.
    result, source, evidence = fetch()
    service.store.save_source(run_id, source)
    service.store.save_cache_entry("pack-test", source, evidence)
    for _ in range(2):
        result, _, _ = executor._cached_lookup(
            run_id, "pack-test", fetch, expected_provider_id=local.provider_id
        )
        assert not result.coverage_complete
        assert not result.metadata.get("cache_hit")
    key.write_bytes(b"replacement-key-material-32-bytes!")
    with pytest.raises(ValueError, match="PACK_"):
        executor._cached_lookup(
            run_id, "pack-test", fetch, expected_provider_id=local.provider_id
        )


def test_remote_pack_through_mcp_binds_run_and_rechecks_key(tmp_path, monkeypatch):
    from alr_tw.config import Settings
    from alr_tw.workflow_cli import call_tool
    from tw_legal_rag_mcp.mcp_server.server import McpSession

    _, _, root, key = providers(tmp_path)
    seen = []

    async def transport(self, raw):
        seen.append(json.loads(raw))
        return serve_request(raw, root, key)

    monkeypatch.setattr(HttpsPackTransport, "__call__", transport)
    session = McpSession(ready=True, settings=Settings(
        data_mode="official_only", storage_path=tmp_path / "state",
        remote_pack_endpoint="https://cache.example.test/exact",
        remote_pack_snapshot="synthetic-1", data_pack_key_file=key,
    ))
    run_id = call_tool(session, "research_legal_question", {
        "query": "查詢合成裁判", "constraints": {"research_depth": "quick"},
    })["run"]["run_id"]
    for operation in ["remote-first", "remote-second"]:
        result = call_tool(session, "lookup_legal_source", {
            "run_id": run_id, "text": JID, "operation_id": operation,
        })
        assert result["source"]["source_tier"] == "verified_cache"
        assert seen[-1]["run_id"] == run_id
    assert len(seen) == 2
    assert seen[0]["nonce"] != seen[1]["nonce"]
    key.write_bytes(b"different-key-material-32-bytes!!")
    with pytest.raises(ValueError, match="WORKFLOW_DISPATCH_FAILED"):
        call_tool(session, "lookup_legal_source", {
            "run_id": run_id, "text": JID, "operation_id": "remote-revoked",
        })
