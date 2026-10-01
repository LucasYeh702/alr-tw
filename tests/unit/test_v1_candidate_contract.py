"""Freeze the RC's public entry points and exercise wire-level failure semantics."""
import pytest

from tw_legal_rag_mcp.mcp_server.server import McpSession, _server_owned_tool_definitions

# Candidate contract decisions, not a new runtime registry.
INPUTS = {
    "get_legal_research_capabilities": set(),
    "research_legal_question": {"query"},
    "execute_legal_research": {"query"},
    "submit_legal_research_plan": {"run_id", "operation_id", "plan"},
    "continue_legal_research": {"run_id", "operation_id"},
    "get_legal_research_state": {"run_id"},
    "get_legal_research_finalization": {"run_id"},
    "lookup_legal_source": {"text"},
    "inspect_judgment_lineage": {"run_id", "jid", "operation_id"},
    "lookup_legislative_history": {"as_of_date", "bounded_scope"},
    "validate_legal_analysis": {"run_id", "operation_id", "analysis"},
    "review_legal_draft": {"run_id", "answer_text", "claim_bindings"},
    "validate_legal_answer": {"run_id", "answer_text", "operation_id"},
    "complete_legal_research": {"run_id", "answer_text", "claim_bindings", "operation_id"},
    "purge_research_storage": {"scope", "confirm"},
}


def test_candidate_entry_points_and_required_inputs():
    tools = _server_owned_tool_definitions()
    assert {tool["name"]: set(tool["inputSchema"].get("required", [])) for tool in tools} == INPUTS
    assert all(tool["inputSchema"]["additionalProperties"] is False for tool in tools)


@pytest.mark.parametrize("protocol", ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"])
def test_supported_protocol_initialization_discovery_and_call(protocol):
    session = McpSession()
    premature = session.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert premature["error"]["code"] == -32002
    response = session.handle_message({"jsonrpc": "2.0", "id": 2, "method": "initialize",
                                       "params": {"protocolVersion": protocol}})
    assert response["result"]["protocolVersion"] == protocol
    assert response["result"]["serverInfo"]["version"] == "1.0.0"
    session.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"})
    listed = session.handle_message({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    assert set(INPUTS) <= {tool["name"] for tool in listed["result"]["tools"]}
    result = session.handle_message({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {"name": "get_legal_research_capabilities", "arguments": {}}})
    assert not result["result"].get("isError", False)
    rejected = session.handle_message({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
        "params": {"name": "get_legal_research_capabilities", "arguments": {"trusted": True}}})
    assert "error" in rejected or rejected["result"].get("isError")


def test_unknown_protocol_does_not_enable_tools():
    session = McpSession()
    response = session.handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                       "params": {"protocolVersion": "2099-01-01"}})
    assert response["error"]["code"] == -32602
    session.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"})
    response = session.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert response["error"]["code"] == -32002


def test_missing_research_returns_stable_error_without_identifier(tmp_path):
    from alr_tw.research.service import ResearchService
    from alr_tw.storage.sqlite_store import SqliteStore

    session = McpSession(ready=True, research_service=ResearchService(SqliteStore(tmp_path)))
    response = session.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "get_legal_research_state", "arguments": {"run_id": "synthetic-missing"}}})
    assert response["error"] == {"code": -32602, "message": "RESEARCH_RUN_NOT_FOUND"}
