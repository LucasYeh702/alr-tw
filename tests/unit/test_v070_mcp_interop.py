from __future__ import annotations

import json
from pathlib import Path

from alr_tw.research.service import ResearchService
from alr_tw.storage.sqlite_store import SqliteStore
from tw_legal_rag_mcp.mcp_server.server import McpSession, tool_definitions


def _call(session: McpSession, request_id: int, name: str, arguments: dict) -> dict:
    response = session.handle_message(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    return payload["data"]


def _plan_payload() -> dict:
    return {
        "plan_id": "plan-mcp",
        "issues": [
            {
                "issue_id": "issue-rule",
                "label": "適用規範",
                "proposition": "本案應適用何項法律？",
                "category": "claim_basis",
            }
        ],
        "authority_locators": [
            {
                "locator_id": "law-184",
                "material_type": "law",
                "citation": "民法第184條",
                "issue_ids": ["issue-rule"],
            }
        ],
    }


def test_mcp_exposes_agent_neutral_capabilities_and_plan_registration(tmp_path: Path):
    session = McpSession(
        ready=True,
        research_service=ResearchService(SqliteStore(tmp_path / "cache")),
    )
    names = {item["name"] for item in tool_definitions()}

    assert "get_legal_research_capabilities" in names
    assert "submit_legal_research_plan" in names
    assert "validate_legal_analysis" in names

    capabilities = _call(
        session,
        1,
        "get_legal_research_capabilities",
        {},
    )
    assert capabilities["interface_family"] == "agent_neutral_legal_research"
    assert capabilities["accepts_client_evidence"] is False
    assert capabilities["accepts_client_fact_states"] is False
    assert "accepted_civil_analysis_schema" not in capabilities
    assert "civil_analysis_validation_tool" not in capabilities
    assert capabilities["accepted_legal_analysis_schema"] == "alr-tw.legal-analysis/v1"
    assert capabilities["legal_analysis_validation_tool"] == "validate_legal_analysis"
    assert set(capabilities["supported_legal_analysis_profiles"]) == {
        "civil_substantive",
        "civil_procedure",
        "criminal_substantive",
        "criminal_procedure",
        "administrative",
        "constitutional_review",
    }
    assert capabilities["managed_fact_state_store_available"] is False

    created = _call(
        session,
        2,
        "research_legal_question",
        {
            "query": "侵權責任如何判斷？",
            "constraints": {
                "research_depth": "quick",
                "discovery_mode": "client_assisted",
            },
        },
    )
    run_id = created["run"]["run_id"]
    registered = _call(
        session,
        3,
        "submit_legal_research_plan",
        {
            "run_id": run_id,
            "operation_id": "register-plan",
            "plan": _plan_payload(),
        },
    )

    assert registered["trust_status"] == "untrusted_client_proposal"
    assert registered["candidate_only"] is True


def test_mcp_rejects_client_evidence_inside_research_plan(tmp_path: Path):
    session = McpSession(
        ready=True,
        research_service=ResearchService(SqliteStore(tmp_path / "cache")),
    )
    created = _call(
        session,
        1,
        "research_legal_question",
        {
            "query": "侵權責任如何判斷？",
            "constraints": {"discovery_mode": "client_assisted"},
        },
    )
    plan = _plan_payload()
    plan["authority_locators"][0]["evidence"] = {
        "official": True,
        "text": "caller supplied",
    }

    response = session.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "submit_legal_research_plan",
                "arguments": {
                    "run_id": created["run"]["run_id"],
                    "operation_id": "unsafe-plan",
                    "plan": plan,
                },
            },
        }
    )

    assert response is not None
    assert response["error"]["code"] == -32602


def test_mcp_rejects_source_bodies_inside_unified_analysis(tmp_path: Path):
    session = McpSession(
        ready=True,
        research_service=ResearchService(SqliteStore(tmp_path / "cache")),
    )
    analysis = {
        "analysis_id": "analysis-mcp",
        "analyses": [
            {
                "profile": "civil_substantive",
                "claims": [
                    {
                        "claim_id": "claim-1",
                        "label": "示範請求",
                        "legal_basis_source_ids": ["source-1"],
                        "requested_effects": ["right_constituting"],
                    }
                ],
                "elements": [
                    {
                        "element_id": "element-1",
                        "claim_id": "claim-1",
                        "label": "示範要件",
                        "proposition": "是否符合示範要件？",
                        "legal_effect": "right_constituting",
                        "status": "uncertain",
                    }
                ],
            }
        ],
        "counter_authority": {"status": "not_searched"},
        "procedural_posture": {
            "stage": "unknown",
            "description": "尚待確認",
        },
        "source_records": [
            {
                "source_id": "source-1",
                "official": True,
                "text": "caller supplied",
            }
        ],
    }

    response = session.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "validate_legal_analysis",
                "arguments": {
                    "run_id": "run-does-not-matter",
                    "operation_id": "unsafe-analysis",
                    "analysis": analysis,
                },
            },
        }
    )

    assert response is not None
    assert response["error"]["code"] == -32602
    assert "Extra inputs are not permitted" in response["error"]["message"]
