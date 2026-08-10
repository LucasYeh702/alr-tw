from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json

import pytest

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
    evaluate_research_sufficiency,
)


def _run(
    *,
    coverage: CoverageState,
    evidence_ids: list[str] | None = None,
    obligations: list[ResearchObligation] | None = None,
    state: ResearchState = ResearchState.READY_FOR_DRAFT,
) -> ResearchRun:
    now = datetime(2026, 8, 8, tzinfo=UTC)
    return ResearchRun(
        run_id="run-v080",
        query="示範法第1條",
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=1),
        requested_mode=DataMode.OFFICIAL_ONLY,
        effective_mode=DataMode.OFFICIAL_ONLY,
        research_depth=ResearchDepth.QUICK,
        privacy_status=PrivacyStatus.NOT_REQUIRED,
        state=state,
        obligations=obligations
        or [
            ResearchObligation(
                kind=ResearchObligationKind.LAW_RESEARCH,
                status=ResearchObligationStatus.COMPLETED,
            ),
            ResearchObligation(
                kind=ResearchObligationKind.EVIDENCE_SUFFICIENCY,
                status=ResearchObligationStatus.COMPLETED,
            ),
            ResearchObligation(kind=ResearchObligationKind.FINAL_ANSWER_VALIDATION),
        ],
        coverage=coverage,
        evidence_ids=evidence_ids or [],
    )


def test_complete_server_evidence_is_sufficient_and_ordinary() -> None:
    run = _run(
        evidence_ids=["evidence-law-1"],
        coverage=CoverageState(law_checked=True, coverage_complete=True),
    )

    assessment = evaluate_research_sufficiency(run)

    assert assessment.workflow_complete is True
    assert assessment.research_sufficiency is ResearchSufficiency.SUFFICIENT
    assert assessment.answer_mode is AnswerMode.ORDINARY


def test_synthetic_mode_refuses_even_evidence_shaped_ids() -> None:
    run = _run(
        evidence_ids=["evidence-that-looks-live"],
        coverage=CoverageState(law_checked=True, coverage_complete=True),
    ).model_copy(
        update={
            "requested_mode": DataMode.SYNTHETIC,
            "effective_mode": DataMode.SYNTHETIC,
        }
    )

    assessment = evaluate_research_sufficiency(run)

    assert assessment.research_sufficiency is ResearchSufficiency.INSUFFICIENT
    assert assessment.answer_mode is AnswerMode.REFUSAL_ONLY
    assert "SYNTHETIC_MODE_NO_LIVE_EVIDENCE" in assessment.reason_codes


def test_partial_coverage_is_qualified_and_conditional() -> None:
    run = _run(
        evidence_ids=["evidence-law-1"],
        coverage=CoverageState(
            law_checked=True,
            partial_reason_codes=["JUDGMENT_VERIFICATION_BUDGET_TRUNCATED"],
        ),
    )

    assessment = evaluate_research_sufficiency(run)

    assert assessment.research_sufficiency is ResearchSufficiency.QUALIFIED
    assert assessment.answer_mode is AnswerMode.CONDITIONAL


