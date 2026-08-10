from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

from alr_tw.contracts.providers import DataMode
from alr_tw.contracts.finalization import build_finalization_from_run
from alr_tw.contracts.research import (
    ResearchObligation,
    ResearchObligationKind,
    ResearchDepth,
    ResearchObligationStatus,
    ResearchState,
)
from alr_tw.contracts.sources import (
    EvidenceSpan,
    MaterialType,
    SourceRecord,
    SourceTier,
    TrustStatus,
)
from alr_tw.providers.synthetic import SyntheticLegalContextProvider
from alr_tw.research.service import ResearchService
from alr_tw.storage.sqlite_store import SqliteStore
from alr_tw.contracts.provider_snapshot import ProviderSnapshotReceipt
from tw_legal_rag_mcp.mcp_server.server import McpSession, tool_definitions


# Keep the synthetic fixture clock safely ahead of the wall clock.  Tests that
# exercise expiry explicitly derive both the source expiry and ``now`` from
# this constant, so freshness semantics remain deterministic without
# weakening production expiry checks.
NOW = datetime(2099, 1, 1, 8, 0, tzinfo=UTC)


def _prepared_service(
    tmp_path: Path,
    *,
    ready: bool = True,
    mode: DataMode = DataMode.SYNTHETIC,
    source_expires_at: datetime | None = None,
) -> tuple[ResearchService, str, str]:
    store = SqliteStore(tmp_path / "cache")
    service = ResearchService(
        store,
        legal_context_provider=SyntheticLegalContextProvider({"source-1"}),
    )
    run = service.create_run(
        "合成責任法法律研究",
        mode=mode,
        depth=ResearchDepth.QUICK,
        include_counter_authority=False,
        now=NOW,
    )
    text = "合成責任法第1條：行為人應負合成責任。"
    digest = EvidenceSpan.hash_text(text)
    source = SourceRecord(
        source_id="source-1",
        source_key="law:synthetic:1",
        source_version_id="law:synthetic:1:v1",
        material_type=MaterialType.LAW,
        provider_id="synthetic-law",
        source_tier=SourceTier.OFFICIAL,
        trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
        official_identifier="SYNTHETIC-LAW-1",
        official_url="https://example.test/law/1",
        citation="合成責任法第1條",
        fetched_at=NOW,
        verified_at=NOW,
        # Keep the baseline fixture current for tests that use the real clock;
        # stale-evidence cases override this timestamp explicitly.
        expires_at=source_expires_at or NOW + timedelta(hours=24),
        content_hash=digest,
        normalized_content_hash=digest,
        normalized_text=text,
        metadata={"synthetic_fixture": True},
    )
    store.save_source(run.run_id, source)
    evidence = EvidenceSpan.from_exact_text(
        evidence_id="evidence-1",
        source_id="source-1",
        section_id="article-1",
        section_type="law_text",
        exact_text=text,
        eligible_for_claim_support=True,
    )
    store.save_evidence(run.run_id, evidence)
    if ready:
        obligations = [
            item.model_copy(update={"status": ResearchObligationStatus.COMPLETED})
            for item in run.obligations
        ]
        run = run.model_copy(
            update={
                "state": ResearchState.READY_FOR_DRAFT,
                "obligations": obligations,
                "source_ids": [source.source_id],
                "evidence_ids": [evidence.evidence_id],
                "coverage": run.coverage.model_copy(
                    update={
                        "law_checked": True,
                        "coverage_complete": True,
                        "time_context_checked": True,
                    }
                ),
            }
        )
        service.store.save_run(run)
    return service, run.run_id, evidence.evidence_id


def test_get_finalization_is_server_owned_and_legacy_receipt_is_conditional(tmp_path: Path):
    service, run_id, _ = _prepared_service(tmp_path, mode=DataMode.OFFICIAL_ONLY)
    payload = service.get_finalization_contract(run_id, now=NOW)
    assert payload["trust_status"] == "server_owned_finalization"
    assert payload["answer_mode"] == "conditional"
    assert payload["snapshot_consistency"]["status"] == "legacy_no_receipt"
    assert payload["allowed_source_ids"] == ["source-1"]
    assert payload["allowed_evidence_ids"] == ["evidence-1"]


