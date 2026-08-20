from __future__ import annotations

import json

import pytest

from alr_tw.config.settings import ALR_TW_MCP_TOOL_PROFILE, Settings
from alr_tw.contracts import ToolProfile as PublicToolProfile
from alr_tw.contracts.providers import DataMode, ToolProfile
from tw_legal_rag_mcp.mcp_server.server import McpSession, call_tool, tool_definitions
from tw_legal_rag_mcp.mcp_server.tool_catalog import (
    SERVER_OWNED_TOOL_NAMES,
    TOOL_CATALOG,
    TOOL_CATALOG_BY_NAME,
    ToolCategory,
    tool_names_for_profile,
)


def _tool_result(response: dict) -> dict:
    return json.loads(response["content"][0]["text"])


def _listed_tool_names(session: McpSession) -> list[str]:
    response = session.handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    )
    assert response is not None
    return [item["name"] for item in response["result"]["tools"]]


def _listed_names(session: McpSession) -> set[str]:
    return set(_listed_tool_names(session))


def _capabilities(session: McpSession) -> dict:
    response = session.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "get_legal_research_capabilities", "arguments": {}},
        }
    )
    assert response is not None
    assert response["result"]["isError"] is False
    return _tool_result(response["result"])["data"]


@pytest.mark.parametrize(
    "mode", [DataMode.SYNTHETIC, DataMode.OFFICIAL_ONLY, DataMode.HYBRID_VERIFIED]
)
def test_data_mode_defaults_keep_profile_separate(mode: DataMode) -> None:
    settings = Settings.from_env({"ALR_TW_DATA_MODE": mode.value})

    assert settings.data_mode is mode
    assert settings.tool_profile is (
        ToolProfile.DEMO if mode is DataMode.SYNTHETIC else ToolProfile.VERIFIED
    )


def test_explicit_profile_can_opt_in_independently_of_data_mode() -> None:
    settings = Settings.from_env(
        {
            "ALR_TW_DATA_MODE": DataMode.OFFICIAL_ONLY.value,
            ALR_TW_MCP_TOOL_PROFILE: ToolProfile.DEMO.value,
        }
    )

    assert settings.data_mode is DataMode.OFFICIAL_ONLY
    assert settings.tool_profile is ToolProfile.DEMO


def test_tool_profile_is_exported_from_contract_package() -> None:
    assert PublicToolProfile is ToolProfile


def test_unknown_profile_fails_closed_at_settings_and_session_startup(monkeypatch) -> None:
    with pytest.raises(ValueError):
        Settings.from_env({ALR_TW_MCP_TOOL_PROFILE: "unknown"})

    monkeypatch.setenv(ALR_TW_MCP_TOOL_PROFILE, "unknown")
    with pytest.raises(ValueError):
        McpSession(ready=True)


def test_catalog_covers_all_tool_definitions_with_behavioral_categories() -> None:
    catalog_names = [entry.name for entry in TOOL_CATALOG]

    assert catalog_names == [
        definition["name"] for definition in tool_definitions(ToolProfile.DEMO)
    ]
    assert len(TOOL_CATALOG_BY_NAME) == len(TOOL_CATALOG)
    assert {entry.category for entry in TOOL_CATALOG} == set(ToolCategory)
    assert SERVER_OWNED_TOOL_NAMES == {
        entry.name for entry in TOOL_CATALOG if entry.category is ToolCategory.SERVER_OWNED
    }

    assert TOOL_CATALOG_BY_NAME["exact_law_lookup"].category is ToolCategory.SYNTHETIC_DEMO
    assert TOOL_CATALOG_BY_NAME["begin_agentic_run"].category is ToolCategory.LEGACY_COMPATIBILITY
    assert TOOL_CATALOG_BY_NAME["validate_citation"].category is ToolCategory.LEGACY_COMPATIBILITY
    assert TOOL_CATALOG_BY_NAME["research_legal_question"].category is ToolCategory.SERVER_OWNED
    assert TOOL_CATALOG_BY_NAME["lookup_legislative_history"].category is ToolCategory.SERVER_OWNED