def test_counter_authority_gap_is_soft_when_primary_law_evidence_exists() -> None:
    run = _run(
        evidence_ids=["evidence-law-1"],
        obligations=[
            ResearchObligation(
                kind=ResearchObligationKind.LAW_RESEARCH,
                status=ResearchObligationStatus.COMPLETED,
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
        ],
        coverage=CoverageState(
            law_checked=True,
            limitations=["COUNTER_AUTHORITY_SEARCH_NOT_IMPLEMENTED"],
        ),
    )

    assessment = evaluate_research_sufficiency(run)

    assert assessment.research_sufficiency is ResearchSufficiency.QUALIFIED
    assert assessment.answer_mode is AnswerMode.CONDITIONAL
    assert "SOFT_COVERAGE_MISSING:counter_authority" in assessment.reason_codes


def test_scoped_counter_miss_remains_conditional_not_sufficient() -> None:
    run = _run(
        evidence_ids=["evidence-law-1"],
        obligations=[
            ResearchObligation(
                kind=ResearchObligationKind.LAW_RESEARCH,
                status=ResearchObligationStatus.COMPLETED,
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
        ],
        coverage=CoverageState(
            law_checked=True,
            counter_authority_checked=True,
            partial_reason_codes=["COUNTER_AUTHORITY_NOT_FOUND_IN_SCOPE"],
            bounded_query_scope="counter-plan-1",
        ),
    )

    assessment = evaluate_research_sufficiency(run)

    assert assessment.research_sufficiency is ResearchSufficiency.QUALIFIED
    assert assessment.answer_mode is AnswerMode.CONDITIONAL
    assert assessment.research_sufficiency is not ResearchSufficiency.SUFFICIENT


def test_required_official_judgment_verification_gap_is_refusal() -> None:
    run = _run(
        evidence_ids=["evidence-law-1"],
        obligations=[
            ResearchObligation(
                kind=ResearchObligationKind.LAW_RESEARCH,
                status=ResearchObligationStatus.COMPLETED,
            ),
            ResearchObligation(
                kind=ResearchObligationKind.JUDGMENT_RECALL,
                status=ResearchObligationStatus.COMPLETED,
            ),
            ResearchObligation(
                kind=ResearchObligationKind.JUDGMENT_OFFICIAL_VERIFICATION,
                status=ResearchObligationStatus.COMPLETED,
            ),
            ResearchObligation(
                kind=ResearchObligationKind.EVIDENCE_SUFFICIENCY,
                status=ResearchObligationStatus.COMPLETED,
            ),
            ResearchObligation(kind=ResearchObligationKind.FINAL_ANSWER_VALIDATION),
        ],
        coverage=CoverageState(law_checked=True, judgment_checked=True),
    ).model_copy(update={"judgment_recall_incomplete": True})

    assessment = evaluate_research_sufficiency(run)

    assert assessment.research_sufficiency is ResearchSufficiency.INSUFFICIENT
    assert assessment.answer_mode is AnswerMode.REFUSAL_ONLY
    assert "REQUIRED_COVERAGE_INCOMPLETE:judgment_official_verification" in assessment.reason_codes


def test_explicit_historical_version_gap_is_refusal() -> None:
    run = _run(
        evidence_ids=["evidence-law-1"],
        obligations=[
            ResearchObligation(
                kind=ResearchObligationKind.LAW_RESEARCH,
                status=ResearchObligationStatus.COMPLETED,
            ),
            ResearchObligation(
                kind=ResearchObligationKind.LEGAL_TIME_CONTEXT,
                status=ResearchObligationStatus.COMPLETED,
            ),
            ResearchObligation(
                kind=ResearchObligationKind.EVIDENCE_SUFFICIENCY,
                status=ResearchObligationStatus.COMPLETED,
            ),
            ResearchObligation(kind=ResearchObligationKind.FINAL_ANSWER_VALIDATION),
        ],
        coverage=CoverageState(
            law_checked=True,
            time_context_checked=True,
            limitations=["HISTORICAL_LAW_VERSION_UNSUPPORTED"],
        ),
    )

    assessment = evaluate_research_sufficiency(run)

    assert assessment.research_sufficiency is ResearchSufficiency.INSUFFICIENT
    assert assessment.answer_mode is AnswerMode.REFUSAL_ONLY
    assert "REQUIRED_COVERAGE_INCOMPLETE:legal_time_context" in assessment.reason_codes


def test_retryable_provider_error_never_becomes_sufficient() -> None:
    run = _run(
        evidence_ids=["evidence-law-1"],
        coverage=CoverageState(
            law_checked=True,
            error_reason_codes=["OFFICIAL_SOURCE_UNAVAILABLE"],
        ),
    )

    assessment = evaluate_research_sufficiency(run)

    assert assessment.research_sufficiency is ResearchSufficiency.RETRY_REQUIRED
    assert assessment.answer_mode is AnswerMode.REFUSAL_ONLY
    assert any("RETRY_REQUIRED" in reason for reason in assessment.reason_codes)


def test_missing_server_evidence_is_insufficient_and_refusal_only() -> None:
    run = _run(coverage=CoverageState(law_checked=False))

    assessment = evaluate_research_sufficiency(run)

    assert assessment.research_sufficiency is ResearchSufficiency.INSUFFICIENT
    assert assessment.answer_mode is AnswerMode.REFUSAL_ONLY
    assert "NO_SERVER_VERIFIED_EVIDENCE" in assessment.reason_codes


def test_legacy_ready_payload_hydrates_workflow_but_not_sufficiency() -> None:
    run = _run(coverage=CoverageState(law_checked=True), state=ResearchState.READY_FOR_DRAFT)
    payload = run.model_dump(mode="json")
    payload.pop("workflow_complete")
    payload.pop("research_sufficiency")
    payload.pop("answer_mode")
    payload["coverage"].pop("coverage_complete")
    payload["coverage"].pop("absence_claim_allowed")
    restored = ResearchRun.model_validate_json(json.dumps(payload))

    assert restored.workflow_complete is True
    assessment = evaluate_research_sufficiency(restored)
    assert assessment.research_sufficiency is ResearchSufficiency.INSUFFICIENT
    assert assessment.answer_mode is AnswerMode.REFUSAL_ONLY


def test_early_blocked_payload_is_not_marked_workflow_complete() -> None:
    run = _run(
        coverage=CoverageState(),
        state=ResearchState.BLOCKED,
        obligations=[
            ResearchObligation(kind=ResearchObligationKind.LAW_RESEARCH),
            ResearchObligation(kind=ResearchObligationKind.FINAL_ANSWER_VALIDATION),
        ],
    )

    assert run.workflow_complete is False
    assert evaluate_research_sufficiency(run).workflow_complete is False


def test_absence_claim_is_fail_closed_by_default() -> None:
    coverage = CoverageState(law_checked=True, coverage_complete=True)

    assert coverage.absence_claim_allowed is False


def test_absence_claim_requires_bounded_counter_scope_and_successful_providers() -> None:
    with pytest.raises(ValueError, match="counter-authority coverage"):
        CoverageState(coverage_complete=True, absence_claim_allowed=True)

    with pytest.raises(ValueError, match="bounded query scope"):
        CoverageState(
            coverage_complete=True,
            absence_claim_allowed=True,
            counter_authority_checked=True,
        )

    with pytest.raises(ValueError, match="bounded query scope"):
        CoverageState(
            coverage_complete=True,
            absence_claim_allowed=True,
            counter_authority_checked=True,
            bounded_query_scope="   ",
        )

    with pytest.raises(ValueError, match="provider scope identifiers"):
        CoverageState(
            coverage_complete=True,
            absence_claim_allowed=True,
            counter_authority_checked=True,
            bounded_query_scope="provider=official;max_queries=3",
            selected_provider_scope=["   "],
            successful_provider_scope=["   "],
        )

    with pytest.raises(ValueError, match="provider scope identifiers"):
        CoverageState(
            coverage_complete=True,
            absence_claim_allowed=True,
            counter_authority_checked=True,
            bounded_query_scope="provider=official;max_queries=3",
            selected_provider_scope=[" official-judi"],
            successful_provider_scope=[" official-judi"],
        )

    with pytest.raises(ValueError, match="successful selected provider scope"):
        CoverageState(
            coverage_complete=True,
            absence_claim_allowed=True,
            counter_authority_checked=True,
            bounded_query_scope="provider=official;max_queries=3",
            selected_provider_scope=["official-judi"],
        )

    valid = CoverageState(
        coverage_complete=True,
        absence_claim_allowed=True,
        counter_authority_checked=True,
        bounded_query_scope="provider=official;max_queries=3",
        selected_provider_scope=["official-judi"],
        successful_provider_scope=["official-judi"],
    )
    assert valid.absence_claim_allowed is True


def test_absence_claim_cannot_override_scope_limitations() -> None:
    with pytest.raises(ValueError, match="absence_claim_allowed"):
        CoverageState(
            coverage_complete=True,
            absence_claim_allowed=True,
            limitations=["NOT_FOUND_IN_SCOPE"],
        )


def test_caller_supplied_sufficiency_is_ignored_by_evaluator() -> None:
    run = _run(coverage=CoverageState(), evidence_ids=[]).model_copy(
        update={
            "research_sufficiency": ResearchSufficiency.SUFFICIENT,
            "answer_mode": AnswerMode.ORDINARY,
            "workflow_complete": True,
        }
    )

    assessment = evaluate_research_sufficiency(run)

    assert assessment.research_sufficiency is ResearchSufficiency.INSUFFICIENT
    assert assessment.answer_mode is AnswerMode.REFUSAL_ONLY


def test_nonretryable_blocked_required_obligation_is_insufficient() -> None:
    run = _run(
        coverage=CoverageState(),
        obligations=[
            ResearchObligation(
                kind=ResearchObligationKind.LAW_RESEARCH,
                status=ResearchObligationStatus.BLOCKED,
                reason="privacy policy blocked external query",
                blocker_code="PRIVACY_EXTERNAL_QUERY_BLOCKED",
            ),
            ResearchObligation(kind=ResearchObligationKind.FINAL_ANSWER_VALIDATION),
        ],
        state=ResearchState.RESEARCHING,
    )

    assessment = evaluate_research_sufficiency(run)

    assert assessment.research_sufficiency is ResearchSufficiency.INSUFFICIENT
    assert assessment.answer_mode is AnswerMode.REFUSAL_ONLY
    assert "RESEARCH_REQUIRED_OBLIGATION_BLOCKED" in assessment.reason_codes
    assert "NON_RETRYABLE_BLOCKED:law_research" in assessment.reason_codes


def test_retryable_blocked_required_obligation_requires_retry() -> None:
    run = _run(
        coverage=CoverageState(),
        obligations=[
            ResearchObligation(
                kind=ResearchObligationKind.LAW_RESEARCH,
                status=ResearchObligationStatus.BLOCKED,
                reason="temporary provider unavailable",
                blocker_code="OFFICIAL_SOURCE_UNAVAILABLE",
            ),
            ResearchObligation(kind=ResearchObligationKind.FINAL_ANSWER_VALIDATION),
        ],
        state=ResearchState.RESEARCHING,
    )

    assessment = evaluate_research_sufficiency(run)

    assert assessment.research_sufficiency is ResearchSufficiency.RETRY_REQUIRED
    assert assessment.answer_mode is AnswerMode.REFUSAL_ONLY
    assert "RETRY_REQUIRED:law_research" in assessment.reason_codes


def test_timeout_coverage_requires_retry() -> None:
    run = _run(
        evidence_ids=["evidence-law-1"],
        coverage=CoverageState(
            law_checked=True,
            timeout_reason_codes=["OFFICIAL_LOOKUP_TIMEOUT"],
        ),
    )

    assessment = evaluate_research_sufficiency(run)

    assert assessment.research_sufficiency is ResearchSufficiency.RETRY_REQUIRED
    assert assessment.answer_mode is AnswerMode.REFUSAL_ONLY
    assert "RETRY_REQUIRED:OFFICIAL_LOOKUP_TIMEOUT" in assessment.reason_codes
