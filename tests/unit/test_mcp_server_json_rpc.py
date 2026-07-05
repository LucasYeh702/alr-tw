import json
from io import StringIO

from tw_legal_rag_mcp.mcp_server.server import McpSession, handle_message, run_stdio_server, tool_definitions
from tw_legal_rag_mcp.verification.identifier_resolver import (
    SYNTHETIC_OFFICIAL_RECORDS,
    compute_content_hash,
)
from tw_legal_rag_mcp.verification.source_policy import (
    IDENTIFIER_BACKED_VERIFIED_CACHE_ENV,
)

DEMO_RESOLVER_JID = "DEMO,113,測,1,20990101,1"
DEMO_RESOLVER_HASH = compute_content_hash(SYNTHETIC_OFFICIAL_RECORDS[DEMO_RESOLVER_JID])


def _call_tool_json(session: McpSession, request_id: int, name: str, arguments: dict) -> dict:
    response = session.handle_message(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    assert response["result"]["isError"] is False
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    return payload["data"]


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
        "version": "0.5.0",
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
    assert "get_claim_grounding_policy" in names
    assert "extract_answer_claims" in names
    assert "check_claim_support" in names
    assert "exact_law_lookup" in names
    assert "run_agentic_demo" in names
    assert "build_validation_report" in names
    assert "begin_agentic_run" in names
    assert "finalize_agentic_run" in names


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


def test_mcp_tools_call_gets_claim_grounding_policy():
    response = McpSession(ready=True).handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "get_claim_grounding_policy",
                "arguments": {},
            },
        }
    )

    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["data"]["schema"] == "alr-tw.claim-grounding-policy/v1"
    assert "supported_support_status" in payload["data"]


def test_mcp_tools_call_extracts_and_checks_claims():
    response = McpSession(ready=True).handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "extract_answer_claims",
                "arguments": {
                    "answer": "法院認為押金得依契約文字與事實情節判斷。\n程序中另有上訴抗辯。",
                },
            },
        }
    )

    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    data = payload["data"]
    assert data["count"] >= 1
    claim = data["claims"][0]
    assert claim["claim_id"] == "claim-001"

    response = McpSession(ready=True).handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "check_claim_support",
                "arguments": {
                    "answer": "法院認為押金得依契約文字與事實情節判斷。",
                    "claims": [
                        {
                            "claim_id": "claim-001",
                            "claim_text": "法院認為押金得依契約文字與事實情節判斷。",
                            "claim_type": "court_view",
                            "referenced_citation_ids": ["official-demo-law-184"],
                        }
                    ],
                    "segments": [
                        {
                            "segment_id": "official-demo-law-184-seg-01",
                            "source_id": "official-demo-law-184",
                            "citation_id": "official-demo-law-184",
                            "source_tier": "official",
                            "legal_material_type": "law",
                            "section_role": "statute_text",
                            "span_start": 0,
                            "span_end": 36,
                            "text": "synthetic law segment",
                            "official_url": "https://example.test/synthetic-official/civil-law-demo#article-184",
                            "content_hash": "sha256:synthetic-official-law-184",
                            "verified_at": "2026-01-01T00:00:00Z",
                        }
                    ],
                },
            },
        }
    )

    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["data"]["schema"] == "alr-tw.claim-support-result/v1"
    assert isinstance(payload["data"]["claim_support"], list)
    assert payload["data"]["summary"].get("claim_count", 0) >= 1


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
                "arguments": {"jid": "DEMO,113,測,1,20990101,1"},
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


