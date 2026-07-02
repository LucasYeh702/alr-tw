import json
from io import StringIO

from tw_legal_rag_mcp.mcp_server.server import McpSession, handle_message, run_stdio_server, tool_definitions


def test_mcp_initialize_returns_server_metadata():
    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        }
    )

    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert response["result"]["protocolVersion"] == "2024-11-05"
    assert response["result"]["serverInfo"] == {
        "name": "alr-tw",
        "version": "0.2.1",
    }
    assert response["result"]["capabilities"] == {"tools": {}}


def test_mcp_initialize_rejects_unsupported_protocol_version():
    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2099-01-01"},
        }
    )

    assert response["error"]["code"] == -32602
    assert "Unsupported protocol version" in response["error"]["message"]


def test_mcp_tool_list_exposes_agentic_legal_research():
    names = {tool["name"] for tool in tool_definitions()}

    assert "agentic_legal_research" in names
    assert "legal_search" in names
    assert "validate_citation" in names
    assert "exact_law_lookup" in names
    assert "run_agentic_demo" in names
    assert "build_validation_report" in names


def test_mcp_tools_call_runs_agentic_legal_research():
    session = McpSession()
    session.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        }
    )
    session.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"})
    response = session.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "agentic_legal_research",
                "arguments": {"query": "民法第184條 押金"},
            },
        }
    )

    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 2
    assert response["result"]["isError"] is False
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["schema_version"] == "alr-tw.mcp_tool_result/v1"
    assert payload["data"]["schema_version"] == "alr-tw.agentic_trace/v1"
    assert payload["data"]["final_action"] == "answer"


def test_mcp_tools_call_runs_agentic_demo_trace():
    response = McpSession(ready=True).handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "run_agentic_demo",
                "arguments": {"query": "民法第184條 押金", "scenario": "fail_candidate_only"},
            },
        }
    )

    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["data"]["schema_version"] == "alr-tw.agentic_trace/v1"
    assert payload["data"]["final_action"] == "refuse"


def test_mcp_tools_call_builds_validation_report():
    response = McpSession(ready=True).handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "build_validation_report",
                "arguments": {"query": "民法第184條 押金", "scenario": "pass_official_source"},
            },
        }
    )

    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["data"]["report"].startswith("# Legal Research Validation Report")


def test_mcp_tools_call_returns_trust_model_contract():
    response = McpSession(ready=True).handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "get_trust_model", "arguments": {}},
        }
    )

    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["data"]["schema_version"] == "alr-tw.trust_model/v1"
    assert payload["data"]["final_citation_tiers"] == ["official", "verified_cache"]
    assert "external_semantic_recall" in payload["data"]["candidate_only_tiers"]
    assert "synthetic" in payload["data"]["demo_only_tiers"]


def test_mcp_tools_call_exact_lookup_tools_are_demo_only():
    law_response = McpSession(ready=True).handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "exact_law_lookup",
                "arguments": {"title": "示範租賃規則", "article_no": "第1條"},
            },
        }
    )
    judgment_response = McpSession(ready=True).handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "exact_judgment_lookup",
                "arguments": {"jid": "DEMO,001,民,1,20260101,1"},
            },
        }
    )
    constitutional_response = McpSession(ready=True).handle_message(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "exact_constitutional_lookup",
                "arguments": {"source_id": "demo-constitutional-001"},
            },
        }
    )

    for response in [law_response, judgment_response, constitutional_response]:
        payload = json.loads(response["result"]["content"][0]["text"])
        assert payload["ok"] is True
        assert payload["data"]["source_tier"] == "synthetic"


def test_mcp_tools_call_rejects_non_string_arguments():
    session = McpSession(ready=True)
    response = session.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "agentic_legal_research",
                "arguments": {"query": 123},
            },
        }
    )

    assert response["error"]["code"] == -32602
    assert "query must be a string" in response["error"]["message"]


def test_mcp_tools_call_rejects_extra_arguments():
    session = McpSession(ready=True)
    response = session.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "agentic_legal_research",
                "arguments": {"query": "民法第184條", "extra": "ignored"},
            },
        }
    )

    assert response["error"]["code"] == -32602
    assert "unexpected arguments" in response["error"]["message"]


def test_mcp_tools_call_rejects_invalid_enum_argument():
    session = McpSession(ready=True)
    response = session.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "validate_citation",
                "arguments": {"citation_id": "demo", "source_tier": "not-a-tier"},
            },
        }
    )

    assert response["error"]["code"] == -32602
    assert "source_tier must be one of" in response["error"]["message"]


def test_mcp_validate_citation_uses_eligibility_without_claim_support_overclaim():
    response = McpSession(ready=True).handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "validate_citation",
                "arguments": {"citation_id": "official-demo", "source_tier": "official"},
            },
        }
    )

    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["data"]["citation_eligibility"] == "final_eligible"
    assert payload["data"]["support"] == "not_checked"


def test_mcp_validate_citation_allows_complete_verified_cache_metadata():
    response = McpSession(ready=True).handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "validate_citation",
                "arguments": {
                    "citation_id": "cache-demo",
                    "source_tier": "verified_cache",
                    "official_url": "https://example.test/law/184",
                    "official_hash": "sha256:demo",
                    "verified_at": "2026-01-01T00:00:00Z",
                },
            },
        }
    )

    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["data"]["citation_use"] == "allow_final"
    assert payload["data"]["citation_eligibility"] == "final_eligible"


def test_mcp_validate_citation_rejects_incomplete_verified_cache_metadata():
    response = McpSession(ready=True).handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "validate_citation",
                "arguments": {
                    "citation_id": "cache-demo",
                    "source_tier": "verified_cache",
                    "official_url": "https://example.test/law/184",
                },
            },
        }
    )

    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["data"]["citation_use"] == "reject"
    assert payload["data"]["citation_eligibility"] == "rejected"


def test_mcp_tools_call_requires_initialized_session():
    response = McpSession().handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        }
    )

    assert response["error"]["code"] == -32002
    assert response["error"]["message"] == "Server not initialized"


def test_mcp_stdio_lifecycle_lists_tools_after_initialized_notification():
    input_stream = StringIO(
        "\n".join(
            [
                '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05"}}',
                '{"jsonrpc":"2.0","method":"notifications/initialized"}',
                '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}',
            ]
        )
        + "\n"
    )
    output_stream = StringIO()

    run_stdio_server(input_stream, output_stream)

    responses = [json.loads(line) for line in output_stream.getvalue().splitlines()]
    assert responses[0]["result"]["protocolVersion"] == "2024-11-05"
    assert {tool["name"] for tool in responses[1]["result"]["tools"]} >= {
        "agentic_legal_research",
        "legal_search",
    }


def test_mcp_notification_without_id_is_ignored():
    response = handle_message({"jsonrpc": "2.0", "method": "ping", "params": {}})

    assert response is None
