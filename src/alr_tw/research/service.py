"""Atomic server-owned research run service."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
import re
from threading import RLock
from time import perf_counter
from typing import Any, Literal, Protocol
import unicodedata
from uuid import uuid4

from alr_tw.contracts.legal_analysis import LegalAnalysisEnvelope
from alr_tw.contracts.civil_analysis import CounterAuthorityRelation
from alr_tw.contracts.finalization import (
    FinalizationBlocker,
    FinalizationContract,
    build_finalization_from_run,
    build_structured_refusal,
)
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
    MAX_JUDGMENT_VERIFICATIONS,
    PrivacyStatus,
    ResearchDepth,
    ResearchBlocker,
    ResearchBrief,
    ResearchBriefBlocker,
    ResearchBriefObligation,
    ResearchBriefSource,
    ResearchObligation,
    ResearchObligationKind,
    ResearchObligationStatus,
    ResearchRun,
    ResearchState,
    AnswerMode,
    evaluate_research_sufficiency,
)
from alr_tw.contracts.sources import (
    EvidenceSectionType,
    EvidenceSpan,
    MaterialType,
    SourceRecord,
    TrustStatus,
)
from alr_tw.contracts.provider_snapshot import ProviderSnapshotReceipt
from alr_tw.storage.sqlite_store import SqliteStore
from alr_tw.providers.synthetic import SyntheticLegalContextProvider
from alr_tw.research.counter_authority import CounterAuthorityProgress
from alr_tw.verification.legal_analysis import (
    validate_legal_analysis as run_legal_analysis_validation,
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
from .snapshot_receipts import (
    check_run_snapshot_receipts,
    issue_run_snapshot_receipts,
    mark_receipts_inconsistent,
)

TAIWAN_TIME = timezone(timedelta(hours=8))

_EXPLICIT_LAW_ARTICLE = re.compile(
    r"[\u4e00-\u9fff]{1,30}(?:法|條例|規則|辦法)第\s*"
    r"\d+(?:\s*(?:之|-)\s*\d+)*\s*條"
)
_JUDGMENT_LOOKUP_MARKERS = (
    "判決",
    "裁判",
    "類案",
    "法院見解",
    "裁定",
    "案號",
    "字號",
    "JID",
)


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


def _evidence_query_overlap(query: str, text: str) -> int:
    query_key = _claim_key(query)
    text_key = _claim_key(text)
    if not query_key or not text_key:
        return 0
    width = 2 if len(query_key) < 12 else 3
    grams = {
        query_key[index : index + width] for index in range(max(1, len(query_key) - width + 1))
    }
    return sum(gram in text_key for gram in grams)


def _evidence_section_priority(section_type: EvidenceSectionType) -> int:
    priorities = {
        EvidenceSectionType.DISPOSITION: 0,
        EvidenceSectionType.COURT_HOLDING: 1,
        EvidenceSectionType.HOLDING: 1,
        EvidenceSectionType.COURT_REASONING: 2,
        EvidenceSectionType.FACTS: 3,
        EvidenceSectionType.PROCEDURE: 4,
        EvidenceSectionType.PARTY_ARGUMENT: 5,
    }
    return priorities.get(section_type, 9)


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


def _outcome_reason_codes(outcome: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    """Split an executor outcome into auditable coverage reason buckets."""

    warnings = [str(value) for value in outcome.get("warnings", []) if value]
    # Some executor warnings document a deliberate handoff rather than a
    # degraded provider result.  Keep this allowlist narrow: unknown warning
    # codes remain errors until explicitly classified by the provider contract.
    informational_codes = {
        "EXACT_JUDGMENT_IDENTIFIER_WILL_USE_OFFICIAL_PROVIDER",
    }
    metadata = outcome.get("metadata")
    verified_subset_failure_codes: set[str] = set()
    if isinstance(metadata, dict) and metadata.get("verified_source_count", 0) > 0:
        raw_failed_codes = metadata.get("failed_reason_codes", [])
        if isinstance(raw_failed_codes, list):
            verified_subset_failure_codes = {str(code).upper() for code in raw_failed_codes if code}
    if isinstance(metadata, dict) and metadata.get("status") == "not_found_in_scope":
        # A clean bounded miss is a successful scoped outcome.  It must not
        # become a generic partial/error gap merely because the audit reason
        # is present in the provider metadata.
        informational_codes.add("COUNTER_AUTHORITY_NOT_FOUND_IN_SCOPE")
    codes = [code for code in warnings if code.upper() not in informational_codes]
    error_code = outcome.get("error_code")
    if error_code:
        codes.append(str(error_code))
    for call in outcome.get("provider_calls", []):
        if not isinstance(call, dict):
            continue
        call_error = call.get("error_code")
        if call_error:
            codes.append(str(call_error))

    partial: list[str] = []
    errors: list[str] = []
    timeouts: list[str] = []
    for raw_code in codes:
        code = raw_code.upper()
        if "TIMEOUT" in code or "TIMED_OUT" in code:
            timeouts.append(raw_code)
        elif code in verified_subset_failure_codes:
            partial.append(raw_code)
        elif code == "TLR_UNAVAILABLE":
            # TLR is an optional recall enhancer.  Its outage is a bounded
            # degradation; official recall/verification remains authoritative.
            partial.append(raw_code)
        elif code == "QUICK_JUDGMENT_RECALL_BOUNDED":
            partial.append(raw_code)
        elif any(
            marker in code
            for marker in (
                "INCOMPLETE",
                "NOT_IMPLEMENTED",
                "REQUIRE_EXACT_LOOKUP",
                "TRUNCATED",
                "PARTIAL",
                "MISSING",
                "UNRESOLVED",
                "DEGRADED",
                "SYNTHETIC_MODE",
                "UNSUPPORTED",
                "CANDIDATE_ONLY",
                "NOT_FOUND_IN_SCOPE",
                "NOT_FOUND",
            )
        ):
            partial.append(raw_code)
        elif raw_code:
            errors.append(raw_code)
    return sorted(set(partial)), sorted(set(errors)), sorted(set(timeouts))


def _is_retryable_outcome_code(code: str) -> bool:
    normalized = code.upper()
    return any(
        marker in normalized
        for marker in (
            "TIMEOUT",
            "TIMED_OUT",
            "UNAVAILABLE",
            "TEMPORARY",
            "RATE_LIMIT",
            "RETRY",
        )
    )


def _is_retryable_derived_code(code: str) -> bool:
    normalized = code.upper()
    return _is_retryable_outcome_code(normalized) or any(
        marker in normalized for marker in ("INCOMPLETE", "DEGRADED")
    )


def _retryable_outcome_codes(outcome: dict[str, Any]) -> list[str]:
    """Return only explicitly transient provider diagnostics."""

    partial, errors, timeouts = _outcome_reason_codes(outcome)
    return sorted(
        {
            code
            for code in (*partial, *errors, *timeouts)
            if _is_retryable_outcome_code(code)
        }
    )


def _filter_optional_tlr_retry_codes(
    outcome: dict[str, Any],
    codes: list[str],
    *,
    recall_complete: bool = False,
) -> list[str]:
    """Do not block recall when optional TLR failed after official candidates.

    TLR improves recall in hybrid mode but is not itself an authority.  Its
    outage degrades the recall scope; a separate required-provider failure
    remains retryable.  The provider is not re-run after its server-owned
    hybrid-to-official downgrade, so it must not strand the obligation.
    """

    if outcome.get("obligation") != ResearchObligationKind.JUDGMENT_RECALL.value:
        return codes
    provider_error_codes = {
        str(call.get("error_code"))
        for call in outcome.get("provider_calls", [])
        if isinstance(call, dict)
        and call.get("status") == "error"
        and call.get("error_code")
    }
    if recall_complete:
        # A candidate from either recall provider is enough to continue to
        # official exact verification.  Search-provider failures are then a
        # bounded recall limitation, not a reason to strand this obligation.
        return [code for code in codes if code not in provider_error_codes]
    tlr_codes = {
        code
        for code in provider_error_codes
        if code == "TLR_UNAVAILABLE"
        or code.startswith("TLR_")
    }
    tlr_codes.add("TLR_UNAVAILABLE")
    return [code for code in codes if code not in tlr_codes]


def _nonblocking_recall_codes(
    outcome: dict[str, Any],
    *,
    recall_complete: bool,
) -> set[str]:
    if (
        not recall_complete
        or outcome.get("obligation") != ResearchObligationKind.JUDGMENT_RECALL.value
    ):
        return set()
    return {
        str(call.get("error_code"))
        for call in outcome.get("provider_calls", [])
        if isinstance(call, dict)
        and call.get("status") == "error"
        and call.get("error_code")
    }


def _required_coverage_complete(run: ResearchRun) -> bool:
    required_kinds = {
        item.kind
        for item in run.obligations
        if item.required and item.kind is not ResearchObligationKind.FINAL_ANSWER_VALIDATION
    }
    checks = {
        ResearchObligationKind.LAW_RESEARCH: run.coverage.law_checked,
        ResearchObligationKind.JUDGMENT_RECALL: run.coverage.judgment_checked,
        ResearchObligationKind.JUDGMENT_OFFICIAL_VERIFICATION: run.coverage.judgment_checked,
        ResearchObligationKind.CONSTITUTIONAL_RESEARCH: run.coverage.constitutional_checked,
        ResearchObligationKind.COUNTER_AUTHORITY: run.coverage.counter_authority_checked,
        ResearchObligationKind.LEGAL_TIME_CONTEXT: run.coverage.time_context_checked,
    }
    return all(checks.get(kind, True) for kind in required_kinds)


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


class JudgmentLineageExecutor(Protocol):
    def inspect_judgment_lineage(
        self,
        run_id: str,
        jid: str,
        *,
        max_related_nodes: int = 8,
    ) -> dict[str, Any]: ...


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


def _has_explicit_law_article(query: str) -> bool:
    return _EXPLICIT_LAW_ARTICLE.search(query) is not None


def _is_judgment_lookup_query(query: str) -> bool:
    normalized = query.upper()
    if any(marker.upper() in normalized for marker in _JUDGMENT_LOOKUP_MARKERS):
        return True
    if re.search(
        r"[A-Z0-9]{3,12},[^,\r\n]{1,80},[^,\r\n]{1,80},"
        r"\d+,\d{8},\d+",
        query,
        flags=re.IGNORECASE,
    ):
        return True
    return (
        re.search(
            r"[\u4e00-\u9fff]{2,24}法院\s*\d{1,3}\s*年度\s*"
            r"[^,，。；;\r\n]{1,20}?字\s*第\s*\d{1,12}\s*號"
            r"(?:(?:民事|刑事|行政|懲戒)(?:判決|裁定)?)?",
            query,
        )
        is not None
    )


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
    quick_judgment_lookup = depth is ResearchDepth.QUICK and _is_judgment_lookup_query(query)
    # QUICK is query-aware.  A request for similar judgments spends its
    # bounded budget on candidate recall and exact-content verification; an
    # explicit statute citation still keeps the law branch in scope.
    if not quick_judgment_lookup or _has_explicit_law_article(query):
        kinds.append(ResearchObligationKind.LAW_RESEARCH)
    if depth in {ResearchDepth.STANDARD, ResearchDepth.DEEP} or quick_judgment_lookup:
        kinds.extend(
            [
                ResearchObligationKind.JUDGMENT_RECALL,
                ResearchObligationKind.JUDGMENT_OFFICIAL_VERIFICATION,
            ]
        )
        if depth is not ResearchDepth.QUICK and include_counter_authority:
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
        self.legal_context_provider = legal_context_provider or SyntheticLegalContextProvider()
        self._lock = RLock()

    def create_run(
        self,
        query: str,
        *,
        mode: DataMode,
        depth: ResearchDepth = ResearchDepth.STANDARD,
        max_judgment_verifications: int = MAX_JUDGMENT_VERIFICATIONS,
        include_counter_authority: bool | None = None,
        ephemeral: bool = False,
        as_of_date: date | None = None,
        retention_seconds: int = 86400,
        now: datetime | None = None,
        discovery_mode: DiscoveryMode = DiscoveryMode.SERVER_MANAGED,
    ) -> ResearchRun:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query is required")
        if isinstance(max_judgment_verifications, bool) or not (
            1 <= max_judgment_verifications <= MAX_JUDGMENT_VERIFICATIONS
        ):
            raise ValueError("max_judgment_verifications must be an integer between 1 and 5")
        if include_counter_authority is None:
            include_counter_authority = depth is not ResearchDepth.QUICK
        elif include_counter_authority and depth is ResearchDepth.QUICK:
            raise ValueError(
                "include_counter_authority is incompatible with research_depth=quick"
            )
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
            max_judgment_verifications=max_judgment_verifications,
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

    def _run_with_server_refs(self, run: ResearchRun) -> ResearchRun:
        """Refresh source/evidence references strictly from this run's store."""

        return run.model_copy(
            update={
                "source_ids": sorted(item.source_id for item in self.store.list_sources(run.run_id)),
                "evidence_ids": sorted(item.evidence_id for item in self.store.list_evidence(run.run_id)),
            }
        )

    def _run_with_eligible_refs(
        self,
        run: ResearchRun,
        *,
        now: datetime,
    ) -> ResearchRun:
        """Project currently eligible evidence for a finalization decision.

        The persisted run retains every server-linked source/evidence ID for
        audit and possible revalidation.  This ephemeral projection is the
        only view used by sufficiency/finalization: a source must still be
        ``EVIDENCE_ELIGIBLE`` and unexpired, and an evidence span must be
        claim-support eligible and linked to one of those sources.
        """

        sources = self.store.list_sources(run.run_id)
        evidence = self.store.list_evidence(run.run_id)
        eligible_sources = {
            item.source_id: item
            for item in sources
            if item.trust_status is TrustStatus.EVIDENCE_ELIGIBLE
            and item.expires_at > now
        }
        eligible_evidence = [
            item
            for item in evidence
            if item.eligible_for_claim_support
            and item.source_id in eligible_sources
        ]
        dropped_evidence = set(run.evidence_ids) - {
            item.evidence_id for item in eligible_evidence
        }
        dropped_sources = set(run.source_ids) - set(eligible_sources)
        coverage = run.coverage
        limitations = list(coverage.limitations)
        if dropped_evidence or dropped_sources:
            if "SERVER_EVIDENCE_STALE_OR_INELIGIBLE" not in limitations:
                limitations.append("SERVER_EVIDENCE_STALE_OR_INELIGIBLE")
            coverage = coverage.model_copy(update={"limitations": limitations})

        blockers = list(run.blockers)
        if run.evidence_ids and not eligible_evidence:
            if not any(item.code == "SERVER_EVIDENCE_UNAVAILABLE" for item in blockers):
                blockers.append(
                    ResearchBlocker(
                        code="SERVER_EVIDENCE_UNAVAILABLE",
                        message=(
                            "研究仍保留 server evidence 參照，但目前沒有同時具備 "
                            "EVIDENCE_ELIGIBLE、未過期且正確連結的 evidence。"
                        ),
                    )
                )
        return run.model_copy(
            update={
                "source_ids": sorted(eligible_sources),
                "evidence_ids": sorted(item.evidence_id for item in eligible_evidence),
                "coverage": coverage,
                "blockers": blockers,
            }
        )

    def _assessed_finalization_runs(
        self,
        run: ResearchRun,
        *,
        now: datetime,
    ) -> tuple[ResearchRun, ResearchRun]:
        """Return (full server run, eligible assessed projection)."""

        full_run = self._run_with_server_refs(run)
        eligible_run = self._run_with_eligible_refs(full_run, now=now)
        assessed = self._refresh_sufficiency(eligible_run)
        return full_run, assessed

    def _sync_snapshot_receipts(
        self,
        run: ResearchRun,
        *,
        now: datetime,
    ) -> list[ProviderSnapshotReceipt]:
        """Persist receipts issued only from the server's current run material."""

        if run.requested_mode is DataMode.SYNTHETIC:
            self.store.replace_provider_snapshot_receipts(run.run_id, [])
            return []
        sources = self.store.list_sources(run.run_id)
        evidence = self.store.list_evidence(run.run_id)
        receipts = issue_run_snapshot_receipts(
            run,
            sources,
            evidence,
            existing=self.store.list_provider_snapshot_receipts(run.run_id),
            now=now,
        )
        self.store.replace_provider_snapshot_receipts(run.run_id, receipts)
        return receipts

    def _snapshot_receipts_for_finalization(
        self,
        run: ResearchRun,
        *,
        now: datetime,
    ) -> list[ProviderSnapshotReceipt]:
        """Return only receipts still bound to the exact eligible run material."""

        receipts = self.store.list_provider_snapshot_receipts(run.run_id)
        check = check_run_snapshot_receipts(
            run,
            self.store.list_sources(run.run_id),
            self.store.list_evidence(run.run_id),
            receipts,
            now=now,
        )
        if check.valid:
            return receipts
        return mark_receipts_inconsistent(receipts) if receipts else []

    @staticmethod
    def _finalization_summary(contract: FinalizationContract) -> dict[str, Any]:
        """Compact get_state view; full contract is available through its tool."""

        return {
            "schema_version": contract.schema_version,
            "workflow_complete": contract.workflow_complete,
            "research_sufficiency": contract.research_sufficiency.value,
            "answer_mode": contract.answer_mode.value,
            "required_qualification": list(contract.required_qualification),
            "blocker_codes": [item.code for item in contract.blockers],
            "pending_support": list(contract.pending_support),
            "pending_lookups": list(contract.pending_lookups),
            "snapshot_consistency": (
                contract.snapshot_consistency.status.value
                if contract.snapshot_consistency is not None
                else "unknown"
            ),
            "snapshot_receipt_count": len(contract.snapshot_receipts),
            "evidence_authorization": (
                contract.evidence_authorization.model_dump(mode="json")
                if contract.evidence_authorization is not None
                else None
            ),
        }

    def _research_brief(
        self,
        run: ResearchRun,
        contract: FinalizationContract,
        *,
        now: datetime,
    ) -> dict[str, Any]:
        """Build a source-and-progress brief that can never authorize an answer."""

        verified = sorted(
            (
                source
                for source in self.store.list_sources(run.run_id)
                if source.expires_at > now
                and source.trust_status
                in {TrustStatus.OFFICIAL_VERIFIED, TrustStatus.EVIDENCE_ELIGIBLE}
            ),
            key=lambda source: (source.material_type.value, source.citation, source.source_id),
        )
        visible = verified[:64]
        if run.state is ResearchState.BLOCKED or (
            contract.workflow_complete and contract.answer_mode is AnswerMode.REFUSAL_ONLY
        ):
            status: Literal["in_progress", "ready_for_draft", "blocked"] = "blocked"
        elif contract.workflow_complete:
            status = "ready_for_draft"
        else:
            status = "in_progress"

        actions = list(contract.safe_next_actions)
        if not contract.workflow_complete:
            actions.append("以新的 operation_id 繼續完成尚未完成的研究義務。")
        elif contract.answer_mode is not AnswerMode.REFUSAL_ONLY:
            actions.append(
                "僅依 evidence bundle 撰寫草稿，並以 passage 級 claim_bindings 呼叫 "
                "validate_legal_answer。"
            )
        reasons = [item.code for item in contract.blockers]
        reasons.append("RESEARCH_BRIEF_IS_NOT_A_VALIDATED_ANSWER")
        brief = ResearchBrief(
            run_id=run.run_id,
            status=status,
            answer_mode=contract.answer_mode,
            verified_sources=[
                ResearchBriefSource(
                    source_id=source.source_id,
                    material_type=source.material_type.value,
                    trust_status=(
                        "official_verified"
                        if source.trust_status is TrustStatus.OFFICIAL_VERIFIED
                        else "evidence_eligible"
                    ),
                    citation=source.citation,
                    official_identifier=source.official_identifier,
                    official_url=source.official_url,
                    verified_at=source.verified_at,
                )
                for source in visible
            ],
            verified_source_count=len(verified),
            omitted_verified_source_count=len(verified) - len(visible),
            obligations=[
                ResearchBriefObligation(
                    kind=item.kind,
                    status=item.status,
                    required=item.required,
                    reason=item.reason[:500],
                    blocker_code=item.blocker_code,
                )
                for item in run.obligations
            ],
            blockers=[
                ResearchBriefBlocker(
                    code=item.code,
                    message=item.message[:500],
                    retryable=item.retryable,
                )
                for item in contract.blockers
            ],
            reason_codes=sorted(set(reasons)),
            limitations=sorted(set(run.coverage.limitations)),
            safe_next_actions=list(dict.fromkeys(actions)),
        )
        return brief.model_dump(mode="json")

    @staticmethod
    def _refusal_contract(
        contract: FinalizationContract,
        *,
        extra_blocker: FinalizationBlocker | None = None,
    ) -> FinalizationContract:
        """Create a validated refusal envelope without trusting loose dicts.

        ``BaseModel.model_copy(update=...)`` deliberately skips validation in
        Pydantic.  Refusal paths therefore rebuild through ``model_validate``
        so every blocker is a server-owned ``FinalizationBlocker`` rather than
        an untyped caller-shaped mapping.
        """

        payload = contract.model_dump(mode="python")
        blockers = [
            item.model_dump(mode="python")
            for item in contract.blockers
        ]
        if extra_blocker is not None and not any(
            item.get("code") == extra_blocker.code for item in blockers
        ):
            blockers.append(extra_blocker.model_dump(mode="python"))
        payload.update(
            {
                "answer_mode": AnswerMode.REFUSAL_ONLY,
                "answer_draft": None,
                "blockers": blockers,
                "retryable": contract.retryable
                or (extra_blocker.retryable if extra_blocker is not None else False),
            }
        )
        return FinalizationContract.model_validate(payload)

    @staticmethod
    def _terminal_refusal(
        run: ResearchRun,
        contract: FinalizationContract,
    ) -> bool:
        return not contract.retryable and run.state in {
            ResearchState.READY_FOR_DRAFT,
            ResearchState.VALIDATING,
            ResearchState.BLOCKED,
        }

    def _persist_refusal_decision(
        self,
        run: ResearchRun,
        contract: FinalizationContract,
        *,
        timestamp: datetime,
    ) -> ResearchRun:
        """Persist a fail-closed answer decision using legal state transitions.

        A final answer attempt must not silently mutate a still-running
        research workflow.  Only a non-retryable refusal at
        ``READY_FOR_DRAFT`` (or an already validating/blocked run) is terminal;
        pending/retryable runs remain resumable and keep the final-answer
        obligation pending.  Every branch still saves the server-owned run so
        operation replay and state inspection observe the same server facts.
        """

        terminal = self._terminal_refusal(run, contract)
        persisted = run.model_copy(update={"updated_at": timestamp})
        if terminal and persisted.state is ResearchState.READY_FOR_DRAFT:
            persisted = transition_run(
                persisted,
                ResearchState.VALIDATING,
                updated_at=timestamp,
            )
        if terminal and persisted.state is ResearchState.VALIDATING:
            persisted = transition_run(
                persisted,
                ResearchState.BLOCKED,
                updated_at=timestamp,
            )
        if terminal:
            obligations = [
                item.model_copy(update={"status": ResearchObligationStatus.COMPLETED})
                if item.kind is ResearchObligationKind.FINAL_ANSWER_VALIDATION
                else item
                for item in persisted.obligations
            ]
            persisted = persisted.model_copy(update={"obligations": obligations})
        self.store.save_run(persisted)
        return persisted

    def get_finalization_contract(
        self,
        run_id: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Return a server-built finalization contract for one research run."""

        with self._lock:
            run = self._required_run(run_id)
            timestamp = now or datetime.now(UTC)
            if run.expires_at <= timestamp:
                raise ValueError("RESEARCH_RUN_EXPIRED")
            full_run, assessed = self._assessed_finalization_runs(run, now=timestamp)
            refreshed = full_run.model_copy(
                update={
                    "workflow_complete": assessed.workflow_complete,
                    "research_sufficiency": assessed.research_sufficiency,
                    "answer_mode": assessed.answer_mode,
                }
            )
            if refreshed != run:
                self.store.save_run(refreshed)
            contract = build_finalization_from_run(
                assessed,
                snapshot_receipts=self._snapshot_receipts_for_finalization(
                    assessed,
                    now=timestamp,
                ),
                now=timestamp,
            )
            return contract.model_dump(mode="json")

    def get_state(
        self,
        run_id: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        run = self._required_run(run_id)
        # Optional clock injection keeps state projections deterministic for
        # expiry-bound tests and provider adapters without weakening the
        # normal wall-clock freshness gate.
        timestamp = now or datetime.now(UTC)
        full_run, assessed = self._assessed_finalization_runs(run, now=timestamp)
        registered_plan = full_run.registered_plan
        assessment = evaluate_research_sufficiency(assessed)
        assessed_run = full_run.model_copy(
            update={
                "workflow_complete": assessment.workflow_complete,
                "research_sufficiency": assessment.research_sufficiency,
                "answer_mode": assessment.answer_mode,
            }
        )
        contract = build_finalization_from_run(
            assessed,
            snapshot_receipts=self._snapshot_receipts_for_finalization(
                assessed,
                now=timestamp,
            ),
            now=timestamp,
        )
        research_brief = self._research_brief(full_run, contract, now=timestamp)
        return {
            "schema_version": "alr-tw.research-state/v1",
            "run": assessed_run.model_dump(mode="json"),
            "source_count": len(self.store.list_sources(run_id)),
            "evidence_count": len(self.store.list_evidence(run_id)),
            "ready_for_draft": full_run.state == ResearchState.READY_FOR_DRAFT,
            "workflow_complete": assessment.workflow_complete,
            "research_sufficiency": assessment.research_sufficiency.value,
            # This is the final answer posture after snapshot/counter/evidence
            # gates.  Keep the pure sufficiency result separate so clients do
            # not see contradictory ``ordinary``/``conditional`` values.
            "answer_mode": contract.answer_mode.value,
            "research_answer_mode": assessment.answer_mode.value,
            "sufficiency_reasons": assessment.reason_codes,
            "finalization": self._finalization_summary(contract),
            "research_brief": research_brief,
            "awaiting_external_plan": (
                full_run.responsibility.discovery_mode is DiscoveryMode.CLIENT_ASSISTED
                and registered_plan is None
            ),
            "interoperability": {
                "responsibility": full_run.responsibility.model_dump(mode="json"),
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

    def get_evidence_bundle(
        self,
        run_id: str,
        *,
        max_sources: int = 12,
        max_judgment_sources: int = 5,
        max_spans_per_source: int = 8,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Return a bounded read-only view of server-verified source text."""

        if isinstance(max_sources, bool) or not 1 <= max_sources <= 16:
            raise ValueError("max_sources must be an integer between 1 and 16")
        if isinstance(max_judgment_sources, bool) or not 1 <= max_judgment_sources <= 5:
            raise ValueError("max_judgment_sources must be an integer between 1 and 5")
        if isinstance(max_spans_per_source, bool) or not 1 <= max_spans_per_source <= 10:
            raise ValueError("max_spans_per_source must be an integer between 1 and 10")
        run = self._required_run(run_id)
        timestamp = now or datetime.now(UTC)
        if run.expires_at <= timestamp:
            raise ValueError("RESEARCH_RUN_EXPIRED")
        evidence = self.store.list_evidence(run_id)
        evidence_by_source: dict[str, list[EvidenceSpan]] = {}
        for item in evidence:
            if item.eligible_for_claim_support:
                evidence_by_source.setdefault(item.source_id, []).append(item)
        eligible_sources = [
            source
            for source in self.store.list_sources(run_id)
            if source.trust_status is TrustStatus.EVIDENCE_ELIGIBLE
            and source.expires_at > timestamp
            and source.source_id in evidence_by_source
        ]
        material_priority = {
            MaterialType.LAW: 0,
            MaterialType.CONSTITUTIONAL: 1,
            MaterialType.JUDGMENT: 2,
        }
        eligible_sources.sort(
            key=lambda source: (
                material_priority.get(source.material_type, 9),
                source.citation,
                source.source_id,
            )
        )
        non_judgment_sources = [
            source
            for source in eligible_sources
            if source.material_type is not MaterialType.JUDGMENT
        ][:max_sources]
        judgment_budget = min(
            max_judgment_sources,
            max(0, max_sources - len(non_judgment_sources)),
        )
        selected_sources = [
            *non_judgment_sources,
            *[
                source
                for source in eligible_sources
                if source.material_type is MaterialType.JUDGMENT
            ][:judgment_budget],
        ]
        items: list[dict[str, Any]] = []
        for source in selected_sources:
            spans = sorted(
                evidence_by_source[source.source_id],
                key=lambda span: (
                    -_evidence_query_overlap(run.query, span.exact_text),
                    _evidence_section_priority(span.section_type),
                    span.section_id,
                ),
            )
            selected_spans = spans[:max_spans_per_source]
            items.append(
                {
                    "source": {
                        "source_id": source.source_id,
                        "material_type": source.material_type.value,
                        "provider_id": source.provider_id,
                        "source_tier": source.source_tier.value,
                        "trust_status": source.trust_status.value,
                        "citation": source.citation,
                        "official_identifier": source.official_identifier,
                        "official_url": source.official_url,
                        "verified_at": (
                            source.verified_at.isoformat()
                            if source.verified_at is not None
                            else None
                        ),
                        "content_hash": source.content_hash,
                    },
                    "evidence": [item.model_dump(mode="json") for item in selected_spans],
                    "omitted_evidence_count": len(spans) - len(selected_spans),
                }
            )
        return {
            "schema_version": "alr-tw.research-evidence-bundle/v1",
            "run_id": run_id,
            "status": "found" if items else "not_found_in_scope",
            "source_count": len(items),
            "available_source_count": len(eligible_sources),
            "truncated": len(eligible_sources) > len(selected_sources),
            "bounded_scope": (
                f"max_sources={max_sources};max_judgment_sources={max_judgment_sources};"
                f"max_spans_per_source={max_spans_per_source}"
            ),
            "global_absence_claim_allowed": False,
            "answer_authorized": False,
            "items": items,
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
                "evidence_ids": sorted(
                    item.evidence_id for item in self.store.list_evidence(run_id)
                ),
            }
        )
        run = self._refresh_sufficiency(run)
        self._sync_snapshot_receipts(run, now=datetime.now(UTC))
        self.store.save_run(run)
        return result

    def inspect_judgment_lineage(
        self,
        run_id: str,
        jid: str,
        operation_id: str,
        *,
        max_related_nodes: int = 8,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Inspect TLR history for one server-owned judgment and persist official nodes."""

        if not operation_id.strip():
            raise ValueError("operation_id is required")
        if not 1 <= max_related_nodes <= 20:
            raise ValueError("max_related_nodes must be between 1 and 20")
        with self._lock:
            run = self._required_run(run_id)
            timestamp = now or datetime.now(UTC)
            if run.expires_at <= timestamp:
                raise ValueError("RESEARCH_RUN_EXPIRED")
            operation = self.store.record_operation(
                run_id,
                operation_id,
                {"status": "in_progress"},
            )
            if not operation.created:
                return operation.result
            inspect = getattr(self.executor, "inspect_judgment_lineage", None)
            if callable(inspect):
                result = inspect(
                    run_id,
                    jid,
                    max_related_nodes=max_related_nodes,
                )
            else:
                result = {
                    "schema_version": "alr-tw.judgment-lineage-inspection/v1",
                    "status": "blocked",
                    "run_id": run_id,
                    "jid": jid,
                    "reason_codes": ["JUDGMENT_LINEAGE_EXECUTOR_UNAVAILABLE"],
                    "establishes_finality": False,
                    "semantic_opinion_comparison_performed": False,
                    "related_nodes": [],
                    "limitations": ["NO_UPPER_HISTORY_DOES_NOT_ESTABLISH_FINALITY"],
                }

            full_run = self._run_with_server_refs(run)
            limitations = set(full_run.coverage.limitations)
            limitations.update(str(item) for item in result.get("limitations", []))
            treatment = result.get("treatment_summary")
            if (
                isinstance(treatment, dict)
                and treatment.get("officially_confirmed_reversal") is True
            ):
                limitations.add("JUDGMENT_LINEAGE_CONFIRMED_REVERSAL")
                result["current_holding_use"] = "do_not_rely_as_current_holding"
            else:
                result["current_holding_use"] = "qualified_pending_substantive_review"
            if result.get("status") == "blocked":
                limitations.add("JUDGMENT_LINEAGE_CHECK_BLOCKED")
            full_run = full_run.model_copy(
                update={
                    "coverage": full_run.coverage.model_copy(
                        update={"limitations": sorted(limitations)}
                    ),
                    "updated_at": timestamp,
                }
            )
            full_run = self._refresh_sufficiency(full_run)
            self._sync_snapshot_receipts(
                full_run,
                now=now or datetime.now(UTC),
            )
            self.store.save_run(full_run)
            self.store.complete_operation(run_id, operation_id, result)
            return result

    def execute_run_to_completion(
        self,
        run_id: str,
        *,
        max_steps: int = 12,
        operation_prefix: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Advance server-owned obligations in one bounded, auditable call.

        The loop stops before final-answer validation because drafting remains
        external-client owned.  Retryable provider outcomes are returned
        immediately rather than being hammered inside the same request.
        """

        if isinstance(max_steps, bool) or not 1 <= max_steps <= 32:
            raise ValueError("max_steps must be an integer between 1 and 32")
        prefix = (operation_prefix or f"auto_{uuid4().hex}").strip()
        if not prefix:
            raise ValueError("operation_prefix must not be blank")

        with self._lock:
            execution_started = perf_counter()
            run = self._required_run(run_id)
            timestamp = now or datetime.now(UTC)
            if run.expires_at <= timestamp:
                raise ValueError("RESEARCH_RUN_EXPIRED")
            if (
                run.responsibility.discovery_mode is DiscoveryMode.CLIENT_ASSISTED
                and run.registered_plan is None
            ):
                state = self.get_state(run_id, now=timestamp)
                return {
                    "schema_version": "alr-tw.research-execution/v1",
                    "run_id": run_id,
                    "stop_reason": "awaiting_external_plan",
                    "step_count": 0,
                    "steps": [],
                    "elapsed_ms": round((perf_counter() - execution_started) * 1000, 3),
                    "state": state,
                    "finalization": state["finalization"],
                }

            steps: list[dict[str, Any]] = []
            stop_reason = "max_steps_reached"
            for index in range(max_steps):
                run = self._required_run(run_id)
                pending = [
                    item
                    for item in run.obligations
                    if item.status is ResearchObligationStatus.PENDING
                    and item.kind is not ResearchObligationKind.FINAL_ANSWER_VALIDATION
                ]
                if not pending:
                    stop_reason = "ready_for_draft"
                    break
                obligation = pending[0]
                step_started = perf_counter()
                step_result = self.continue_run(
                    run_id,
                    f"{prefix}.step-{index + 1}.{obligation.kind.value}",
                    now=now,
                )
                outcome = step_result.get("outcome")
                steps.append(
                    {
                        "obligation": obligation.kind.value,
                        "status": (outcome.get("status") if isinstance(outcome, dict) else None),
                        "retryable": bool(isinstance(outcome, dict) and outcome.get("retryable")),
                        "warnings": (
                            list(outcome.get("warnings", [])) if isinstance(outcome, dict) else []
                        ),
                        "provider_calls": (
                            list(outcome.get("provider_calls", []))
                            if isinstance(outcome, dict)
                            else []
                        ),
                        "elapsed_ms": round((perf_counter() - step_started) * 1000, 3),
                    }
                )
                if isinstance(outcome, dict) and outcome.get("retryable"):
                    stop_reason = "retry_required"
                    break
            else:
                run = self._required_run(run_id)
                if not any(
                    item.status is ResearchObligationStatus.PENDING
                    and item.kind is not ResearchObligationKind.FINAL_ANSWER_VALIDATION
                    for item in run.obligations
                ):
                    stop_reason = "ready_for_draft"

            projection_time = now or datetime.now(UTC)
            state = self.get_state(run_id, now=projection_time)
            result = {
                "schema_version": "alr-tw.research-execution/v1",
                "run_id": run_id,
                "stop_reason": stop_reason,
                "step_count": len(steps),
                "elapsed_ms": round((perf_counter() - execution_started) * 1000, 3),
                "steps": steps,
                "state": state,
                "finalization": state["finalization"],
            }
            if stop_reason == "ready_for_draft":
                result["evidence_bundle"] = self.get_evidence_bundle(
                    run_id,
                    max_sources=min(16, run.max_judgment_verifications + 7),
                    max_judgment_sources=run.max_judgment_verifications,
                    now=projection_time,
                )
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
            was_semantic_recall_degraded = run.semantic_recall_degraded
            previous_limitations = set(run.coverage.limitations)
            outcome = self.executor.execute(run, obligation)
            run_updates = outcome.pop("_run_updates", {})
            if not isinstance(run_updates, dict):
                raise TypeError("executor _run_updates must be a dictionary")
            if run_updates:
                run = run.model_copy(update=run_updates)
            recall_complete = (
                obligation.kind is ResearchObligationKind.JUDGMENT_RECALL
                and not run.judgment_recall_incomplete
            )
            demoted_recall_codes = _nonblocking_recall_codes(
                outcome,
                recall_complete=recall_complete,
            )
            retryable_codes = _retryable_outcome_codes(outcome)
            retryable_codes = _filter_optional_tlr_retry_codes(
                outcome,
                retryable_codes,
                recall_complete=recall_complete,
            )
            derived_limitations = {
                code
                for code in set(run.coverage.limitations) - previous_limitations
                if _is_retryable_derived_code(code)
            }
            if retryable_codes:
                retryable_codes = sorted(set(retryable_codes) | derived_limitations)
            # Provider updates may set a derived degradation flag alongside a
            # transient error.  Track it only when this obligation introduced
            # it, so a successful retry cannot erase an unrelated limitation.
            if (
                retryable_codes
                and not was_semantic_recall_degraded
                and any(
                    str(value).upper() == "SEMANTIC_RECALL_DEGRADED"
                    for value in outcome.get("warnings", [])
                )
            ):
                retryable_codes = sorted(
                    set(retryable_codes) | {"SEMANTIC_RECALL_DEGRADED"}
                )
            previous_retry_codes = set(obligation.retryable_reason_codes)
            counter_progress_payload: dict[str, Any] | None = None
            counter_diagnostic_codes: list[str] = []
            if obligation.kind is ResearchObligationKind.COUNTER_AUTHORITY:
                metadata = outcome.get("metadata")
                if isinstance(metadata, dict):
                    raw_progress = metadata.get("progress")
                    if isinstance(raw_progress, dict):
                        counter_progress_payload = CounterAuthorityProgress.model_validate(
                            raw_progress
                        ).model_dump(mode="json")
                    raw_diagnostics = metadata.get("reason_codes", [])
                    if isinstance(raw_diagnostics, list):
                        counter_diagnostic_codes = sorted(
                            {str(code) for code in raw_diagnostics if code}
                        )
                if counter_progress_payload is None:
                    counter_progress_payload = obligation.counter_authority_progress
            if retryable_codes:
                obligation_updates: dict[str, Any] = {
                    "status": ResearchObligationStatus.PENDING,
                    "reason": "retryable provider outcome; retry with a new operation_id",
                    "blocker_code": retryable_codes[0],
                    "retryable_reason_codes": retryable_codes,
                }
                if obligation.kind is ResearchObligationKind.COUNTER_AUTHORITY:
                    obligation_updates.update(
                        {
                            "counter_authority_progress": counter_progress_payload,
                            "counter_authority_diagnostic_codes": counter_diagnostic_codes,
                        }
                    )
                updated_obligation = obligation.model_copy(
                    update=obligation_updates,
                )
            else:
                obligation_updates = {
                    "status": ResearchObligationStatus.COMPLETED,
                    "reason": "",
                    "blocker_code": None,
                    "retryable_reason_codes": [],
                }
                if obligation.kind is ResearchObligationKind.COUNTER_AUTHORITY:
                    # Keep the full progress in the completed operation result
                    # for audit, but never let a later operation resume a
                    # terminal-clean/non-retryable obligation.
                    obligation_updates.update(
                        {
                            "counter_authority_progress": None,
                            "counter_authority_diagnostic_codes": [],
                        }
                    )
                updated_obligation = obligation.model_copy(
                    update=obligation_updates,
                )
            # These fields are server-owned diagnostics in the persisted
            # operation result; an executor cannot self-declare retryability.
            outcome["retryable"] = bool(retryable_codes)
            outcome["retry_reason_codes"] = retryable_codes
            obligations = [
                updated_obligation if item.kind == obligation.kind else item
                for item in run.obligations
            ]
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
            elif (
                not retryable_codes
                and obligation.kind
                in {
                    ResearchObligationKind.JUDGMENT_OFFICIAL_VERIFICATION,
                    ResearchObligationKind.EVIDENCE_SUFFICIENCY,
                }
                and run.state == ResearchState.RESEARCHING
            ):
                run = transition_run(run, ResearchState.VERIFYING, updated_at=timestamp)
            run = self._apply_outcome_coverage(
                run,
                outcome,
                clear_codes=(
                    previous_retry_codes
                    | (
                        set(obligation.counter_authority_diagnostic_codes)
                        if obligation.kind is ResearchObligationKind.COUNTER_AUTHORITY
                        else set()
                    )
                ),
                demote_codes=demoted_recall_codes,
            )
            if not retryable_codes and "SEMANTIC_RECALL_DEGRADED" in previous_retry_codes:
                restore_updates: dict[str, Any] = {"semantic_recall_degraded": False}
                if run.requested_mode is DataMode.HYBRID_VERIFIED and run.privacy_status in {
                    PrivacyStatus.SAFE,
                    PrivacyStatus.REDACTED_SAFE,
                }:
                    restore_updates["effective_mode"] = run.requested_mode
                run = run.model_copy(update=restore_updates)
            run = self._refresh_sufficiency(run)
            self._sync_snapshot_receipts(
                run,
                now=now or datetime.now(UTC),
            )
            self.store.save_run(run)
            result = self._result(run, outcome, replayed=False)
            self.store.complete_operation(run_id, operation_id, result)
            return result

    @staticmethod
    def _apply_outcome_coverage(
        run: ResearchRun,
        outcome: dict[str, Any],
        *,
        clear_codes: set[str] | frozenset[str] = frozenset(),
        demote_codes: set[str] | frozenset[str] = frozenset(),
    ) -> ResearchRun:
        """Merge executor diagnostics into the server-owned coverage receipt."""

        partial, errors, timeouts = _outcome_reason_codes(outcome)
        demoted = set(demote_codes)
        partial = sorted(set(partial).union(demoted))
        errors = sorted(set(errors) - demoted)
        timeouts = sorted(set(timeouts) - demoted)
        coverage = run.coverage
        cleared = set(clear_codes)
        selected = set(coverage.selected_provider_scope)
        successful = set(coverage.successful_provider_scope)
        for call in outcome.get("provider_calls", []):
            if not isinstance(call, dict):
                continue
            provider_id = call.get("provider_id")
            if not provider_id:
                continue
            provider_id = str(provider_id)
            selected.add(provider_id)
            if call.get("status") in {"found", "not_found", "partial"}:
                successful.add(provider_id)
        updates = {
            "limitations": sorted(set(coverage.limitations) - cleared),
            "partial_reason_codes": sorted(
                (set(coverage.partial_reason_codes) - cleared).union(partial)
            ),
            "error_reason_codes": sorted(
                (set(coverage.error_reason_codes) - cleared).union(errors)
            ),
            "timeout_reason_codes": sorted(
                (set(coverage.timeout_reason_codes) - cleared).union(timeouts)
            ),
            "selected_provider_scope": sorted(selected),
            "successful_provider_scope": sorted(successful),
        }
        return run.model_copy(update={"coverage": coverage.model_copy(update=updates)})

    @staticmethod
    def _refresh_sufficiency(run: ResearchRun) -> ResearchRun:
        """Recompute server-owned status fields after every research step."""

        workflow_complete = evaluate_research_sufficiency(run).workflow_complete
        coverage = run.coverage
        coverage_complete = (
            workflow_complete
            and run.evidence_ids
            and _required_coverage_complete(run)
            and not coverage.limitations
            and not coverage.partial_reason_codes
            and not coverage.error_reason_codes
            and not coverage.timeout_reason_codes
            and not run.semantic_recall_degraded
            and not run.judgment_recall_incomplete
        )
        if coverage.coverage_complete != bool(coverage_complete):
            coverage = coverage.model_copy(
                update={"coverage_complete": bool(coverage_complete)}
            )
        absence_claim_allowed = bool(
            coverage.coverage_complete
            and coverage.counter_authority_checked
            and coverage.bounded_query_scope
            and coverage.bounded_query_scope.strip()
            and bool(coverage.selected_provider_scope)
            and set(coverage.selected_provider_scope).issubset(
                set(coverage.successful_provider_scope)
            )
            and not coverage.limitations
            and not coverage.partial_reason_codes
            and not coverage.error_reason_codes
            and not coverage.timeout_reason_codes
        )
        if coverage.absence_claim_allowed != absence_claim_allowed:
            coverage = coverage.model_copy(
                update={"absence_claim_allowed": absence_claim_allowed}
            )
        if coverage != run.coverage:
            # Re-run the receipt validator after deriving the bounded absence
            # capability; model_copy itself intentionally skips validation.
            coverage = CoverageState.model_validate(coverage.model_dump(mode="python"))
            run = run.model_copy(update={"coverage": coverage})
        assessment = evaluate_research_sufficiency(run)
        return run.model_copy(
            update={
                "workflow_complete": assessment.workflow_complete,
                "research_sufficiency": assessment.research_sufficiency,
                "answer_mode": assessment.answer_mode,
            }
        )

    def validate_legal_analysis(
        self,
        run_id: str,
        operation_id: str,
        analysis: LegalAnalysisEnvelope,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Validate an untrusted multi-branch analysis against server-owned state."""

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
                as_of_date=run.as_of_date or timestamp.astimezone(TAIWAN_TIME).date(),
                assessed_at=timestamp,
            )
            validation = run_legal_analysis_validation(
                analysis,
                server_sources=sources,
                server_evidence=evidence,
                legal_context=legal_context,
                server_run_id=run_id,
                validated_at=timestamp,
            )
            receipts = validation.counter_authority_relation_receipts
            for receipt in receipts:
                self.store.save_counter_authority_relation_receipt(receipt)

            opposing_receipts = [
                receipt
                for receipt in receipts
                if receipt.relation is CounterAuthorityRelation.OPPOSING
            ]
            counter_status = run.coverage.counter_authority_status
            if receipts:
                coverage = run.coverage.model_copy(
                    update={
                        "counter_authority_relation_receipt_ids": sorted(
                            {
                                *run.coverage.counter_authority_relation_receipt_ids,
                                *(receipt.receipt_id for receipt in receipts),
                            }
                        ),
                    }
                )
                run = run.model_copy(update={"coverage": coverage, "updated_at": timestamp})
            if opposing_receipts:
                counter_status = "found_verified"
                classified_codes = {
                    "COUNTER_AUTHORITY_RELATION_UNCLASSIFIED",
                    "COUNTER_AUTHORITY_PARTIAL",
                }
                coverage = run.coverage.model_copy(
                    update={
                        "counter_authority_checked": True,
                        "counter_authority_status": counter_status,
                        "limitations": sorted(
                            set(run.coverage.limitations) - classified_codes
                        ),
                        "partial_reason_codes": sorted(
                            set(run.coverage.partial_reason_codes) - classified_codes
                        ),
                        "receipt_reference": opposing_receipts[0].receipt_id,
                    }
                )
                run = self._refresh_sufficiency(
                    run.model_copy(update={"coverage": coverage, "updated_at": timestamp})
                )
            if receipts:
                self.store.save_run(run)
            result = {
                **validation.model_dump(mode="json"),
                "run_id": run_id,
                "counter_authority_status": counter_status,
                "counter_authority_coverage": (
                    "complete"
                    if (
                        run.coverage.counter_authority_coverage_complete
                        if run.coverage.counter_authority_coverage_complete is not None
                        else run.coverage.coverage_complete
                    )
                    else "partial"
                ),
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
            full_run, assessed = self._assessed_finalization_runs(run, now=timestamp)
            run = full_run.model_copy(
                update={
                    "workflow_complete": assessed.workflow_complete,
                    "research_sufficiency": assessed.research_sufficiency,
                    "answer_mode": assessed.answer_mode,
                }
            )
            finalization = build_finalization_from_run(
                assessed,
                snapshot_receipts=self._snapshot_receipts_for_finalization(
                    assessed,
                    now=timestamp,
                ),
                now=timestamp,
            )
            claim = self.store.record_operation(
                run_id,
                operation_id,
                {"status": "in_progress"},
            )
            if not claim.created:
                return claim.result
            if finalization.answer_mode.value == "refusal_only":
                finalization = self._refusal_contract(finalization)
                terminal_refusal = self._terminal_refusal(run, finalization)
                persisted = self._persist_refusal_decision(
                    run,
                    finalization,
                    timestamp=timestamp,
                )
                refusal = build_structured_refusal(finalization)
                result = {
                    "schema_version": "alr-tw.answer-validation/v4",
                    "run_id": run_id,
                    "decision": ResearchState.BLOCKED.value,
                    "decision_code": "ANSWER_REFUSAL_ONLY",
                    "safe_to_present": False,
                    "answer_text": None,
                    "required_qualification": finalization.required_qualification,
                    "structured_refusal": refusal.model_dump(mode="json"),
                    "claim_support": [],
                    "semantic_summary": None,
                    "verification_method": "finalization_gate",
                    "semantic_entailment_performed": False,
                    "binding_mode": "not_executed",
                    "issue_coverage": None,
                    "privacy": None,
                    "coverage_summary": persisted.coverage.model_dump(mode="json"),
                    "blockers": [item.code for item in finalization.blockers],
                    "effective_mode": run.effective_mode.value,
                    "citations": [],
                    "finalization": finalization.model_dump(mode="json"),
                }
                self.store.complete_operation(run_id, operation_id, result)
                if terminal_refusal and persisted.ephemeral:
                    self.store.purge_run(run_id)
                    result["storage_purged"] = True
                return result
            if run.state != ResearchState.READY_FOR_DRAFT:
                finalization = self._refusal_contract(
                    finalization,
                    extra_blocker=FinalizationBlocker(
                        code="RESEARCH_OBLIGATION_PENDING",
                        message="研究流程尚未到可驗證階段。",
                        retryable=True,
                    ),
                )
                terminal_refusal = self._terminal_refusal(run, finalization)
                persisted = self._persist_refusal_decision(
                    run,
                    finalization,
                    timestamp=timestamp,
                )
                result = {
                    "schema_version": "alr-tw.answer-validation/v4",
                    "run_id": run_id,
                    "decision": ResearchState.BLOCKED.value,
                    "decision_code": "ANSWER_RESEARCH_STATE_NOT_READY",
                    "safe_to_present": False,
                    "answer_text": None,
                    "required_qualification": finalization.required_qualification,
                    "structured_refusal": build_structured_refusal(finalization).model_dump(
                        mode="json"
                    ),
                    "coverage_summary": persisted.coverage.model_dump(mode="json"),
                    "blockers": [item.code for item in finalization.blockers],
                    "citations": [],
                    "effective_mode": persisted.effective_mode.value,
                    "verification_method": "finalization_gate",
                    "semantic_entailment_performed": False,
                    "binding_mode": "not_executed",
                    "issue_coverage": None,
                    "privacy": None,
                    "finalization": finalization.model_dump(mode="json"),
                }
                self.store.complete_operation(run_id, operation_id, result)
                if terminal_refusal and persisted.ephemeral:
                    self.store.purge_run(run_id)
                    result["storage_purged"] = True
                return result
            bindings = [
                item if isinstance(item, ClaimBinding) else ClaimBinding.model_validate(item)
                for item in (claim_bindings or [])
            ]
            claims = _claims_for_validation(answer_text, bindings)
            answer_privacy = screen_answer_output(answer_text)
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
            finalization_qualified = finalization.answer_mode.value == "conditional"
            if safe and (
                coverage_qualified
                or finalization_qualified
                or binding_mode == "legacy_unbound"
            ):
                decision = ResearchState.QUALIFIED
                if finalization_qualified and finalization.required_qualification:
                    qualification = list(finalization.required_qualification)
                    if binding_mode == "legacy_unbound":
                        qualification.extend(
                            item
                            for item in (
                                "claim_bindings",
                                "未提供 claim_bindings；本結果僅為舊版相容驗證，"
                                "不得將其視為核心法律主張已完成 span-level 驗證。",
                            )
                            if item not in qualification
                        )
                elif binding_mode == "legacy_unbound":
                    qualification = [
                        "claim_bindings",
                        "未提供 claim_bindings；本結果僅為舊版相容驗證，"
                        "不得將其視為核心法律主張已完成 span-level 驗證。",
                    ]
                else:
                    qualification = [_coverage_qualification(run)]
            elif safe:
                decision = ResearchState.VALIDATED
                qualification = []
            else:
                decision = ResearchState.BLOCKED
                qualification = []
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
                "schema_version": "alr-tw.answer-validation/v4",
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
                "finalization": finalization.model_dump(mode="json"),
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
