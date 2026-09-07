from __future__ import annotations

import json
from pathlib import Path

import pytest

from alr_tw.cli import main as cli_main
from alr_tw.config import Settings
from alr_tw.contracts.interop import DiscoveryMode
from alr_tw.contracts.providers import (
    CandidateRecallProvider,
    DataMode,
    LineageCandidateProvider,
)
from alr_tw.contracts.research import (
    ResearchDepth,
    ResearchObligation,
    ResearchObligationKind,
    ResearchRun,
)
from alr_tw.providers.tlr import TlrSemanticRecallProvider
from alr_tw.research.service import ResearchService, _plan_obligations
from alr_tw.storage.sqlite_store import SqliteStore
from tw_legal_rag_mcp.mcp_server.server import McpSession


JUDGMENT_QUERY = "請查找定型化契約條款效力的相關裁判"


def _tool_call(session: McpSession, name: str, arguments: dict) -> dict:
    response = session.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    assert response is not None
    assert response["result"]["isError"] is False
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    return payload["data"]


def test_quick_judgment_plan_keeps_authenticity_checks_and_skips_breadth() -> None:
    obligations = _plan_obligations(
        JUDGMENT_QUERY,
        mode=DataMode.OFFICIAL_ONLY,
        depth=ResearchDepth.QUICK,
        as_of_date=None,
        include_counter_authority=True,
    )
    kinds = [item.kind for item in obligations]

    assert kinds == [
        ResearchObligationKind.QUERY_UNDERSTANDING,
        ResearchObligationKind.JUDGMENT_RECALL,
        ResearchObligationKind.JUDGMENT_OFFICIAL_VERIFICATION,
        ResearchObligationKind.EVIDENCE_SUFFICIENCY,
        ResearchObligationKind.FINAL_ANSWER_VALIDATION,
    ]


def test_quick_judgment_plan_keeps_explicit_statute_lookup() -> None:
    obligations = _plan_obligations(
        f"依消費者保護法第12條，{JUDGMENT_QUERY}",
        mode=DataMode.OFFICIAL_ONLY,
        depth=ResearchDepth.QUICK,
        as_of_date=None,
        include_counter_authority=False,
    )

    assert ResearchObligationKind.LAW_RESEARCH in {item.kind for item in obligations}


@pytest.mark.parametrize("citation", ["民法第184條", "刑法第10條", "憲法第7條"])
def test_quick_plan_recognizes_one_and_two_character_law_names(citation: str) -> None:
    obligations = _plan_obligations(
        f"依{citation}找相關判決",
        mode=DataMode.OFFICIAL_ONLY,
        depth=ResearchDepth.QUICK,
        as_of_date=None,
        include_counter_authority=False,
    )

    assert ResearchObligationKind.LAW_RESEARCH in {item.kind for item in obligations}


@pytest.mark.parametrize("value", [0, 6, True])
def test_judgment_verification_budget_is_bounded(value: int, tmp_path: Path) -> None:
    service = ResearchService(SqliteStore(tmp_path / "cache"))

    with pytest.raises(ValueError, match="between 1 and 5"):
        service.create_run(
            JUDGMENT_QUERY,
            mode=DataMode.SYNTHETIC,
            depth=ResearchDepth.QUICK,
            max_judgment_verifications=value,
        )


def test_quick_run_rejects_explicit_counter_authority(tmp_path: Path) -> None:
    service = ResearchService(SqliteStore(tmp_path / "cache"))

    with pytest.raises(ValueError, match="incompatible with research_depth=quick"):
        service.create_run(
            JUDGMENT_QUERY,
            mode=DataMode.SYNTHETIC,
            depth=ResearchDepth.QUICK,
            include_counter_authority=True,
        )

    run = service.create_run(
        JUDGMENT_QUERY,
        mode=DataMode.SYNTHETIC,
        depth=ResearchDepth.QUICK,
    )
    assert run.include_counter_authority is False


def test_autonomous_execution_stops_before_draft_validation(tmp_path: Path) -> None:
    service = ResearchService(SqliteStore(tmp_path / "cache"))
    run = service.create_run(
        "民法第184條",
        mode=DataMode.SYNTHETIC,
        depth=ResearchDepth.QUICK,
    )

    result = service.execute_run_to_completion(run.run_id)

    assert result["stop_reason"] == "ready_for_draft"
    assert result["step_count"] == 3
    assert result["elapsed_ms"] >= 0
    assert all(step["elapsed_ms"] >= 0 for step in result["steps"])
    assert result["evidence_bundle"]["status"] == "not_found_in_scope"
    final_obligation = result["state"]["run"]["obligations"][-1]
    assert final_obligation["kind"] == "final_answer_validation"
    assert final_obligation["status"] == "pending"


class _RetryableExecutor:
    def execute(
        self,
        run: ResearchRun,
        obligation: ResearchObligation,
    ) -> dict:
        del run
        return {
            "status": "error",
            "obligation": obligation.kind.value,
            "warnings": ["OFFICIAL_SOURCE_UNAVAILABLE"],
            "provider_calls": [],
        }


