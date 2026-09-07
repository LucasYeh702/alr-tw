from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest

from alr_tw.cli import main as cli_main
from alr_tw.config import Settings
from alr_tw.contracts.provider_snapshot import ProviderSnapshotReceipt
from alr_tw.contracts.providers import DataMode
from alr_tw.contracts.research import ResearchDepth, ResearchObligationKind
from alr_tw.contracts.sources import (
    EvidenceSpan,
    MaterialType,
    SourceRecord,
    SourceTier,
    TrustStatus,
)
from alr_tw.research.service import ResearchService, _plan_obligations
from alr_tw.storage.sqlite_store import SqliteStore
from tw_legal_rag_mcp.mcp_server.server import McpSession, tool_definitions


def _quick_kinds(query: str) -> set[ResearchObligationKind]:
    return {
        item.kind
        for item in _plan_obligations(
            query,
            mode=DataMode.OFFICIAL_ONLY,
            depth=ResearchDepth.QUICK,
            as_of_date=None,
            include_counter_authority=False,
        )
    }


@pytest.mark.parametrize(
    "query",
    [
        "DEMO,130,測,1,20990101,1",
        "示範法院130年度測字第1號",
    ],
)
def test_quick_routes_bare_judgment_identifiers_to_official_verification(query: str) -> None:
    kinds = _quick_kinds(query)

    assert ResearchObligationKind.JUDGMENT_RECALL in kinds
    assert ResearchObligationKind.JUDGMENT_OFFICIAL_VERIFICATION in kinds


def test_quick_plain_reference_does_not_trigger_judgment_path() -> None:
    kinds = _quick_kinds("民法第184條")

    assert ResearchObligationKind.JUDGMENT_RECALL not in kinds
    assert ResearchObligationKind.JUDGMENT_OFFICIAL_VERIFICATION not in kinds


def test_execute_tool_exposes_operation_prefix_not_idempotency_fields() -> None:
    definition = next(
        item for item in tool_definitions("verified") if item["name"] == "execute_legal_research"
    )
    properties = definition["inputSchema"]["properties"]

    assert "operation_prefix" in properties
    assert "operation_id" not in properties
    assert "client_id" not in properties
    assert "request_id" not in properties
    assert "not a request idempotency key" in properties["operation_prefix"]["description"]


def test_execute_tool_rejects_legacy_operation_id(tmp_path: Path) -> None:
    service = ResearchService(SqliteStore(tmp_path / "cache"))
    session = McpSession(ready=True, settings=Settings(), research_service=service)

    response = session.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "execute_legal_research",
                "arguments": {"query": "民法第184條", "operation_id": "retry-key"},
            },
        }
    )

    assert response is not None
    assert response["error"]["code"] == -32602
    assert "unexpected argument" in response["error"]["message"]


def test_provider_cli_cannot_self_certify_caller_envelope(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    now = datetime.now(UTC)
    provider_id = "fake-official-provider"
    text = "合成法規內容，僅供結構契約測試。"
    digest = EvidenceSpan.hash_text(text)
    source = SourceRecord(
        source_id="fake-source",
        source_key="law:fake",
        source_version_id="law:fake:v1",
        material_type=MaterialType.LAW,
        provider_id=provider_id,
        source_tier=SourceTier.OFFICIAL,
        trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
        official_identifier="FAKE:1",
        official_url="https://example.test/fake-law",
        citation="合成法第1條",
        fetched_at=now - timedelta(minutes=2),
        verified_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(hours=1),
        content_hash=digest,
        normalized_content_hash=digest,
        normalized_text=text,
    )
    evidence = EvidenceSpan.from_exact_text(
        evidence_id="fake-evidence",
        source_id=source.source_id,
        section_id="article-1",
        section_type="law_text",
        exact_text=text,
        eligible_for_claim_support=True,
    )
    receipt = ProviderSnapshotReceipt(
        receipt_id="fake-receipt",
        provider_id=provider_id,
        snapshot_id="fake-snapshot",
        generation="fake-generation",
        issued_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(hours=1),
        content_digest=digest,
    )
    envelope = {
        "request": {
            "provider_id": provider_id,
            "role": "official_verifier",
            "bounded_scope": "caller supplied test scope",
            "expected_material_types": ["law"],
            "require_snapshot_receipt": True,
        },
        "result": {
            "status": "found",
            "provider_id": provider_id,
            "source_ids": [source.source_id],
            "evidence_ids": [evidence.evidence_id],
            "coverage_complete": True,
        },
        "server_sources": [source.model_dump(mode="json")],
        "server_evidence": [evidence.model_dump(mode="json")],
        "receipts": [receipt.model_dump(mode="json")],
        "server_receipts": [receipt.model_dump(mode="json")],
    }
    path = tmp_path / "caller-envelope.json"
    path.write_text(json.dumps(envelope), encoding="utf-8")

    exit_code = cli_main(["verify-provider", "--input", str(path)])
    payload = json.loads(capsys.readouterr().out)["data"]

    assert exit_code == 0
    assert payload["decision"] == "qualified"
    assert payload["input_trust"] == "caller_supplied_envelope"
    assert payload["validation_scope"] == "structural_conformance_only"
    assert payload["server_owned_decision"] is False
    assert payload["runtime_promotion_authorized"] is False
    assert payload["ordinary_eligible"] is False
    assert payload["absence_claim_allowed"] is False
    assert payload["eligible_source_ids"] == []
    assert payload["eligible_evidence_ids"] == []
    assert "PROVIDER_CLI_CALLER_SUPPLIED_ENVELOPE" in payload["reason_codes"]
