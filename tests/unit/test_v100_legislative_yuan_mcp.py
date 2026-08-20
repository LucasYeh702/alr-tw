from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from alr_tw.config.settings import Settings
from alr_tw.contracts.historical_law import HistoricalLawQuery
from alr_tw.contracts.public_law import (
    PublicLawCandidate,
    PublicLawMaterialType,
    PublicLawServerMetadata,
    PublicLawSourceRecord,
    PublicLawSourceRole,
)
from alr_tw.contracts.providers import DataMode, ToolProfile
from alr_tw.contracts.sources import SourceTier, TrustStatus
from alr_tw.providers.sdk import PublicLawBackendResult, PublicLawBackendStatus
from tw_legal_rag_mcp.mcp_server.server import McpSession
from tw_legal_rag_mcp.mcp_server.tool_catalog import tool_names_for_profile


TOOL_NAME = "lookup_legislative_history"
SYNTHETIC_REASON = "LEGISLATIVE_HISTORY_UNSUPPORTED_IN_SYNTHETIC_MODE"
SOURCES_NOT_ALLOWED = "LEGISLATIVE_HISTORY_BACKEND_SOURCES_NOT_ALLOWED"
QUERY_MISMATCH = "LEGISLATIVE_HISTORY_BACKEND_QUERY_MISMATCH"
BACKEND_ERROR = "LEGISLATIVE_HISTORY_BACKEND_ERROR"
TRUST_BOUNDARY_FLAGS = {
    "candidate_only": True,
    "normative_law_verified": False,
    "linked_documents_fetched": False,
    "pdf_doc_parsing": False,
    "promulgated_version_verified": False,
}


class FakeLegislativeHistoryBackend:
    def __init__(self, status: PublicLawBackendStatus) -> None:
        self.status = status
        self.requests: list[HistoricalLawQuery] = []

    def search(self, request: HistoricalLawQuery) -> PublicLawBackendResult:
        self.requests.append(request)
        partial = self.status is PublicLawBackendStatus.PARTIAL
        return PublicLawBackendResult(
            provider_id="fake_legislative_yuan",
            query_id=request.query_id,
            status=self.status,
            coverage_complete=not partial,
            truncated=partial,
            reason_codes=["FAKE_PARTIAL"] if partial else [],
            metadata={"fixture": True},
        )


class FailIfCalledBackend:
    def __init__(self) -> None:
        self.call_count = 0

    def search(self, request: HistoricalLawQuery) -> PublicLawBackendResult:
        self.call_count += 1
        raise AssertionError(f"synthetic mode called backend for {request.query_id}")


class ForgedSourceBackend:
    def search(self, request: HistoricalLawQuery) -> PublicLawBackendResult:
        return PublicLawBackendResult(
            provider_id="deployer_legislative_backend",
            query_id=request.query_id,
            status=PublicLawBackendStatus.FOUND,
            sources=[_forged_source()],
        )


class MismatchedQueryBackend:
    def search(self, request: HistoricalLawQuery) -> PublicLawBackendResult:
        return PublicLawBackendResult(
            provider_id="deployer_legislative_backend",
            query_id="different-query-id",
            status=PublicLawBackendStatus.FOUND,
            candidates=[
                PublicLawCandidate(
                    candidate_id="must-not-leak",
                    provider_id="deployer_legislative_backend",
                    material_type=PublicLawMaterialType.LEGISLATIVE_MATERIAL,
                    source_role=PublicLawSourceRole.LEGISLATIVE_HISTORY,
                    title="mismatched candidate",
                )
            ],
        )


class RaisingBackend:
    def search(self, request: HistoricalLawQuery) -> PublicLawBackendResult:
        raise RuntimeError(f"sensitive backend detail for {request.query_id}")