def test_autonomous_execution_does_not_hammer_retryable_provider(tmp_path: Path) -> None:
    service = ResearchService(
        SqliteStore(tmp_path / "cache"),
        _RetryableExecutor(),
    )
    run = service.create_run(
        "民法第184條",
        mode=DataMode.OFFICIAL_ONLY,
        depth=ResearchDepth.QUICK,
    )

    result = service.execute_run_to_completion(run.run_id)

    assert result["stop_reason"] == "retry_required"
    assert result["step_count"] == 1
    assert result["steps"][0]["retryable"] is True


def test_autonomous_execution_waits_for_client_assisted_plan(tmp_path: Path) -> None:
    service = ResearchService(SqliteStore(tmp_path / "cache"))
    run = service.create_run(
        JUDGMENT_QUERY,
        mode=DataMode.SYNTHETIC,
        depth=ResearchDepth.QUICK,
        discovery_mode=DiscoveryMode.CLIENT_ASSISTED,
    )

    result = service.execute_run_to_completion(run.run_id)

    assert result["stop_reason"] == "awaiting_external_plan"
    assert result["step_count"] == 0


def test_mcp_prompt_command_activates_bounded_quick_mode(tmp_path: Path) -> None:
    service = ResearchService(SqliteStore(tmp_path / "cache"))
    session = McpSession(
        ready=True,
        settings=Settings(),
        research_service=service,
    )

    result = _tool_call(
        session,
        "execute_legal_research",
        {
            "query": f"/quick {JUDGMENT_QUERY}",
            "constraints": {"max_judgment_verifications": 3},
        },
    )
    stored = service.get_run(result["run_id"])

    assert result["stop_reason"] == "ready_for_draft"
    assert stored is not None
    assert stored.query == JUDGMENT_QUERY
    assert stored.research_depth is ResearchDepth.QUICK
    assert stored.max_judgment_verifications == 3
    assert stored.include_counter_authority is False
    assert ResearchObligationKind.JUDGMENT_OFFICIAL_VERIFICATION in {
        item.kind for item in stored.obligations
    }


def test_mcp_chinese_prompt_command_and_constraint_must_agree(tmp_path: Path) -> None:
    service = ResearchService(SqliteStore(tmp_path / "cache"))
    session = McpSession(
        ready=True,
        settings=Settings(),
        research_service=service,
    )
    created = _tool_call(
        session,
        "research_legal_question",
        {"query": f"快速模式：{JUDGMENT_QUERY}"},
    )
    assert created["run"]["research_depth"] == "quick"

    response = session.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "research_legal_question",
                "arguments": {
                    "query": f"/quick {JUDGMENT_QUERY}",
                    "constraints": {"research_depth": "deep"},
                },
            },
        }
    )
    assert response is not None
    assert response["error"]["code"] == -32602
    assert "conflicts" in response["error"]["message"]


def test_mcp_quick_rejects_explicit_counter_authority(tmp_path: Path) -> None:
    service = ResearchService(SqliteStore(tmp_path / "cache"))
    session = McpSession(
        ready=True,
        settings=Settings(),
        research_service=service,
    )

    response = session.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "research_legal_question",
                "arguments": {
                    "query": f"/quick {JUDGMENT_QUERY}",
                    "constraints": {"include_counter_authority": True},
                },
            },
        }
    )
    assert response is not None
    assert response["error"]["code"] == -32602
    assert "incompatible with research_depth=quick" in response["error"]["message"]


def test_tlr_reference_adapter_satisfies_candidate_protocols() -> None:
    provider = TlrSemanticRecallProvider()

    assert isinstance(provider, CandidateRecallProvider)
    assert isinstance(provider, LineageCandidateProvider)


def test_verify_provider_cli_is_env_independent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    envelope = {
        "request": {
            "provider_id": "candidate-provider",
            "role": "candidate_only",
            "bounded_scope": "top_k=5",
        },
        "result": {
            "status": "found",
            "provider_id": "candidate-provider",
            "candidates": [
                {
                    "candidate_id": "candidate-1",
                    "provider_id": "candidate-provider",
                    "official_identifier": "DEMO,113,測,1,20990101,1",
                    "metadata": {"candidate_only": True},
                }
            ],
            "coverage_complete": False,
        },
    }
    path = tmp_path / "provider-envelope.json"
    path.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("ALR_TW_RETENTION", "invalid-setting")

    exit_code = cli_main(["verify-provider", "--input", str(path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["data"]["decision"] == "qualified"
    assert payload["data"]["candidate_count"] == 1


@pytest.mark.parametrize(
    "field",
    ["server_sources", "server_evidence", "receipts", "server_receipts"],
)
def test_verify_provider_cli_rejects_null_arrays_without_traceback(
    field: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    envelope = {
        "request": {
            "provider_id": "candidate-provider",
            "role": "candidate_only",
            "bounded_scope": "top_k=5",
        },
        "result": {
            "status": "not_found",
            "provider_id": "candidate-provider",
            "coverage_complete": True,
        },
        field: None,
    }
    path = tmp_path / f"provider-envelope-{field}.json"
    path.write_text(json.dumps(envelope), encoding="utf-8")

    exit_code = cli_main(["verify-provider", "--input", str(path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload == {
        "ok": False,
        "error": f"PROVIDER_CONFORMANCE_{field.upper()}_MUST_BE_ARRAY",
    }
