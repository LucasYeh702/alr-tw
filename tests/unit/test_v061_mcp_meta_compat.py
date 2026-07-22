import json
from pathlib import Path

import pytest

from alr_tw.research.service import ResearchService
from alr_tw.storage.sqlite_store import SqliteStore
from tw_legal_rag_mcp.mcp_server.request_normalization import (
    normalize_call_tool_params,
)
from tw_legal_rag_mcp.mcp_server.server import McpSession, tool_definitions


def _call(
    session: McpSession,
    name: str,
    arguments: dict,
    *,
    request_meta: dict | None = None,
) -> dict:
    params = {"name": name, "arguments": arguments}
    if request_meta is not None:
        params["_meta"] = request_meta
    response = session.handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params}
    )
    assert response is not None
    assert "error" not in response
    assert response["result"]["isError"] is False
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    return payload["data"]


@pytest.mark.parametrize(
    ("request_meta", "argument_meta"),
    [
        (None, None),
        ({"progressToken": "request-secret"}, None),
        (None, {"codex": "argument-secret"}),
        ({"progressToken": "request-secret"}, {"codex": "argument-secret"}),
    ],
)
def test_zero_argument_tool_accepts_only_reserved_meta_locations(
    request_meta: dict | None,
    argument_meta: dict | None,
) -> None:
    arguments = {} if argument_meta is None else {"_meta": argument_meta}
    payload = _call(
        McpSession(ready=True),
        "get_trust_model",
        arguments,
        request_meta=request_meta,
    )
    assert payload["schema_version"] == "alr-tw.trust_model/v1"


def test_all_v060_tools_accept_codex_argument_meta(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("ALR_TW_DATA_MODE", raising=False)
    store = SqliteStore(tmp_path / "cache")
    session = McpSession(ready=True, research_service=ResearchService(store))
    meta = {"codex": {"trace": "must-not-persist"}}

    created = _call(
        session,
        "research_legal_question",
        {"query": "民法第184條", "_meta": meta},
    )
    run_id = created["run"]["run_id"]
    for index in range(8):
        state = _call(
            session,
            "get_legal_research_state",
            {"run_id": run_id, "_meta": meta},
        )
        if state["ready_for_draft"]:
            break
        _call(
            session,
            "continue_legal_research",
            {
                "run_id": run_id,
                "operation_id": f"continue-{index}",
                "_meta": meta,
            },
        )
    assert state["ready_for_draft"] is True
    _call(session, "lookup_legal_source", {"text": "民法第184條", "_meta": meta})
    _call(
        session,
        "validate_legal_answer",
        {
            "run_id": run_id,
            "answer_text": "目前沒有可驗證證據。",
            "operation_id": "validate-1",
            "_meta": meta,
        },
    )
    _call(
        session,
        "purge_research_storage",
        {"scope": "run", "run_id": run_id, "confirm": True, "_meta": meta},
    )

    for file_path in (tmp_path / "cache").glob("**/*"):
        if file_path.is_file():
            assert b"must-not-persist" not in file_path.read_bytes()


def test_unknown_business_argument_still_fails() -> None:
    response = McpSession(ready=True).handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "get_trust_model",
                "arguments": {"unknown_field": True, "_meta": {}},
            },
        }
    )
    assert response is not None
    assert response["error"]["code"] == -32602
    assert "INVALID_TOOL_ARGUMENTS" in response["error"]["message"]
    assert "unknown_field" in response["error"]["message"]


@pytest.mark.parametrize("value", ["bad", 1, [], True])
def test_meta_must_be_an_object(value: object) -> None:
    with pytest.raises(ValueError, match="_meta must be an object"):
        normalize_call_tool_params(
            {"name": "get_trust_model", "arguments": {}, "_meta": value}
        )


def test_nested_business_meta_is_not_recursively_removed() -> None:
    normalized = normalize_call_tool_params(
        {
            "name": "research_legal_question",
            "arguments": {
                "query": "民法第184條",
                "constraints": {"_meta": {"not": "transport"}},
                "_meta": {"codex": True},
            },
        }
    )
    assert normalized.arguments["constraints"]["_meta"] == {"not": "transport"}


def test_validate_answer_schema_exposes_structured_claim_bindings() -> None:
    schema = next(
        tool["inputSchema"]
        for tool in tool_definitions()
        if tool["name"] == "validate_legal_answer"
    )
    bindings = schema["properties"]["claim_bindings"]

    assert bindings["type"] == "array"
    assert bindings["items"]["additionalProperties"] is False
    assert "evidence_ids" in bindings["items"]["required"]