def test_profiles_filter_tools_and_mark_non_server_descriptions() -> None:
    verified = set(tool_names_for_profile(ToolProfile.VERIFIED))
    compatibility = set(tool_names_for_profile(ToolProfile.COMPATIBILITY))
    demo = set(tool_names_for_profile(ToolProfile.DEMO))

    assert verified == SERVER_OWNED_TOOL_NAMES
    assert verified < compatibility < demo
    assert demo == set(TOOL_CATALOG_BY_NAME)
    assert all(
        TOOL_CATALOG_BY_NAME[name].category is not ToolCategory.SYNTHETIC_DEMO
        for name in compatibility
    )

    for definition in tool_definitions(ToolProfile.DEMO):
        first_line = definition["description"].splitlines()[0]
        category = TOOL_CATALOG_BY_NAME[definition["name"]].category
        if category is ToolCategory.SYNTHETIC_DEMO:
            assert first_line.startswith("[DEMO ONLY]")
            assert "lookup_legal_source" in first_line
        elif category is ToolCategory.LEGACY_COMPATIBILITY:
            assert first_line.startswith("[LEGACY COMPATIBILITY]")


def test_session_tools_list_and_direct_call_share_profile_gate() -> None:
    session = McpSession(ready=True, tool_profile=ToolProfile.VERIFIED)

    assert _listed_names(session) == SERVER_OWNED_TOOL_NAMES
    result = call_tool(
        {
            "name": "exact_law_lookup",
            "arguments": {"title": "示範租賃規則", "article_no": "第1條"},
        },
        session=session,
    )
    payload = _tool_result(result)

    assert result["isError"] is True
    assert payload["ok"] is False
    assert payload["error"]["code"] == "TOOL_NOT_AVAILABLE_IN_PROFILE"
    assert payload["error"]["details"]["profile"] == ToolProfile.VERIFIED.value
    assert "lookup_legal_source" in payload["error"]["message"]


def test_capabilities_report_active_profile_and_exact_tools_list() -> None:
    session = McpSession(
        ready=True,
        settings=Settings(data_mode=DataMode.OFFICIAL_ONLY),
        tool_profile=ToolProfile.DEMO,
    )

    listed = _listed_tool_names(session)
    capabilities = _capabilities(session)

    assert capabilities["active_data_mode"] == DataMode.OFFICIAL_ONLY.value
    assert capabilities["active_mcp_tool_profile"] == ToolProfile.DEMO.value
    assert capabilities["available_mcp_tool_names"] == listed


def test_session_profile_and_settings_do_not_drift_with_environment(monkeypatch) -> None:
    monkeypatch.setenv("ALR_TW_DATA_MODE", DataMode.SYNTHETIC.value)
    monkeypatch.delenv(ALR_TW_MCP_TOOL_PROFILE, raising=False)
    session = McpSession(ready=True)

    monkeypatch.setenv("ALR_TW_DATA_MODE", DataMode.OFFICIAL_ONLY.value)
    monkeypatch.setenv(ALR_TW_MCP_TOOL_PROFILE, ToolProfile.VERIFIED.value)

    assert session.settings.data_mode is DataMode.SYNTHETIC
    assert session.tool_profile is ToolProfile.DEMO
    listed = _listed_tool_names(session)
    assert listed == list(tool_names_for_profile(ToolProfile.DEMO))
    capabilities = _capabilities(session)
    assert capabilities["active_data_mode"] == DataMode.SYNTHETIC.value
    assert capabilities["active_mcp_tool_profile"] == ToolProfile.DEMO.value
    assert capabilities["available_mcp_tool_names"] == listed
    allowed = session.handle_message(
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
    assert allowed is not None
    assert allowed["result"]["isError"] is False

    fresh = McpSession(ready=True)
    assert fresh.settings.data_mode is DataMode.OFFICIAL_ONLY
    assert fresh.tool_profile is ToolProfile.VERIFIED
    assert _listed_names(fresh) == SERVER_OWNED_TOOL_NAMES
