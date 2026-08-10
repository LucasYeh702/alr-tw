from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from alr_tw.contracts.finalization import (
    AbsenceClaimGate,
    CounterAuthorityGate,
    FinalizationContract,
    FinalizationValidationResult,
    build_finalization_contract,
    build_finalization_from_run,
    build_structured_refusal,
    validate_finalization,
)
from alr_tw.contracts.provider_snapshot import (
    ProviderSnapshotReceipt,
    SnapshotConsistency,
    SnapshotConsistencyResult,
)
from alr_tw.contracts.providers import DataMode
from alr_tw.contracts.research import (
    AnswerMode,
    CoverageState,
    PrivacyStatus,
    ResearchDepth,
    ResearchObligation,
    ResearchObligationKind,
    ResearchObligationStatus,
    ResearchRun,
    ResearchState,
    ResearchSufficiency,
)


NOW = datetime(2026, 8, 8, 8, 0, tzinfo=UTC)


def _receipt(
    receipt_id: str = "receipt-1",
    *,
    snapshot_id: str = "snapshot-1",
    generation: str = "generation-1",
) -> ProviderSnapshotReceipt:
    return ProviderSnapshotReceipt(
        receipt_id=receipt_id,
        provider_id="official-law",
        snapshot_id=snapshot_id,
        generation=generation,
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


def _ordinary(**kwargs):
    receipt = kwargs.pop("receipt", _receipt())
    defaults = {
        "run_id": "run-1",
        "workflow_complete": True,
        "research_sufficiency": ResearchSufficiency.SUFFICIENT,
        "allowed_source_ids": ["source-1"],
        "allowed_evidence_ids": ["evidence-1"],
        "server_source_ids": ["source-1"],
        "server_evidence_ids": ["evidence-1"],
        "coverage_complete": True,
        "time_context_complete": True,
        "authority_complete": True,
        "required_evidence_available": True,
        "counter_authority": CounterAuthorityGate(
            required=True,
            coverage_complete=True,
            # Bounded counter-authority coverage cannot certify global
            # consensus; this run does not request such a claim.
            consensus_claim_allowed=False,
        ),
        "absence_claim": AbsenceClaimGate(
            requested=False,
            allowed=False,
            reason_codes=["ABSENCE_CLAIM_NOT_ESTABLISHED"],
        ),
        "snapshot_receipts": [receipt],
        "server_snapshot_receipts": [receipt],
        "answer_draft": "合成答案。",
        "claim_support_summary": {"semantic_safe_to_present": True},
        "privacy_allowed": True,
        "now": NOW,
    }
    defaults.update(kwargs)
    return build_finalization_contract(**defaults)


def _server_run(*, pending_law: bool = False) -> ResearchRun:
    obligations = [
        ResearchObligation(
            kind=ResearchObligationKind.LAW_RESEARCH,
            status=(
                ResearchObligationStatus.PENDING
                if pending_law
                else ResearchObligationStatus.COMPLETED
            ),
        ),
        ResearchObligation(
            kind=ResearchObligationKind.COUNTER_AUTHORITY,
            status=ResearchObligationStatus.COMPLETED,
        ),
        ResearchObligation(
            kind=ResearchObligationKind.EVIDENCE_SUFFICIENCY,
            status=ResearchObligationStatus.COMPLETED,
        ),
        ResearchObligation(kind=ResearchObligationKind.FINAL_ANSWER_VALIDATION),
    ]
    now = NOW
    return ResearchRun(
        run_id="run-1",
        query="示範法第1條",
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=1),
        requested_mode=DataMode.OFFICIAL_ONLY,
        effective_mode=DataMode.OFFICIAL_ONLY,
        research_depth=ResearchDepth.QUICK,
        include_counter_authority=True,
        privacy_status=PrivacyStatus.NOT_REQUIRED,
        state=ResearchState.READY_FOR_DRAFT,
        obligations=obligations,
        coverage=CoverageState(
            law_checked=not pending_law,
            counter_authority_checked=True,
            time_context_checked=True,
            coverage_complete=not pending_law,
        ),
        source_ids=["source-1"],
        evidence_ids=["evidence-1"],
    )


