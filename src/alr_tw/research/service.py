"""Atomic server-owned research run service."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from threading import RLock
from typing import Any, Protocol
from uuid import uuid4

from alr_tw.contracts.providers import DataMode
from alr_tw.contracts.research import (
    CoverageState,
    PrivacyStatus,
    ResearchDepth,
    ResearchObligation,
    ResearchObligationKind,
    ResearchObligationStatus,
    ResearchRun,
    ResearchState,
)
from alr_tw.contracts.sources import EvidenceSectionType, EvidenceSpan, TrustStatus
from alr_tw.storage.sqlite_store import SqliteStore
from alr_tw.providers.tlr.privacy import screen_external_query
from alr_tw.verification.claim_support import (
    LegalSegment,
    SectionRole,
    check_claim_support,
    extract_answer_claims,
)

from .state_machine import transition_run


class ObligationExecutor(Protocol):
    def execute(
        self,
        run: ResearchRun,
        obligation: ResearchObligation,
    ) -> dict[str, Any]: ...


class SourceLookupExecutor(Protocol):
    def lookup(self, text: str, *, run_id: str | None = None) -> dict[str, Any]: ...


class SyntheticObligationExecutor:
    """Deterministic executor used before live providers are enabled."""

    def execute(
        self,
        run: ResearchRun,
        obligation: ResearchObligation,
    ) -> dict[str, Any]:
        del run
        return {
            "status": "completed",
            "obligation": obligation.kind.value,
            "provider_calls": [],
            "warnings": ["SYNTHETIC_MODE_NO_LIVE_EVIDENCE"],
        }


def _plan_obligations(
    query: str,
    *,
    mode: DataMode,
    depth: ResearchDepth,
    as_of_date: date | None,
    include_counter_authority: bool,
) -> list[ResearchObligation]:
    kinds = [ResearchObligationKind.QUERY_UNDERSTANDING]
    if mode == DataMode.HYBRID_VERIFIED:
        kinds.append(ResearchObligationKind.PRIVACY_SCREEN)
    kinds.append(ResearchObligationKind.LAW_RESEARCH)
    if depth in {ResearchDepth.STANDARD, ResearchDepth.DEEP}:
        kinds.extend(
            [
                ResearchObligationKind.JUDGMENT_RECALL,
                ResearchObligationKind.JUDGMENT_OFFICIAL_VERIFICATION,
            ]
        )
        if include_counter_authority:
            kinds.append(ResearchObligationKind.COUNTER_AUTHORITY)
    if any(token in query for token in ("憲法", "釋字", "憲判字", "基本權")):
        kinds.append(ResearchObligationKind.CONSTITUTIONAL_RESEARCH)
    if as_of_date is not None or any(token in query for token in ("修法前", "修法後", "當時")):
        kinds.append(ResearchObligationKind.LEGAL_TIME_CONTEXT)
    kinds.extend(
        [
            ResearchObligationKind.EVIDENCE_SUFFICIENCY,
            ResearchObligationKind.FINAL_ANSWER_VALIDATION,
        ]
    )
    return [ResearchObligation(kind=kind) for kind in kinds]


class ResearchService:
    def __init__(self, store: SqliteStore, executor: ObligationExecutor | None = None):
        self.store = store
        self.executor = executor or SyntheticObligationExecutor()
        self._lock = RLock()

    def create_run(
        self,
        query: str,
        *,
        mode: DataMode,
        depth: ResearchDepth = ResearchDepth.STANDARD,
        include_counter_authority: bool = True,
        ephemeral: bool = False,
        as_of_date: date | None = None,
        retention_seconds: int = 86400,
        now: datetime | None = None,
    ) -> ResearchRun:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query is required")
        timestamp = now or datetime.now(UTC)
        run = ResearchRun(
            run_id=f"run_{uuid4().hex}",
            query=normalized_query,
            created_at=timestamp,
            updated_at=timestamp,
            expires_at=timestamp + timedelta(seconds=retention_seconds),
            requested_mode=mode,
            effective_mode=mode,
            research_depth=depth,
            include_counter_authority=include_counter_authority,
            ephemeral=ephemeral,
            as_of_date=as_of_date,
            privacy_status=(
                PrivacyStatus.UNCERTAIN
                if mode == DataMode.HYBRID_VERIFIED
                else PrivacyStatus.NOT_REQUIRED
            ),
            state=ResearchState.PLANNING,
            obligations=_plan_obligations(
                normalized_query,
                mode=mode,
                depth=depth,
                as_of_date=as_of_date,
                include_counter_authority=include_counter_authority,
            ),
            coverage=CoverageState(),
        )
        self.store.save_run(run)
        return run

    def get_run(self, run_id: str) -> ResearchRun | None:
        return self.store.get_run(run_id)

    def get_state(self, run_id: str) -> dict[str, Any]:
        run = self._required_run(run_id)
        return {
            "schema_version": "alr-tw.research-state/v1",
            "run": run.model_dump(mode="json"),
            "source_count": len(self.store.list_sources(run_id)),
            "evidence_count": len(self.store.list_evidence(run_id)),
            "ready_for_draft": run.state == ResearchState.READY_FOR_DRAFT,
        }

    def lookup_source(
        self,
        text: str,
        *,
        run_id: str | None = None,
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        normalized = text.strip()
        if not normalized:
            raise ValueError("text is required")
        lookup = getattr(self.executor, "lookup", None)
        if not callable(lookup):
            return {
                "schema_version": "alr-tw.legal-source-lookup/v1",
                "status": "not_found",
                "error_code": "SYNTHETIC_LOOKUP_UNAVAILABLE",
                "claim_verified": False,
            }
        if run_id is None:
            return lookup(normalized, run_id=None)
        self._required_run(run_id)
        if operation_id is None:
            return lookup(normalized, run_id=run_id)
        claim = self.store.record_operation(run_id, operation_id, {"status": "in_progress"})
        if not claim.created:
            return claim.result
        result = lookup(normalized, run_id=run_id)
        self.store.complete_operation(run_id, operation_id, result)
        run = self._required_run(run_id)
        run = run.model_copy(
            update={
                "source_ids": sorted(item.source_id for item in self.store.list_sources(run_id)),
                "evidence_ids": sorted(item.evidence_id for item in self.store.list_evidence(run_id)),
            }
        )
        self.store.save_run(run)
        return result

    def continue_run(
        self,
        run_id: str,
        operation_id: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not operation_id.strip():
            raise ValueError("operation_id is required")
        with self._lock:
            run = self._required_run(run_id)
            timestamp = now or datetime.now(UTC)
            if run.expires_at <= timestamp:
                raise ValueError("RESEARCH_RUN_EXPIRED")
            claim = self.store.record_operation(
                run_id,
                operation_id,
                {"status": "in_progress"},
            )
            if not claim.created:
                return claim.result

            pending = [
                item
                for item in run.obligations
                if item.status == ResearchObligationStatus.PENDING
                and item.kind != ResearchObligationKind.FINAL_ANSWER_VALIDATION
            ]
            if not pending:
                result = self._result(run, None, replayed=False)
                self.store.complete_operation(run_id, operation_id, result)
                return result

            obligation = pending[0]
            if run.state == ResearchState.PLANNING:
                run = transition_run(run, ResearchState.RESEARCHING, updated_at=timestamp)
            outcome = self.executor.execute(run, obligation)
            run_updates = outcome.pop("_run_updates", {})
            if not isinstance(run_updates, dict):
                raise TypeError("executor _run_updates must be a dictionary")
            if run_updates:
                run = run.model_copy(update=run_updates)
            completed = obligation.model_copy(
                update={"status": ResearchObligationStatus.COMPLETED}
            )
            obligations = [completed if item.kind == obligation.kind else item for item in run.obligations]
            sources = self.store.list_sources(run_id)
            evidence = self.store.list_evidence(run_id)
            run = run.model_copy(
                update={
                    "obligations": obligations,
                    "updated_at": timestamp,
                    "source_ids": sorted(source.source_id for source in sources),
                    "evidence_ids": sorted(item.evidence_id for item in evidence),
                }
            )
            remaining = [
                item
                for item in obligations
                if item.status == ResearchObligationStatus.PENDING
                and item.kind != ResearchObligationKind.FINAL_ANSWER_VALIDATION
            ]
            if not remaining:
                run = transition_run(run, ResearchState.VERIFYING, updated_at=timestamp)
                run = transition_run(run, ResearchState.READY_FOR_DRAFT, updated_at=timestamp)
            elif obligation.kind in {
                ResearchObligationKind.JUDGMENT_OFFICIAL_VERIFICATION,
                ResearchObligationKind.EVIDENCE_SUFFICIENCY,
            } and run.state == ResearchState.RESEARCHING:
                run = transition_run(run, ResearchState.VERIFYING, updated_at=timestamp)
            self.store.save_run(run)
            result = self._result(run, outcome, replayed=False)
            self.store.complete_operation(run_id, operation_id, result)
            return result

    def validate_answer(
        self,
        run_id: str,
        answer_text: str,
        operation_id: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not answer_text.strip():
            raise ValueError("answer_text is required")
        with self._lock:
            run = self._required_run(run_id)
            timestamp = now or datetime.now(UTC)
            if run.expires_at <= timestamp:
                raise ValueError("RESEARCH_RUN_EXPIRED")
            if run.state != ResearchState.READY_FOR_DRAFT:
                raise ValueError("RESEARCH_OBLIGATION_PENDING")
            claim = self.store.record_operation(
                run_id,
                operation_id,
                {"status": "in_progress"},
            )
            if not claim.created:
                return claim.result
            run = transition_run(run, ResearchState.VALIDATING, updated_at=timestamp)
            sources = {source.source_id: source for source in self.store.list_sources(run_id)}
            evidence = self.store.list_evidence(run_id)
            eligible = [
                item
                for item in evidence
                if item.eligible_for_claim_support
                and item.source_id in sources
                and sources[item.source_id].trust_status == TrustStatus.EVIDENCE_ELIGIBLE
                and sources[item.source_id].expires_at > timestamp
            ]
            reasons_from_sources: list[str] = []
            if any(source.expires_at <= timestamp for source in sources.values()):
                reasons_from_sources.append("SOURCE_STALE")
            if sources and not eligible:
                reasons_from_sources.append("SOURCE_NOT_EVIDENCE_ELIGIBLE")
            claims = extract_answer_claims(answer_text)
            segments = [
                self._claim_segment(
                    item,
                    sources[item.source_id].source_tier.value,
                    sources[item.source_id].material_type.value,
                    sources[item.source_id].official_url,
                    sources[item.source_id].verified_at,
                )
                for item in eligible
            ]
            support, summary, reasons = check_claim_support(
                answer=answer_text,
                claims=claims,
                segments=segments,
            )
            reasons.extend(reasons_from_sources)
            if not claims:
                reasons.append("CLAIM_SUPPORT_NOT_CHECKED")
            answer_privacy = screen_external_query(answer_text)
            if answer_privacy.redactions or not answer_privacy.allowed:
                reasons.append("ANSWER_CONTAINS_SENSITIVE_DATA")
            if "HISTORICAL_LAW_VERSION_UNSUPPORTED" in run.coverage.limitations:
                reasons.append("HISTORICAL_LAW_VERSION_UNSUPPORTED")
            safe = bool(eligible) and summary.semantic_safe_to_present and not reasons
            if safe and (run.semantic_recall_degraded or run.judgment_recall_incomplete):
                decision = ResearchState.QUALIFIED
                qualification = "本次普通法院裁判盤點可能不完整，結論僅限已驗證來源。"
            elif safe:
                decision = ResearchState.VALIDATED
                qualification = None
            else:
                decision = ResearchState.BLOCKED
                qualification = None
            run = transition_run(run, decision, updated_at=timestamp)
            obligations = [
                item.model_copy(update={"status": ResearchObligationStatus.COMPLETED})
                if item.kind == ResearchObligationKind.FINAL_ANSWER_VALIDATION
                else item
                for item in run.obligations
            ]
            run = run.model_copy(update={"obligations": obligations})
            self.store.save_run(run)
            result = {
                "schema_version": "alr-tw.answer-validation/v2",
                "run_id": run_id,
                "decision": decision.value,
                "decision_code": (
                    "ANSWER_QUALIFIED"
                    if decision == ResearchState.QUALIFIED
                    else "ANSWER_BLOCKED"
                    if decision == ResearchState.BLOCKED
                    else None
                ),
                "safe_to_present": decision in {ResearchState.VALIDATED, ResearchState.QUALIFIED},
                "answer_text": answer_text
                if decision in {ResearchState.VALIDATED, ResearchState.QUALIFIED}
                else None,
                "required_qualification": qualification,
                "claim_support": [item.model_dump(mode="json") for item in support],
                "semantic_summary": summary.model_dump(mode="json"),
                "blockers": sorted(set(reasons)) if decision == ResearchState.BLOCKED else [],
                "effective_mode": run.effective_mode.value,
                "citations": [
                    {
                        "source_id": source.source_id,
                        "citation": source.citation,
                        "official_identifier": source.official_identifier,
                        "official_url": source.official_url,
                        "evidence_ids": sorted(
                            item.evidence_id
                            for item in eligible
                            if item.source_id == source.source_id
                        ),
                    }
                    for source in sorted(sources.values(), key=lambda item: item.source_id)
                    if any(item.source_id == source.source_id for item in eligible)
                ],
            }
            self.store.complete_operation(run_id, operation_id, result)
            if run.ephemeral:
                self.store.purge_run(run_id)
                result["storage_purged"] = True
            return result

    def _required_run(self, run_id: str) -> ResearchRun:
        run = self.store.get_run(run_id)
        if run is None:
            raise KeyError(f"RESEARCH_RUN_NOT_FOUND: {run_id}")
        return run

    @staticmethod
    def _claim_segment(
        evidence: EvidenceSpan,
        source_tier: str,
        material_type: str,
        official_url: str | None,
        verified_at: datetime | None,
    ) -> LegalSegment:
        role_map = {
            EvidenceSectionType.LAW_TEXT: SectionRole.STATUTE_TEXT,
            EvidenceSectionType.HOLDING: SectionRole.COURT_HOLDING,
            EvidenceSectionType.COURT_HOLDING: SectionRole.COURT_HOLDING,
            EvidenceSectionType.DISPOSITION: SectionRole.DISPOSITION,
            EvidenceSectionType.COURT_REASONING: SectionRole.COURT_REASONING,
            EvidenceSectionType.PARTY_ARGUMENT: SectionRole.PARTY_ARGUMENT,
            EvidenceSectionType.FACTS: SectionRole.FACTS,
            EvidenceSectionType.PROCEDURE: SectionRole.PROCEDURE,
            EvidenceSectionType.CONCURRING_OPINION: SectionRole.CONCURRING_OPINION,
            EvidenceSectionType.DISSENTING_OPINION: SectionRole.DISSENTING_OPINION,
            EvidenceSectionType.MIXED: SectionRole.UNKNOWN,
            EvidenceSectionType.UNKNOWN: SectionRole.UNKNOWN,
            EvidenceSectionType.OTHER: SectionRole.UNKNOWN,
        }
        return LegalSegment(
            segment_id=evidence.evidence_id,
            source_id=evidence.source_id,
            citation_id=evidence.source_id,
            source_tier=source_tier,
            legal_material_type=material_type,
            section_role=role_map[evidence.section_type],
            text=evidence.exact_text,
            span_start=evidence.start_offset or 0,
            span_end=evidence.end_offset or len(evidence.exact_text),
            content_hash=evidence.text_hash,
            official_url=official_url,
            verified_at=verified_at.isoformat() if verified_at else None,
        )

    @staticmethod
    def _result(
        run: ResearchRun,
        outcome: dict[str, Any] | None,
        *,
        replayed: bool,
    ) -> dict[str, Any]:
        return {
            "schema_version": "alr-tw.research-step-result/v1",
            "run_id": run.run_id,
            "state": run.state.value,
            "outcome": outcome,
            "remaining_obligations": [
                item.kind.value
                for item in run.obligations
                if item.status == ResearchObligationStatus.PENDING
            ],
            "replayed": replayed,
        }
