"""Atomic server-owned research run service."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
import re
from threading import RLock
from typing import Any, Protocol
import unicodedata
from uuid import uuid4

from alr_tw.contracts.civil_analysis import CivilLawAnalysis
from alr_tw.contracts.interop import (
    DiscoveryMode,
    RegisteredResearchPlan,
    ResearchPlanProposal,
    ResearchResponsibility,
)
from alr_tw.contracts.legal_context import LegalContextProvider
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
from alr_tw.contracts.sources import (
    EvidenceSectionType,
    EvidenceSpan,
    MaterialType,
    SourceRecord,
    TrustStatus,
)
from alr_tw.storage.sqlite_store import SqliteStore
from alr_tw.providers.synthetic import SyntheticLegalContextProvider
from alr_tw.verification.civil_analysis import (
    validate_civil_analysis as run_civil_analysis_validation,
)
from alr_tw.verification.claim_support import (
    AnswerClaim,
    ClaimBinding,
    ClaimType,
    Importance,
    LegalSegment,
    SectionRole,
    check_claim_support,
    extract_answer_claims,
)
from alr_tw.verification.output_privacy import screen_answer_output

from .state_machine import transition_run

TAIWAN_TIME = timezone(timedelta(hours=8))


_BINDING_CLAIM_TYPES = {
    "law_rule": ClaimType.STATUTORY_RULE,
    "court_view": ClaimType.COURT_VIEW,
    "disposition": ClaimType.COURT_VIEW,
    "fact": ClaimType.FACTUAL_SUMMARY,
    "procedure": ClaimType.PROCEDURAL_STATEMENT,
    "limitation": ClaimType.RISK_ASSESSMENT,
}


def _claim_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return re.sub(r"[^\u3400-\u9fffA-Za-z0-9]", "", normalized).lower()


def _claims_for_validation(
    answer_text: str,
    bindings: list[ClaimBinding],
) -> list[AnswerClaim]:
    extracted = extract_answer_claims(answer_text)
    if not bindings:
        return extracted
    claim_ids = [item.claim_id for item in bindings]
    if len(claim_ids) != len(set(claim_ids)):
        raise ValueError("CLAIM_BINDING_ID_DUPLICATED")
    answer_key = _claim_key(answer_text)
    bound_claims: list[AnswerClaim] = []
    bound_keys: list[str] = []
    for item in bindings:
        key = _claim_key(item.claim_text)
        if not key or key not in answer_key:
            raise ValueError("CLAIM_BINDING_TEXT_NOT_IN_ANSWER")
        bound_keys.append(key)
        bound_claims.append(
            AnswerClaim(
                claim_id=item.claim_id,
                claim_text=item.claim_text,
                claim_type=_BINDING_CLAIM_TYPES[item.claim_type],
                referenced_citation_ids=list(dict.fromkeys(item.evidence_ids)),
                importance=(
                    Importance.CORE
                    if item.importance == "core"
                    else Importance.SUPPLEMENTARY
                ),
            )
        )
    for claim in extracted:
        key = _claim_key(claim.claim_text)
        if not any(key in bound or bound in key for bound in bound_keys):
            bound_claims.append(claim)
    return bound_claims


def _coverage_qualification(run: ResearchRun) -> str:
    qualifications: list[str] = []
    if "COUNTER_AUTHORITY_SEARCH_NOT_IMPLEMENTED" in run.coverage.limitations:
        qualifications.append("公開版未執行系統性的反方裁判搜尋；結論僅限目前已驗證來源。")
    if run.semantic_recall_degraded or run.judgment_recall_incomplete:
        qualifications.append("本次普通法院裁判盤點可能不完整，結論僅限已驗證來源。")
    if not qualifications:
        qualifications.append("本次結論受限於已揭露的檢索與法源涵蓋範圍。")
    return "".join(qualifications)


def _issue_coverage(
    run: ResearchRun,
    bindings: list[ClaimBinding],
) -> tuple[dict[str, Any], list[str]]:
    registered = run.registered_plan
    if registered is None:
        return (
            {
                "schema_version": "alr-tw.issue-coverage/v1",
                "mode": "not_applicable",
                "required_core_issue_ids": [],
                "bound_issue_ids": [],
                "missing_core_issue_ids": [],
                "unknown_issue_ids": [],
            },
            [],
        )

    issues = registered.proposal.issues
    known_issue_ids = {item.issue_id for item in issues}
    required_core_issue_ids = {
        item.issue_id
        for item in issues
        if item.importance.value == "core" and item.requires_conclusion
    }
    bound_issue_ids = {issue_id for binding in bindings for issue_id in binding.issue_ids}
    unknown_issue_ids = bound_issue_ids - known_issue_ids
    missing_core_issue_ids = required_core_issue_ids - bound_issue_ids
    blockers: list[str] = []
    if unknown_issue_ids:
        blockers.append("CLAIM_BINDING_ISSUE_NOT_IN_PLAN")
    if missing_core_issue_ids:
        blockers.append("CORE_RESEARCH_ISSUE_UNBOUND")
    return (
        {
            "schema_version": "alr-tw.issue-coverage/v1",
            "mode": "registered_plan",
            "plan_id": registered.proposal.plan_id,
            "required_core_issue_ids": sorted(required_core_issue_ids),
            "bound_issue_ids": sorted(bound_issue_ids & known_issue_ids),
            "missing_core_issue_ids": sorted(missing_core_issue_ids),
            "unknown_issue_ids": sorted(unknown_issue_ids),
        },
        blockers,
    )


def _clause_span(value: str, position: int) -> tuple[int, int]:
    boundaries = "。\n；;"
    start = max(value.rfind(delimiter, 0, position) for delimiter in boundaries) + 1
    following = [
        index
        for delimiter in boundaries
        if (index := value.find(delimiter, position)) >= 0
    ]
    end = min(following) + 1 if following else len(value)
    return start, end


def _citation_occurrence_reasons(
    answer_text: str,
    bindings: list[ClaimBinding],
    *,
    evidence_by_id: dict[str, EvidenceSpan],
    sources: dict[str, SourceRecord],
) -> list[str]:
    reasons: list[str] = []
    for binding in bindings:
        claim_positions: list[int] = []
        start = 0
        while (position := answer_text.find(binding.claim_text, start)) >= 0:
            claim_positions.append(position)
            start = position + len(binding.claim_text)
        for occurrence in binding.citation_occurrences:
            if occurrence.evidence_id not in binding.evidence_ids:
                reasons.append("CITATION_OCCURRENCE_EVIDENCE_NOT_BOUND")
                continue
            if (
                occurrence.end_offset > len(answer_text)
                or occurrence.end_offset <= occurrence.start_offset
                or answer_text[occurrence.start_offset : occurrence.end_offset]
                != occurrence.citation_text
            ):
                reasons.append("CITATION_OCCURRENCE_TEXT_MISMATCH")
                continue
            evidence = evidence_by_id.get(occurrence.evidence_id)
            source = sources.get(evidence.source_id) if evidence is not None else None
            if source is None or not any(
                value and value in occurrence.citation_text
                for value in (source.citation, source.official_identifier)
            ):
                reasons.append("CITATION_OCCURRENCE_SOURCE_MISMATCH")
            citation_clause = _clause_span(answer_text, occurrence.start_offset)
            if not any(
                _clause_span(answer_text, position) == citation_clause
                for position in claim_positions
            ):
                reasons.append("CITATION_OCCURRENCE_OUTSIDE_BOUND_CLAUSE")
    return reasons


def _merge_plan_obligations(
    obligations: list[ResearchObligation],
    proposal: ResearchPlanProposal,
) -> list[ResearchObligation]:
    material_types = {item.material_type.value for item in proposal.authority_locators}
    issue_categories = {item.category.value for item in proposal.issues}
    purposes = {item.purpose.value for item in proposal.authority_locators}
    required_kinds: list[ResearchObligationKind] = []
    if "judgment" in material_types:
        required_kinds.extend(
            [
                ResearchObligationKind.JUDGMENT_RECALL,
                ResearchObligationKind.JUDGMENT_OFFICIAL_VERIFICATION,
            ]
        )
    if "constitutional" in material_types:
        required_kinds.append(ResearchObligationKind.CONSTITUTIONAL_RESEARCH)
    if "counter_authority" in issue_categories or "counter_authority" in purposes:
        required_kinds.append(ResearchObligationKind.COUNTER_AUTHORITY)
    if "temporal_applicability" in issue_categories or "temporal_context" in purposes:
        required_kinds.append(ResearchObligationKind.LEGAL_TIME_CONTEXT)

    existing = {item.kind for item in obligations}
    additions = [
        ResearchObligation(kind=kind)
        for kind in required_kinds
        if kind not in existing
    ]
    if not additions:
        return obligations
    insert_at = next(
        (
            index
            for index, item in enumerate(obligations)
            if item.kind is ResearchObligationKind.EVIDENCE_SUFFICIENCY
        ),
        len(obligations),
    )
    return obligations[:insert_at] + additions + obligations[insert_at:]


def _missing_required_locator_types(
    run: ResearchRun,
    proposal: ResearchPlanProposal,
) -> list[MaterialType]:
    obligation_kinds = {item.kind for item in run.obligations}
    required = {MaterialType.LAW}
    if ResearchObligationKind.JUDGMENT_RECALL in obligation_kinds:
        required.add(MaterialType.JUDGMENT)
    if ResearchObligationKind.CONSTITUTIONAL_RESEARCH in obligation_kinds:
        required.add(MaterialType.CONSTITUTIONAL)
    provided = {item.material_type for item in proposal.authority_locators}
    return sorted(required - provided, key=lambda item: item.value)


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
    current_date: date | None = None,
    discovery_mode: DiscoveryMode = DiscoveryMode.SERVER_MANAGED,
) -> list[ResearchObligation]:
    kinds: list[ResearchObligationKind] = []
    if discovery_mode is DiscoveryMode.CLIENT_ASSISTED:
        kinds.append(ResearchObligationKind.EXTERNAL_PLAN_REVIEW)
    kinds.append(ResearchObligationKind.QUERY_UNDERSTANDING)
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
    reference_date = current_date or datetime.now(TAIWAN_TIME).date()
    if (as_of_date is not None and as_of_date != reference_date) or any(
        token in query for token in ("修法前", "修法後", "當時")
    ):
        kinds.append(ResearchObligationKind.LEGAL_TIME_CONTEXT)
    kinds.extend(
        [
            ResearchObligationKind.EVIDENCE_SUFFICIENCY,
            ResearchObligationKind.FINAL_ANSWER_VALIDATION,
        ]
    )
    return [ResearchObligation(kind=kind) for kind in kinds]


class ResearchService:
    def __init__(
        self,
        store: SqliteStore,
        executor: ObligationExecutor | None = None,
        *,
        legal_context_provider: LegalContextProvider | None = None,
    ):
        self.store = store
        self.executor = executor or SyntheticObligationExecutor()
        self.legal_context_provider = (
            legal_context_provider or SyntheticLegalContextProvider()
        )
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
        discovery_mode: DiscoveryMode = DiscoveryMode.SERVER_MANAGED,
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
                current_date=timestamp.astimezone(TAIWAN_TIME).date(),
                discovery_mode=discovery_mode,
            ),
            coverage=CoverageState(),
            responsibility=ResearchResponsibility(discovery_mode=discovery_mode),
        )
        self.store.save_run(run)
        return run

    def get_run(self, run_id: str) -> ResearchRun | None:
        return self.store.get_run(run_id)

    def get_state(self, run_id: str) -> dict[str, Any]:
        run = self._required_run(run_id)
        registered_plan = run.registered_plan
        return {
            "schema_version": "alr-tw.research-state/v1",
            "run": run.model_dump(mode="json"),
            "source_count": len(self.store.list_sources(run_id)),
            "evidence_count": len(self.store.list_evidence(run_id)),
            "ready_for_draft": run.state == ResearchState.READY_FOR_DRAFT,
            "awaiting_external_plan": (
                run.responsibility.discovery_mode is DiscoveryMode.CLIENT_ASSISTED
                and registered_plan is None
            ),
            "interoperability": {
                "responsibility": run.responsibility.model_dump(mode="json"),
                "registered_plan": (
                    {
                        "plan_id": registered_plan.proposal.plan_id,
                        "proposal_digest": registered_plan.proposal_digest,
                        "trust_status": registered_plan.trust_status,
                        "issue_count": len(registered_plan.proposal.issues),
                        "authority_locator_count": len(
                            registered_plan.proposal.authority_locators
                        ),
                    }
                    if registered_plan is not None
                    else None
                ),
            },
        }

    def register_research_plan(
        self,
        run_id: str,
        operation_id: str,
        proposal: ResearchPlanProposal | dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not operation_id.strip():
            raise ValueError("operation_id is required")
        normalized_proposal = (
            proposal
            if isinstance(proposal, ResearchPlanProposal)
            else ResearchPlanProposal.model_validate(proposal)
        )
        with self._lock:
            existing = self.store.get_operation(run_id, operation_id)
            if existing is not None:
                return existing
            run = self._required_run(run_id)
            timestamp = now or datetime.now(UTC)
            if run.expires_at <= timestamp:
                raise ValueError("RESEARCH_RUN_EXPIRED")
            if run.state is not ResearchState.PLANNING:
                raise ValueError("RESEARCH_PLAN_REGISTRATION_CLOSED")
            if run.responsibility.discovery_mode is not DiscoveryMode.CLIENT_ASSISTED:
                raise ValueError("CLIENT_ASSISTED_DISCOVERY_NOT_ENABLED")
            if run.registered_plan is not None:
                raise ValueError("RESEARCH_PLAN_ALREADY_REGISTERED")
            missing_locator_types = _missing_required_locator_types(
                run,
                normalized_proposal,
            )
            if missing_locator_types:
                raise ValueError(
                    "RESEARCH_PLAN_REQUIRED_LOCATOR_MISSING: "
                    + ", ".join(item.value for item in missing_locator_types)
                )

            registered = RegisteredResearchPlan.from_proposal(
                normalized_proposal,
                received_at=timestamp,
            )
            obligations = [
                item.model_copy(update={"status": ResearchObligationStatus.COMPLETED})
                if item.kind is ResearchObligationKind.EXTERNAL_PLAN_REVIEW
                else item
                for item in run.obligations
            ]
            obligations = _merge_plan_obligations(obligations, normalized_proposal)
            run = run.model_copy(
                update={
                    "registered_plan": registered,
                    "obligations": obligations,
                    "updated_at": timestamp,
                }
            )
            result = {
                "schema_version": "alr-tw.research-plan-registration/v1",
                "run_id": run_id,
                "plan_id": registered.proposal.plan_id,
                "proposal_digest": registered.proposal_digest,
                "trust_status": registered.trust_status,
                "accepted_issue_ids": [
                    item.issue_id for item in registered.proposal.issues
                ],
                "accepted_locator_ids": [
                    item.locator_id
                    for item in registered.proposal.authority_locators
                ],
                "candidate_only": True,
            }
            self.store.record_operation(run_id, operation_id, {"status": "in_progress"})
            self.store.save_run(run)
            self.store.complete_operation(run_id, operation_id, result)
            return result

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
            if (
                run.responsibility.discovery_mode is DiscoveryMode.CLIENT_ASSISTED
                and run.registered_plan is None
            ):
                raise ValueError("EXTERNAL_RESEARCH_PLAN_REQUIRED")
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

    def validate_civil_analysis(
        self,
        run_id: str,
        operation_id: str,
        analysis: CivilLawAnalysis,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Validate an untrusted civil analysis against this run's server-owned state."""

        with self._lock:
            run = self._required_run(run_id)
            timestamp = now or datetime.now(UTC)
            if run.expires_at <= timestamp:
                raise ValueError("RESEARCH_RUN_EXPIRED")
            if run.state is not ResearchState.READY_FOR_DRAFT:
                raise ValueError("RESEARCH_OBLIGATION_PENDING")
            operation = self.store.record_operation(
                run_id,
                operation_id,
                {"status": "in_progress"},
            )
            if not operation.created:
                return operation.result

            sources = self.store.list_sources(run_id)
            evidence = self.store.list_evidence(run_id)
            legal_context = self.legal_context_provider.assess(
                sources,
                as_of_date=(
                    run.as_of_date
                    or timestamp.astimezone(TAIWAN_TIME).date()
                ),
                assessed_at=timestamp,
            )
            validation = run_civil_analysis_validation(
                analysis,
                server_sources=sources,
                server_evidence=evidence,
                legal_context=legal_context,
                validated_at=timestamp,
            )
            result = {
                **validation.model_dump(mode="json"),
                "run_id": run_id,
                "legal_context": {
                    "schema_version": legal_context.schema_version,
                    "provider_id": legal_context.provider_id,
                    "status": legal_context.status.value,
                    "record_count": len(legal_context.records),
                    "limitations": legal_context.limitations,
                },
            }
            self.store.complete_operation(run_id, operation_id, result)
            return result

    def validate_answer(
        self,
        run_id: str,
        answer_text: str,
        operation_id: str,
        *,
        claim_bindings: list[dict[str, Any]] | list[ClaimBinding] | None = None,
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
            bindings = [
                item if isinstance(item, ClaimBinding) else ClaimBinding.model_validate(item)
                for item in (claim_bindings or [])
            ]
            claims = _claims_for_validation(answer_text, bindings)
            answer_privacy = screen_answer_output(answer_text)
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
            evidence_by_id = {item.evidence_id: item for item in evidence}
            bound_evidence_ids = {
                evidence_id for item in bindings for evidence_id in item.evidence_ids
            }
            binding_reasons: list[str] = []
            for evidence_id in sorted(bound_evidence_ids):
                item = evidence_by_id.get(evidence_id)
                if item is None:
                    binding_reasons.append("CLAIM_EVIDENCE_NOT_FOUND")
                    continue
                source = sources.get(item.source_id)
                if source is None:
                    binding_reasons.append("CLAIM_EVIDENCE_SOURCE_NOT_FOUND")
                elif source.expires_at <= timestamp:
                    binding_reasons.append("SOURCE_STALE")
                elif source.trust_status != TrustStatus.EVIDENCE_ELIGIBLE:
                    binding_reasons.append("SOURCE_NOT_EVIDENCE_ELIGIBLE")
                elif not item.eligible_for_claim_support:
                    binding_reasons.append("EVIDENCE_NOT_ELIGIBLE_FOR_CLAIM_SUPPORT")
            eligible = [
                item
                for item in evidence
                if item.eligible_for_claim_support
                and item.source_id in sources
                and sources[item.source_id].trust_status == TrustStatus.EVIDENCE_ELIGIBLE
                and sources[item.source_id].expires_at > timestamp
            ]
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
                require_explicit_bindings=True,
            )
            reasons.extend(binding_reasons)
            issue_coverage, issue_reasons = _issue_coverage(run, bindings)
            reasons.extend(issue_reasons)
            reasons.extend(
                _citation_occurrence_reasons(
                    answer_text,
                    bindings,
                    evidence_by_id=evidence_by_id,
                    sources=sources,
                )
            )
            if not claims:
                reasons.append("CLAIM_SUPPORT_NOT_CHECKED")
            if answer_privacy.status == "redaction_required":
                reasons.append("ANSWER_PRIVACY_REDACTION_REQUIRED")
                reasons.append("ANSWER_CONTAINS_SENSITIVE_DATA")
            elif answer_privacy.status == "blocked":
                reasons.append("ANSWER_PRIVACY_BLOCKED")
                reasons.append("ANSWER_CONTAINS_SENSITIVE_DATA")
            if "HISTORICAL_LAW_VERSION_UNSUPPORTED" in run.coverage.limitations:
                reasons.append("HISTORICAL_LAW_VERSION_UNSUPPORTED")
            binding_mode = "structured" if bindings else "legacy_unbound"
            safe = (
                bool(eligible)
                and summary.semantic_safe_to_present
                and answer_privacy.allowed
                and not reasons
            )
            coverage_qualified = bool(
                run.semantic_recall_degraded
                or run.judgment_recall_incomplete
                or run.coverage.limitations
            )
            if safe and (coverage_qualified or binding_mode == "legacy_unbound"):
                decision = ResearchState.QUALIFIED
                qualification = (
                    "未提供 claim_bindings；本結果僅為舊版相容驗證，"
                    "不得將其視為核心法律主張已完成 span-level 驗證。"
                    if binding_mode == "legacy_unbound"
                    else _coverage_qualification(run)
                )
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
                "schema_version": "alr-tw.answer-validation/v3",
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
                "verification_method": "deterministic_grounding_v2",
                "semantic_entailment_performed": False,
                "binding_mode": binding_mode,
                "issue_coverage": issue_coverage,
                "privacy": answer_privacy.model_dump(mode="json"),
                "coverage_summary": {
                    **run.coverage.model_dump(mode="json"),
                    "semantic_recall_degraded": run.semantic_recall_degraded,
                    "judgment_recall_incomplete": run.judgment_recall_incomplete,
                },
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
                            and (
                                binding_mode == "legacy_unbound"
                                or item.evidence_id in bound_evidence_ids
                            )
                        ),
                    }
                    for source in sorted(sources.values(), key=lambda item: item.source_id)
                    if any(
                        item.source_id == source.source_id
                        and (
                            binding_mode == "legacy_unbound"
                            or item.evidence_id in bound_evidence_ids
                        )
                        for item in eligible
                    )
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
            citation_id=evidence.evidence_id,
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