def test_ordinary_requires_all_server_gates_and_receipt():
    contract = _ordinary()
    assert contract.answer_mode is AnswerMode.ORDINARY
    result = validate_finalization(
        contract,
        server_run_id="run-1",
        server_source_ids=["source-1"],
        server_evidence_ids=["evidence-1"],
        server_snapshot_receipts=contract.snapshot_receipts,
        server_run=_server_run(),
        now=NOW,
    )
    assert result.valid
    assert result.safe_to_draft
    assert result.safe_to_present is False
    # Finalization is a pre-draft posture; legacy answer_draft input is
    # discarded and never returned by the validator.
    assert result.answer_draft is None


def test_incomplete_coverage_is_conditional_not_ordinary():
    contract = _ordinary(coverage_complete=False)
    assert contract.answer_mode is AnswerMode.CONDITIONAL
    assert contract.required_qualification
    result = validate_finalization(
        contract,
        server_run_id="run-1",
        server_source_ids=["source-1"],
        server_evidence_ids=["evidence-1"],
        server_snapshot_receipts=contract.snapshot_receipts,
        server_run=_server_run(),
        now=NOW,
    )
    assert result.valid
    assert result.answer_mode is AnswerMode.CONDITIONAL
    assert result.safe_to_draft
    assert result.safe_to_present is False


def test_counter_authority_incomplete_disallows_consensus_but_can_be_conditional():
    contract = _ordinary(
        counter_authority=CounterAuthorityGate(
            required=True,
            coverage_complete=False,
            consensus_claim_allowed=False,
        )
    )
    assert contract.answer_mode is AnswerMode.CONDITIONAL
    assert any("反向" in item for item in contract.required_qualification)


def test_bounded_counter_coverage_allows_non_consensus_ordinary_answer():
    contract = _ordinary(
        counter_authority=CounterAuthorityGate(
            required=True,
            coverage_complete=True,
            consensus_claim_requested=False,
            consensus_claim_allowed=False,
        )
    )
    assert contract.answer_mode is AnswerMode.ORDINARY


def test_global_consensus_request_is_not_authorized_by_bounded_coverage():
    contract = _ordinary(
        counter_authority=CounterAuthorityGate(
            required=True,
            coverage_complete=True,
            consensus_claim_requested=True,
            consensus_claim_allowed=False,
        )
    )
    assert contract.answer_mode is AnswerMode.CONDITIONAL
    assert any("一致" in item for item in contract.required_qualification)


def test_consensus_authority_flag_is_fixed_closed_in_v080_contract():
    with pytest.raises(ValidationError):
        CounterAuthorityGate(
            required=True,
            coverage_complete=True,
            consensus_claim_allowed=True,
        )


def test_absence_claim_denied_is_conditional_and_never_authorized():
    contract = _ordinary(
        absence_claim=AbsenceClaimGate(
            requested=True,
            allowed=False,
            reason_codes=["NOT_FOUND_IN_SCOPE"],
        )
    )
    assert contract.answer_mode is AnswerMode.CONDITIONAL
    assert any("不存在" in item for item in contract.required_qualification)


def test_absence_gate_can_be_available_without_an_absence_claim_request():
    contract = _ordinary(
        absence_claim=AbsenceClaimGate(
            requested=False,
            allowed=True,
            scope="本次法規／裁判搜尋範圍",
        ),
    )
    assert contract.answer_mode is AnswerMode.ORDINARY
    assert contract.absence_claim.requested is False
    assert contract.absence_claim.allowed is True


def test_absence_authority_requires_bounded_scope():
    with pytest.raises(ValidationError):
        AbsenceClaimGate(requested=False, allowed=True)


def test_builder_carries_bounded_absence_scope_from_server_run():
    run = _server_run()
    coverage = run.coverage.model_copy(
        update={
            "absence_claim_allowed": True,
            "bounded_query_scope": "官方法規與裁判搜尋範圍",
        }
    )
    run = run.model_copy(update={"coverage": coverage})
    contract = build_finalization_from_run(run, now=NOW)
    assert contract.absence_claim.allowed is True
    assert contract.absence_claim.scope == "官方法規與裁判搜尋範圍"


def test_insufficient_research_is_structured_refusal_without_draft():
    contract = _ordinary(
        workflow_complete=False,
        research_sufficiency=ResearchSufficiency.INSUFFICIENT,
        answer_draft="不得洩漏的草稿",
    )
    assert contract.answer_mode is AnswerMode.REFUSAL_ONLY
    assert contract.answer_draft is None
    refusal = build_structured_refusal(contract)
    assert refusal.answer_mode == "refusal_only"
    assert refusal.reason_codes
    assert "answer_draft" not in refusal.model_dump()