def test_mcp_actual_tool_run_answers_when_official_evidence_passes():
    session = McpSession(ready=True)
    begin = _call_tool_json(
        session,
        2,
        "begin_agentic_run",
        {"query": "民法第184條 押金"},
    )
    run_id = begin["run_id"]

    _call_tool_json(session, 3, "legal_search", {"query": "民法第184條 押金"})
    _call_tool_json(
        session,
        4,
        "validate_citation",
        {
            "citation_id": "official-demo-law-184",
            "source_tier": "official",
            "official_url": "https://example.test/synthetic-official/civil-law-demo#article-184",
            "source_label": "Synthetic Civil Code Article 184",
            "legal_material_type": "law",
        },
    )
    answer = "法院認為押金可否返還需依契約約定與事實情節判斷。"
    claims = _call_tool_json(session, 5, "extract_answer_claims", {"answer": answer})["claims"]
    claims[0]["referenced_citation_ids"] = ["official-demo-law-184"]
    _call_tool_json(
        session,
        6,
        "check_claim_support",
        {
            "answer": answer,
            "claims": claims,
            "segments": [
                {
                    "segment_id": "official-demo-law-184-seg-01",
                    "source_id": "official-demo-law-184",
                    "citation_id": "official-demo-law-184",
                    "source_tier": "official",
                    "legal_material_type": "law",
                    "section_role": "statute_text",
                    "span_start": 0,
                    "span_end": 36,
                    "text": "法院認為押金可否返還需依契約約定與事實情節判斷。",
                    "official_url": (
                        "https://example.test/synthetic-official/civil-law-demo#article-184"
                    ),
                    "content_hash": "sha256:synthetic-official-law-184",
                    "verified_at": "2099-01-01T00:00:00Z",
                }
            ],
        },
    )
    trace = _call_tool_json(
        session,
        7,
        "finalize_agentic_run",
        {"run_id": run_id, "answer": answer},
    )

    assert trace["schema_version"] == "alr-tw.agentic_trace/v1"
    assert trace["trace_kind"] == "externally_driven"
    assert trace["final_action"] == "answer"
    assert trace["answer"] == answer
    assert trace["trust_gate"]["safe_to_present"] is True
    assert {call["execution_mode"] for call in trace["tool_calls"]} == {"actual_tool"}
    assert {"legal_search", "validate_citation", "extract_answer_claims", "check_claim_support"}.issubset(
        {call["tool_name"] for call in trace["tool_calls"]}
    )


def test_mcp_actual_tool_run_refuses_candidate_only_evidence_and_drops_answer():
    session = McpSession(ready=True)
    run_id = _call_tool_json(
        session,
        2,
        "begin_agentic_run",
        {"query": "民法第184條 押金"},
    )["run_id"]

    _call_tool_json(
        session,
        3,
        "validate_citation",
        {
            "citation_id": "tlr-candidate-demo-001",
            "source_tier": "external_semantic_recall",
            "source_label": "Synthetic TLR Candidate",
            "legal_material_type": "judgment",
        },
    )
    trace = _call_tool_json(
        session,
        4,
        "finalize_agentic_run",
        {"run_id": run_id, "answer": "Candidate-only answer must be dropped."},
    )

    assert trace["final_action"] == "refuse"
    assert trace["answer"] is None
    assert "NO_FINAL_CITATION" in trace["trust_gate"]["failure_reasons"]
    assert trace["evidence"][0]["citation_use"] == "allow_candidate_only"


def test_mcp_actual_tool_run_refuses_synthetic_only_evidence():
    session = McpSession(ready=True)
    run_id = _call_tool_json(
        session,
        2,
        "begin_agentic_run",
        {"query": "民法第184條 押金"},
    )["run_id"]

    _call_tool_json(
        session,
        3,
        "validate_citation",
        {
            "citation_id": "synthetic-demo-001",
            "source_tier": "synthetic",
            "source_label": "Synthetic Demo Source",
        },
    )
    trace = _call_tool_json(
        session,
        4,
        "finalize_agentic_run",
        {"run_id": run_id, "answer": "Synthetic-only answer must be dropped."},
    )

    assert trace["final_action"] == "refuse"
    assert trace["answer"] is None
    assert trace["evidence"][0]["citation_use"] == "demo_only"


def test_mcp_actual_tool_run_rejects_client_supplied_computed_fields():
    session = McpSession(ready=True)
    begin = session.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "begin_agentic_run",
                "arguments": {"query": "民法第184條", "final_action": "answer"},
            },
        }
    )
    assert begin["error"]["code"] == -32602
    assert "unexpected arguments" in begin["error"]["message"]

    run_id = _call_tool_json(
        session,
        3,
        "begin_agentic_run",
        {"query": "民法第184條 押金"},
    )["run_id"]
    finalize = session.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "finalize_agentic_run",
                "arguments": {
                    "run_id": run_id,
                    "answer": "answer",
                    "safe_to_present": True,
                },
            },
        }
    )
    assert finalize["error"]["code"] == -32602
    assert "unexpected arguments" in finalize["error"]["message"]

    validation = session.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "validate_citation",
                "arguments": {
                    "citation_id": "cache-demo",
                    "source_tier": "verified_cache",
                    "identifier_resolution": "resolved",
                },
            },
        }
    )
    assert validation["error"]["code"] == -32602
    assert "unexpected arguments" in validation["error"]["message"]