def test_expired_evidence_is_removed_from_finalization_refs_and_refuses(
    tmp_path: Path,
):
    service, run_id, _ = _prepared_service(
        tmp_path,
        mode=DataMode.OFFICIAL_ONLY,
        source_expires_at=NOW + timedelta(hours=1),
    )
    payload = service.get_finalization_contract(run_id, now=NOW + timedelta(hours=2))
    assert payload["answer_mode"] == "refusal_only"
    assert payload["research_sufficiency"] == "insufficient"
    assert payload["allowed_source_ids"] == []
    assert payload["allowed_evidence_ids"] == []
    assert "SERVER_EVIDENCE_UNAVAILABLE" in {
        item["code"] for item in payload["blockers"]
    }

    # The full run linkage remains available for audit/revalidation, while the
    # finalization posture contains no stale references.
    state = service.get_state(run_id, now=NOW + timedelta(hours=2))
    assert state["run"]["source_ids"] == ["source-1"]
    assert state["run"]["evidence_ids"] == ["evidence-1"]
    assert state["research_sufficiency"] == "insufficient"
    assert state["answer_mode"] == state["finalization"]["answer_mode"]


def test_validate_answer_rechecks_stale_evidence_before_claim_validation(tmp_path: Path):
    service, run_id, evidence_id = _prepared_service(
        tmp_path,
        mode=DataMode.OFFICIAL_ONLY,
        source_expires_at=NOW + timedelta(hours=1),
    )
    result = service.validate_answer(
        run_id,
        "不應使用過期證據的答案。",
        "validate-stale-evidence",
        claim_bindings=[
            {
                "claim_id": "claim-stale",
                "claim_text": "不應使用過期證據的答案。",
                "claim_type": "law_rule",
                "evidence_ids": [evidence_id],
            }
        ],
        now=NOW + timedelta(hours=2),
    )
    assert result["decision"] == "blocked"
    assert result["decision_code"] == "ANSWER_REFUSAL_ONLY"
    assert result["answer_text"] is None
    assert result["binding_mode"] == "not_executed"
    assert "SERVER_EVIDENCE_UNAVAILABLE" in result["blockers"]