def test_foreign_evidence_is_blocked_and_answer_draft_is_removed():
    contract = _ordinary(allowed_evidence_ids=["foreign-evidence"])
    assert contract.answer_mode is AnswerMode.REFUSAL_ONLY
    result = validate_finalization(
        contract,
        server_run_id="run-1",
        server_source_ids=["source-1"],
        server_evidence_ids=["evidence-1"],
        server_snapshot_receipts=contract.snapshot_receipts,
        server_run=_server_run(),
        now=NOW,
    )
    assert not result.valid
    assert not result.safe_to_present
    assert result.answer_draft is None
    assert any(item.code == "FINALIZATION_EVIDENCE_NOT_SERVER_OWNED" for item in result.blockers)


def test_presentable_contract_without_server_refs_or_facts_fails_closed():
    # This mirrors the trust-bypass report: a caller cannot make a
    # conditional draft presentable by self-declaring sufficiency and a
    # qualification while omitting all server-owned bindings.
    contract = FinalizationContract(
        run_id="run-x",
        research_schema_version="alr-tw.research-run/v1",
        workflow_complete=True,
        research_sufficiency=ResearchSufficiency.QUALIFIED,
        answer_mode=AnswerMode.CONDITIONAL,
        required_qualification=["有限制"],
        answer_draft="無證據答案",
    )
    result = validate_finalization(
        contract,
        server_run_id="run-x",
        server_source_ids=[],
        server_evidence_ids=[],
        server_snapshot_receipts=[],
        now=NOW,
    )
    assert not result.valid
    assert not result.safe_to_present
    assert result.answer_mode is AnswerMode.REFUSAL_ONLY
    assert result.answer_draft is None
    assert {
        "FINALIZATION_SERVER_EVIDENCE_REQUIRED",
        "FINALIZATION_SERVER_FACTS_REQUIRED",
    }.issubset({item.code for item in result.blockers})


def test_builder_without_explicit_server_binding_cannot_return_presentable_posture():
    receipt = _receipt()
    contract = build_finalization_contract(
        run_id="run-1",
        workflow_complete=True,
        research_sufficiency=ResearchSufficiency.SUFFICIENT,
        allowed_source_ids=["source-1"],
        allowed_evidence_ids=["evidence-1"],
        coverage_complete=True,
        time_context_complete=True,
        authority_complete=True,
        counter_authority=CounterAuthorityGate(
            required=True,
            coverage_complete=True,
        ),
        absence_claim=AbsenceClaimGate(
            requested=False,
            allowed=False,
            reason_codes=["ABSENCE_CLAIM_NOT_ESTABLISHED"],
        ),
        snapshot_receipts=[receipt],
        server_snapshot_receipts=[receipt],
        answer_draft="不得直接呈現",
        now=NOW,
    )
    assert contract.answer_mode is AnswerMode.REFUSAL_ONLY
    assert any(
        item.code == "FINALIZATION_SERVER_BINDING_REQUIRED"
        for item in contract.blockers
    )
    assert contract.answer_draft is None


def test_server_refs_without_contract_bindings_cannot_authorize_draft():
    contract = FinalizationContract(
        run_id="run-1",
        research_schema_version="alr-tw.research-run/v1",
        workflow_complete=True,
        research_sufficiency=ResearchSufficiency.QUALIFIED,
        answer_mode=AnswerMode.CONDITIONAL,
        required_qualification=["有限制"],
        answer_draft="無證據答案",
    )
    result = validate_finalization(
        contract,
        server_run_id="run-1",
        server_source_ids=["source-1"],
        server_evidence_ids=["evidence-1"],
        server_snapshot_receipts=[],
        server_run=_server_run(),
        now=NOW,
    )
    assert not result.valid
    assert not result.safe_to_present
    assert result.answer_draft is None
    assert any(
        item.code == "FINALIZATION_SERVER_EVIDENCE_REQUIRED"
        for item in result.blockers
    )


def test_forged_workflow_and_sufficiency_cannot_bypass_server_run():
    contract = _ordinary()
    result = validate_finalization(
        contract,
        server_run_id="run-1",
        server_source_ids=["source-1"],
        server_evidence_ids=["evidence-1"],
        server_snapshot_receipts=contract.snapshot_receipts,
        server_run=_server_run(pending_law=True),
        now=NOW,
    )
    codes = {item.code for item in result.blockers}
    assert not result.valid
    assert not result.safe_to_present
    assert result.answer_draft is None
    assert {
        "FINALIZATION_WORKFLOW_FACTS_MISMATCH",
        "FINALIZATION_SUFFICIENCY_FACTS_MISMATCH",
        "FINALIZATION_SERVER_REFUSAL",
    }.issubset(codes)