def test_mcp_actual_tool_run_unknown_run_id_returns_json_rpc_error():
    response = McpSession(ready=True).handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "finalize_agentic_run",
                "arguments": {"run_id": "missing-run", "answer": "answer"},
            },
        }
    )

    assert response["error"]["code"] == -32602
    assert "unknown run_id" in response["error"]["message"]


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


def _validate_identifier_backed_citation(
    official_hash: str,
    legal_material_type: str = "judgment",
    official_identifier: str = DEMO_RESOLVER_JID,
) -> dict:
    response = McpSession(ready=True).handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "validate_citation",
                "arguments": {
                    "citation_id": "cache-jid-demo",
                    "source_tier": "verified_cache",
                    "official_identifier": official_identifier,
                    "official_hash": official_hash,
                    "verified_at": "2026-01-01T00:00:00Z",
                    "legal_material_type": legal_material_type,
                },
            },
        }
    )
    return json.loads(response["result"]["content"][0]["text"])["data"]


def test_mcp_validate_citation_rejects_identifier_backed_cache_by_default(monkeypatch):
    monkeypatch.delenv(IDENTIFIER_BACKED_VERIFIED_CACHE_ENV, raising=False)

    data = _validate_identifier_backed_citation(DEMO_RESOLVER_HASH)

    assert data["citation_use"] == "reject"
    assert data["citation_eligibility"] == "rejected"
    assert data["error_code"] == "IDENTIFIER_BACKED_DISABLED"


def test_mcp_validate_citation_resolves_identifier_when_opted_in(monkeypatch):
    monkeypatch.setenv(IDENTIFIER_BACKED_VERIFIED_CACHE_ENV, "1")

    data = _validate_identifier_backed_citation(DEMO_RESOLVER_HASH)

    assert data["citation_use"] == "allow_final"
    assert data["citation_eligibility"] == "final_eligible"
    assert data["identifier_resolution"] == "hash_match"
    assert data["official_identifier"] == DEMO_RESOLVER_JID


def test_mcp_validate_citation_rejects_fabricated_hash_when_opted_in(monkeypatch):
    monkeypatch.setenv(IDENTIFIER_BACKED_VERIFIED_CACHE_ENV, "1")

    data = _validate_identifier_backed_citation("sha256:fabricated")

    assert data["citation_use"] == "reject"
    assert data["error_code"] == "IDENTIFIER_HASH_MISMATCH"


def test_mcp_validate_citation_rejects_unresolved_identifier_when_opted_in(monkeypatch):
    monkeypatch.setenv(IDENTIFIER_BACKED_VERIFIED_CACHE_ENV, "1")

    data = _validate_identifier_backed_citation(
        DEMO_RESOLVER_HASH, official_identifier="DEMO,113,測,999,20990101,1"
    )

    assert data["citation_use"] == "reject"
    assert data["error_code"] == "IDENTIFIER_UNRESOLVED"


def test_mcp_validate_citation_rejects_identifier_backed_law_records(monkeypatch):
    monkeypatch.setenv(IDENTIFIER_BACKED_VERIFIED_CACHE_ENV, "1")

    data = _validate_identifier_backed_citation(
        DEMO_RESOLVER_HASH, legal_material_type="law"
    )

    assert data["citation_use"] == "reject"
    assert data["error_code"] == "IDENTIFIER_MATERIAL_NOT_ELIGIBLE"


def test_mcp_validate_citation_rejects_caller_declared_resolution_status():
    response = McpSession(ready=True).handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "validate_citation",
                "arguments": {
                    "citation_id": "cache-jid-demo",
                    "source_tier": "verified_cache",
                    "official_identifier": DEMO_RESOLVER_JID,
                    "official_hash": DEMO_RESOLVER_HASH,
                    "verified_at": "2026-01-01T00:00:00Z",
                    "identifier_resolution": "hash_match",
                },
            },
        }
    )

    assert response["error"]["code"] == -32602
    assert "unexpected arguments" in response["error"]["message"]


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