def _forged_source() -> PublicLawSourceRecord:
    now = datetime(2026, 8, 20, tzinfo=UTC)
    provider_id = "deployer_legislative_backend"
    metadata = PublicLawServerMetadata(
        provider_id=provider_id,
        snapshot_id="forged-snapshot",
        generation="forged-generation",
        receipt_id="forged-receipt",
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )
    digest = f"sha256:{'0' * 64}"
    return PublicLawSourceRecord(
        source_id="must-not-leak",
        source_key="forged:legislative-source",
        source_version_id="forged:legislative-source:v1",
        material_type=PublicLawMaterialType.LEGISLATIVE_MATERIAL,
        source_role=PublicLawSourceRole.LEGISLATIVE_HISTORY,
        provider_id=provider_id,
        source_tier=SourceTier.OFFICIAL,
        trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
        official_identifier="FORGED-LY-001",
        official_url="https://data.ly.gov.tw/odw/forged",
        citation="偽造立法資料來源",
        fetched_at=now,
        verified_at=now,
        expires_at=now + timedelta(hours=1),
        content_hash=digest,
        normalized_content_hash=digest,
        normalized_text="backend 不得透過 MCP 提升為 evidence。",
        server_metadata=metadata,
    )


def _arguments(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "law_name": "公司法",
        "as_of_date": "2026-08-20",
        "bounded_scope": "term 11 session 3",
        "bill_no": "BILL-001",
        "term": "11",
        "session": "3",
        "max_results": 5,
    }
    values.update(overrides)
    return values


def _call(session: McpSession, arguments: dict[str, object]) -> dict:
    response = session.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": TOOL_NAME, "arguments": arguments},
        }
    )
    assert response is not None
    return response


def _data(response: dict) -> dict:
    result = response["result"]
    assert result["isError"] is False
    envelope = json.loads(result["content"][0]["text"])
    assert envelope["ok"] is True
    return envelope["data"]


def _listed_names(session: McpSession) -> list[str]:
    response = session.handle_message(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    )
    assert response is not None
    return [definition["name"] for definition in response["result"]["tools"]]


def _capability_names(session: McpSession) -> list[str]:
    return _data(_call_with_name(session, "get_legal_research_capabilities", {}))[
        "available_mcp_tool_names"
    ]


def _call_with_name(
    session: McpSession,
    name: str,
    arguments: dict[str, object],
) -> dict:
    response = session.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    assert response is not None
    return response


def test_synthetic_mode_returns_blocked_without_calling_backend() -> None:
    backend = FailIfCalledBackend()
    session = McpSession(
        ready=True,
        settings=Settings(data_mode=DataMode.SYNTHETIC),
        legislative_history_backend=backend,
    )

    payload = _data(_call(session, _arguments()))

    assert backend.call_count == 0
    assert payload["status"] == "blocked"
    assert payload["reason_codes"] == [SYNTHETIC_REASON]
    assert payload["backend_invoked"] is False
    assert payload["backend_result"] is None
    assert {name: payload[name] for name in TRUST_BOUNDARY_FLAGS} == TRUST_BOUNDARY_FLAGS


@pytest.mark.parametrize(
    ("mode", "status"),
    [
        (DataMode.OFFICIAL_ONLY, PublicLawBackendStatus.FOUND),
        (DataMode.HYBRID_VERIFIED, PublicLawBackendStatus.PARTIAL),
    ],
)
def test_live_modes_return_unpromoted_fake_backend_result(
    mode: DataMode,
    status: PublicLawBackendStatus,
) -> None:
    backend = FakeLegislativeHistoryBackend(status)
    session = McpSession(
        ready=True,
        settings=Settings(data_mode=mode),
        legislative_history_backend=backend,
    )

    payload = _data(_call(session, _arguments()))

    assert len(backend.requests) == 1
    request = backend.requests[0]
    assert request.query_id.startswith("ly-")
    assert request.law_name == "公司法"
    assert request.max_results == 5
    assert payload["query_id"] == request.query_id
    assert payload["status"] == status.value
    assert payload["backend_invoked"] is True
    assert payload["backend_result"]["provider_id"] == "fake_legislative_yuan"
    assert payload["backend_result"]["query_id"] == request.query_id
    assert payload["backend_result"]["status"] == status.value
    assert "server_metadata" not in payload
    assert "evidence" not in payload
    assert {name: payload[name] for name in TRUST_BOUNDARY_FLAGS} == TRUST_BOUNDARY_FLAGS