def test_caller_draft_and_validator_flags_never_become_presentable_answer():
    base = _ordinary(coverage_complete=False)
    forged = base.model_copy(
        update={
            "answer_draft": "caller 偽造答案",
            "claim_support_summary": {"semantic_safe_to_present": True},
            "privacy_allowed": True,
        }
    )
    result = validate_finalization(
        forged,
        server_run_id="run-1",
        server_source_ids=["source-1"],
        server_evidence_ids=["evidence-1"],
        server_snapshot_receipts=base.snapshot_receipts,
        server_run=_server_run(),
        now=NOW,
    )
    assert not result.valid
    assert not result.safe_to_present
    assert result.answer_draft is None
    assert "FINALIZATION_DRAFT_NOT_ALLOWED" in {
        item.code for item in result.blockers
    }


def test_finalization_validation_result_cannot_authorize_presentation():
    with pytest.raises(ValidationError):
        FinalizationValidationResult(
            run_id="run-1",
            valid=True,
            answer_mode=AnswerMode.ORDINARY,
            safe_to_present=True,
            safe_to_draft=True,
            snapshot_consistency=SnapshotConsistencyResult(
                status=SnapshotConsistency.CONSISTENT,
                consistent=True,
                receipt_count=1,
            ),
        )


def test_forged_counter_and_absence_gates_cannot_bypass_server_run():
    forged_counter = CounterAuthorityGate(
        required=True,
        coverage_complete=True,
        consensus_claim_requested=False,
    ).model_copy(update={"consensus_claim_allowed": True})
    contract = _ordinary(
        absence_claim=AbsenceClaimGate(
            requested=False,
            allowed=True,
            scope="本次法規／裁判搜尋範圍",
        ),
    )
    # model_copy(update=...) simulates a forged post-validation payload; the
    # server comparison must still reject it.
    contract = contract.model_copy(update={"counter_authority": forged_counter})
    result = validate_finalization(
        contract,
        server_run_id="run-1",
        server_source_ids=["source-1"],
        server_evidence_ids=["evidence-1"],
        server_snapshot_receipts=contract.snapshot_receipts,
        server_run=_server_run(),
        now=NOW,
    )
    codes = {item.code for item in result.blockers}
    assert not result.valid
    assert not result.safe_to_present
    assert result.answer_draft is None
    assert "FINALIZATION_COUNTER_GATE_NOT_SERVER_OWNED" in codes
    assert "FINALIZATION_ABSENCE_GATE_NOT_SERVER_OWNED" in codes


def test_snapshot_mismatch_blocks_ordinary_finalization():
    first = _receipt()
    second = _receipt("receipt-2", snapshot_id="snapshot-2", generation="generation-2")
    contract = _ordinary(
        snapshot_receipts=[first, second],
        server_snapshot_receipts=[first, second],
    )
    assert contract.answer_mode is AnswerMode.REFUSAL_ONLY
    assert any(item.code == "SNAPSHOT_RECEIPT_MISMATCH" for item in contract.blockers)


def test_legacy_no_receipt_is_qualified_and_not_ordinary():
    contract = _ordinary(snapshot_receipts=[], server_snapshot_receipts=[])
    assert contract.answer_mode is AnswerMode.CONDITIONAL
    assert contract.snapshot_consistency is not None
    assert not contract.snapshot_consistency.consistent
    assert any("snapshot receipt" in item for item in contract.required_qualification)


def test_contract_rejects_draft_on_refusal_and_extra_client_proposal():
    refusal = FinalizationContract(
        run_id="run-1",
        research_schema_version="alr-tw.research-run/v1",
        workflow_complete=False,
        research_sufficiency=ResearchSufficiency.INSUFFICIENT,
        answer_mode=AnswerMode.REFUSAL_ONLY,
        blockers=["RESEARCH_INSUFFICIENT"],
        answer_draft="不得輸出的草稿",
    )
    assert refusal.answer_draft is None
    with pytest.raises(ValidationError):
        FinalizationContract(
            run_id="run-1",
            research_schema_version="alr-tw.research-run/v1",
            workflow_complete=False,
            research_sufficiency=ResearchSufficiency.INSUFFICIENT,
            answer_mode=AnswerMode.REFUSAL_ONLY,
            client_proposal={"trust_status": "untrusted_client_proposal"},
        )