def test_current_law_quick_run_without_temporal_or_counter_obligation_can_be_ordinary(
    tmp_path: Path,
):
    service, run_id, _ = _prepared_service(
        tmp_path,
        mode=DataMode.OFFICIAL_ONLY,
    )
    run = service.get_run(run_id)
    assert run is not None
    # Deliberately leave the temporal receipt false; QUICK creates no temporal
    # obligation, so this must not manufacture a finalization gap. Likewise,
    # include_counter_authority is false here and no counter obligation exists.
    run = run.model_copy(
        update={
            "include_counter_authority": True,
            "coverage": run.coverage.model_copy(update={"time_context_checked": False}),
        }
    )
    receipt = ProviderSnapshotReceipt(
        receipt_id="receipt-current-law",
        provider_id="official-law",
        snapshot_id="snapshot-current-law",
        generation="generation-current-law",
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    contract = build_finalization_from_run(
        run,
        snapshot_receipts=[receipt],
        now=NOW,
    )
    assert contract.answer_mode.value == "ordinary"
    assert contract.counter_authority.required is False
    assert contract.counter_authority.coverage_complete is True
    assert contract.required_qualification == []


def test_explicit_temporal_or_counter_obligation_keeps_missing_gate_fail_closed(
    tmp_path: Path,
):
    service, run_id, _ = _prepared_service(
        tmp_path,
        mode=DataMode.OFFICIAL_ONLY,
    )
    run = service.get_run(run_id)
    assert run is not None
    receipt = ProviderSnapshotReceipt(
        receipt_id="receipt-gated-law",
        provider_id="official-law",
        snapshot_id="snapshot-gated-law",
        generation="generation-gated-law",
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )

    temporal_run = run.model_copy(
        update={
            "obligations": [
                *run.obligations,
                ResearchObligation(
                    kind=ResearchObligationKind.LEGAL_TIME_CONTEXT,
                    status=ResearchObligationStatus.COMPLETED,
                ),
            ],
            "coverage": run.coverage.model_copy(update={"time_context_checked": False}),
        }
    )
    temporal_contract = build_finalization_from_run(
        temporal_run,
        snapshot_receipts=[receipt],
        now=NOW,
    )
    assert temporal_contract.answer_mode.value == "refusal_only"

    counter_run = run.model_copy(
        update={
            "obligations": [
                *run.obligations,
                ResearchObligation(
                    kind=ResearchObligationKind.COUNTER_AUTHORITY,
                    status=ResearchObligationStatus.COMPLETED,
                ),
            ],
            "coverage": run.coverage.model_copy(
                update={"counter_authority_checked": False}
            ),
        }
    )
    counter_contract = build_finalization_from_run(
        counter_run,
        snapshot_receipts=[receipt],
        now=NOW,
    )
    assert counter_contract.answer_mode.value == "conditional"
    assert counter_contract.counter_authority.required is True
    assert counter_contract.counter_authority.coverage_complete is False


def test_conditional_finalization_cannot_be_upgraded_to_validated(tmp_path: Path):
    service, run_id, evidence_id = _prepared_service(
        tmp_path,
        mode=DataMode.OFFICIAL_ONLY,
    )
    answer = "合成責任法第1條規定，行為人應負合成責任。"
    result = service.validate_answer(
        run_id,
        answer,
        "validate-conditional",
        claim_bindings=[
            {
                "claim_id": "claim-1",
                "claim_text": answer,
                "claim_type": "law_rule",
                "evidence_ids": [evidence_id],
            }
        ],
        now=NOW,
    )
    assert result["decision"] == "qualified"
    assert result["decision"] != "validated"
    assert result["schema_version"] == "alr-tw.answer-validation/v4"
    assert isinstance(result["required_qualification"], list)
    assert result["finalization"]["answer_mode"] == "conditional"


def test_refusal_does_not_echo_draft_and_operation_replay_is_idempotent(tmp_path: Path):
    service, run_id, _ = _prepared_service(tmp_path, ready=False)
    secret_draft = "這是不可回傳的 client 草稿"
    result = service.validate_answer(run_id, secret_draft, "validate-refusal", now=NOW)
    encoded = json.dumps(result, ensure_ascii=False)
    assert result["decision"] == "blocked"
    assert result["answer_text"] is None
    assert result["structured_refusal"]["answer_mode"] == "refusal_only"
    assert result["schema_version"] == "alr-tw.answer-validation/v4"
    assert isinstance(result["required_qualification"], list)
    assert secret_draft not in encoded

    replay = service.validate_answer(run_id, "另一份草稿", "validate-refusal", now=NOW)
    assert replay == result
    persisted = service.get_run(run_id)
    assert persisted is not None
    assert persisted.state is ResearchState.PLANNING
    assert persisted.obligations[-1].kind.value == "final_answer_validation"
    assert persisted.obligations[-1].status is ResearchObligationStatus.PENDING


def test_synthetic_evidence_shaped_records_still_refuse_answer(tmp_path: Path):
    service, run_id, evidence_id = _prepared_service(tmp_path, mode=DataMode.SYNTHETIC)
    draft = "合成資料看似官方，但不得支撐法律答案。"
    result = service.validate_answer(
        run_id,
        draft,
        "validate-synthetic-evidence",
        claim_bindings=[
            {
                "claim_id": "claim-synthetic",
                "claim_text": draft,
                "claim_type": "law_rule",
                "evidence_ids": [evidence_id],
            }
        ],
        now=NOW,
    )
    assert result["decision"] == "blocked"
    assert result["decision_code"] == "ANSWER_REFUSAL_ONLY"
    assert result["binding_mode"] == "not_executed"
    assert result["answer_text"] is None
    assert "RESEARCH_INSUFFICIENT" in result["blockers"]
    assert draft not in json.dumps(result, ensure_ascii=False)

def test_non_retryable_ready_refusal_transitions_and_completes_final_obligation(
    tmp_path: Path,
):
    service = ResearchService(SqliteStore(tmp_path / "cache"))
    run = service.create_run(
        "沒有證據的合成研究",
        mode=DataMode.SYNTHETIC,
        depth=ResearchDepth.QUICK,
        include_counter_authority=False,
        now=NOW,
    )
    completed = [
        item.model_copy(update={"status": ResearchObligationStatus.COMPLETED})
        for item in run.obligations
    ]
    run = run.model_copy(
        update={
            "state": ResearchState.READY_FOR_DRAFT,
            "obligations": completed,
            "coverage": run.coverage.model_copy(
                update={
                    "law_checked": True,
                    "time_context_checked": True,
                    "coverage_complete": True,
                }
            ),
        }
    )
    service.store.save_run(run)
    run_id = run.run_id
    result = service.validate_answer(run_id, "不應回傳的草稿", "validate-terminal", now=NOW)
    assert result["decision"] == "blocked"
    assert result["structured_refusal"]["answer_mode"] == "refusal_only"
    persisted = service.get_run(run_id)
    assert persisted is not None
    assert persisted.state is ResearchState.BLOCKED
    assert persisted.obligations[-1].status is ResearchObligationStatus.COMPLETED


def test_terminal_refusal_preserves_ephemeral_purge_semantics(tmp_path: Path):
    service = ResearchService(SqliteStore(tmp_path / "cache"))
    run = service.create_run(
        "沒有證據的暫存研究",
        mode=DataMode.SYNTHETIC,
        depth=ResearchDepth.QUICK,
        include_counter_authority=False,
        ephemeral=True,
        now=NOW,
    )
    run = run.model_copy(
        update={
            "state": ResearchState.READY_FOR_DRAFT,
            "obligations": [
                item.model_copy(update={"status": ResearchObligationStatus.COMPLETED})
                for item in run.obligations
            ],
            "coverage": run.coverage.model_copy(
                update={
                    "law_checked": True,
                    "time_context_checked": True,
                    "coverage_complete": True,
                }
            ),
        }
    )
    service.store.save_run(run)
    result = service.validate_answer(run.run_id, "不可回傳的暫存草稿", "validate-purge", now=NOW)
    assert result["decision"] == "blocked"
    assert result["storage_purged"] is True
    assert service.get_run(run.run_id) is None


def test_retryable_or_not_ready_refusal_does_not_purge_ephemeral_run(tmp_path: Path):
    service, run_id, _ = _prepared_service(tmp_path, ready=False)
    run = service.get_run(run_id)
    assert run is not None
    service.store.save_run(run.model_copy(update={"ephemeral": True}))
    result = service.validate_answer(run_id, "可重試的草稿", "validate-retry", now=NOW)
    assert result["decision"] == "blocked"
    assert "storage_purged" not in result
    assert service.get_run(run_id) is not None


def test_retryable_ready_refusal_does_not_purge_ephemeral_run(tmp_path: Path):
    service, run_id, _ = _prepared_service(tmp_path, mode=DataMode.OFFICIAL_ONLY)
    run = service.get_run(run_id)
    assert run is not None
    service.store.save_run(
        run.model_copy(
            update={
                "ephemeral": True,
                "coverage": run.coverage.model_copy(
                    update={"timeout_reason_codes": ["OFFICIAL_PROVIDER_TIMEOUT"]}
                ),
            }
        )
    )
    result = service.validate_answer(run_id, "可重試的草稿", "validate-ready-retry", now=NOW)
    assert result["decision"] == "blocked"
    assert result["finalization"]["retryable"] is True
    assert "storage_purged" not in result
    persisted = service.get_run(run_id)
    assert persisted is not None
    assert persisted.state is ResearchState.READY_FOR_DRAFT


def test_state_not_ready_uses_validated_blocker_and_keeps_workflow_open(
    tmp_path: Path,
):
    service, run_id, _ = _prepared_service(tmp_path, mode=DataMode.OFFICIAL_ONLY)
    run = service.get_run(run_id)
    assert run is not None
    obligations = [
        item.model_copy(update={"status": ResearchObligationStatus.COMPLETED})
        for item in run.obligations
    ]
    run = run.model_copy(
        update={
            "state": ResearchState.PLANNING,
            "obligations": obligations,
        }
    )
    service.store.save_run(run)

    result = service.validate_answer(run_id, "不可回傳的草稿", "validate-not-ready", now=NOW)
    assert result["decision"] == "blocked"
    assert "RESEARCH_OBLIGATION_PENDING" in result["blockers"]
    assert "RESEARCH_OBLIGATION_PENDING" in result["structured_refusal"]["reason_codes"]
    persisted = service.get_run(run_id)
    assert persisted is not None
    assert persisted.state is ResearchState.PLANNING
    assert persisted.obligations[-1].status is ResearchObligationStatus.COMPLETED


def test_get_state_separates_sufficiency_from_finalization_answer_mode(tmp_path: Path):
    service, run_id, _ = _prepared_service(tmp_path, mode=DataMode.OFFICIAL_ONLY)
    state = service.get_state(run_id)
    assert state["research_answer_mode"] == "ordinary"
    assert state["answer_mode"] == "conditional"
    assert state["answer_mode"] == state["finalization"]["answer_mode"]


def test_mcp_exposes_server_finalization_tool(tmp_path: Path):
    service, run_id, _ = _prepared_service(tmp_path, mode=DataMode.OFFICIAL_ONLY)
    session = McpSession(ready=True, research_service=service)
    names = {item["name"] for item in tool_definitions()}
    assert "get_legal_research_finalization" in names
    response = session.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "get_legal_research_finalization",
                "arguments": {"run_id": run_id},
            },
        }
    )
    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["data"]["answer_mode"] == "conditional"