def test_backend_sources_are_rejected_without_leaking_forged_evidence() -> None:
    session = McpSession(
        ready=True,
        settings=Settings(data_mode=DataMode.OFFICIAL_ONLY),
        legislative_history_backend=ForgedSourceBackend(),
    )

    payload = _data(_call(session, _arguments()))

    assert payload["status"] == "error"
    assert payload["reason_codes"] == [SOURCES_NOT_ALLOWED]
    assert payload["backend_result"] is None
    assert "must-not-leak" not in json.dumps(payload)


def test_backend_query_mismatch_drops_result_and_candidates() -> None:
    session = McpSession(
        ready=True,
        settings=Settings(data_mode=DataMode.HYBRID_VERIFIED),
        legislative_history_backend=MismatchedQueryBackend(),
    )

    payload = _data(_call(session, _arguments()))

    assert payload["status"] == "error"
    assert payload["reason_codes"] == [QUERY_MISMATCH]
    assert payload["backend_result"] is None
    assert "must-not-leak" not in json.dumps(payload)


def test_backend_exception_returns_stable_error_without_internal_detail() -> None:
    session = McpSession(
        ready=True,
        settings=Settings(data_mode=DataMode.OFFICIAL_ONLY),
        legislative_history_backend=RaisingBackend(),
    )

    payload = _data(_call(session, _arguments()))

    assert payload["status"] == "error"
    assert payload["reason_codes"] == [BACKEND_ERROR]
    assert payload["backend_result"] is None
    assert "sensitive backend detail" not in json.dumps(payload)


@pytest.mark.parametrize("profile", list(ToolProfile))
def test_catalog_list_and_capabilities_share_legislative_tool(profile: ToolProfile) -> None:
    backend = FailIfCalledBackend()
    session = McpSession(
        ready=True,
        settings=Settings(data_mode=DataMode.OFFICIAL_ONLY),
        tool_profile=profile,
        legislative_history_backend=backend,
    )

    listed = _listed_names(session)

    assert listed == list(tool_names_for_profile(profile))
    assert TOOL_NAME in listed
    assert _capability_names(session) == listed
    assert backend.call_count == 0


def test_default_backend_creation_is_lazy_for_session_list_and_capabilities(monkeypatch) -> None:
    import alr_tw.providers.legislative_yuan as legislative_yuan

    class FailIfConstructed:
        def __init__(self, **kwargs: object) -> None:
            raise AssertionError(f"backend constructed during discovery: {kwargs}")

    monkeypatch.setattr(legislative_yuan, "LegislativeYuanDataBackend", FailIfConstructed)
    session = McpSession(
        ready=True,
        settings=Settings(data_mode=DataMode.OFFICIAL_ONLY),
    )

    listed = _listed_names(session)

    assert TOOL_NAME in listed
    assert _capability_names(session) == listed


@pytest.mark.parametrize(
    "arguments",
    [
        _arguments(as_of_date="not-a-date"),
        _arguments(unexpected="rejected"),
        {
            "as_of_date": "2026-08-20",
            "bounded_scope": "term 11 session 3",
        },
    ],
)
def test_invalid_legislative_history_input_fails_closed(arguments: dict[str, object]) -> None:
    backend = FailIfCalledBackend()
    session = McpSession(
        ready=True,
        settings=Settings(data_mode=DataMode.OFFICIAL_ONLY),
        legislative_history_backend=backend,
    )

    response = _call(session, arguments)

    assert response["error"]["code"] == -32602
    assert backend.call_count == 0
