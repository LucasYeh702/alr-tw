"""Provider-backed execution of one server-owned research obligation."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Coroutine, TypeVar
from urllib.parse import parse_qs, unquote, urlsplit

from alr_tw.contracts.providers import (
    CandidateRecallProvider,
    CandidatePrivacyDecision,
    CandidateIdentity,
    DataMode,
    LineageCandidateProvider,
    ProviderCandidate,
    ProviderErrorCode,
    ProviderResult,
    ProviderResultStatus,
)
from alr_tw.contracts.authority_lineage import NegativeTreatmentStatus
from alr_tw.contracts.interop import AuthorityLocatorProposal, DiscoveryMode
from alr_tw.contracts.research import (
    PrivacyStatus,
    ResearchDepth,
    ResearchObligation,
    ResearchObligationKind,
    ResearchRun,
)
from alr_tw.contracts.sources import (
    EvidenceSpan,
    MaterialType,
    SourceRecord,
    SourceTier,
    TrustStatus,
)
from alr_tw.providers.local_portal import JudgmentProviderPort
from alr_tw.providers.official import (
    OfficialConstitutionalProvider,
    OfficialJudgmentProvider,
    OfficialLawProvider,
)
from alr_tw.providers.tlr import (
    TlrCaseHistoryRecord,
    TlrSemanticRecallProvider,
    screen_external_query,
)
from alr_tw.research.judgment_identity import (
    ResolvedJudgmentIdentity,
    direct_judgment_identity,
    rank_and_dedupe_judgment_identities,
    resolve_judgment_candidate,
)
from alr_tw.research.judgment_lineage import (
    VerifiedLineageSource,
    build_lineage_contract,
    disposition_codes,
    evidence_summary,
    verified_node_payload,
)
from alr_tw.research.counter_authority import (
    CounterAuthorityStatus,
    CounterAuthorityVerification,
    CounterAuthorityProgress,
    build_counter_authority_plan,
    execute_bounded_counter_authority,
)
from alr_tw.storage.sqlite_store import SqliteStore

_T = TypeVar("_T")
_LAW_CITATION = re.compile(
    r"(?P<law>[\u4e00-\u9fff]{1,30}(?:法|條例|規則|辦法))第\s*"
    r"(?P<article>\d+(?:\s*(?:之|-)\s*\d+)*)\s*條"
)
_JID = re.compile(
    r"(?P<jid>[A-Z0-9]{3,12},[^,\r\n]{1,80},[^,\r\n]{1,80},"
    r"\d+,\d{8},\d+)"
)
_FORMAL_JUDGMENT_CITATION = re.compile(
    r"(?P<citation>[\u4e00-\u9fff]{2,24}法院\s*\d{1,3}\s*年度\s*"
    r"[^,，。；;\r\n]{1,20}?字\s*第\s*\d{1,12}\s*號"
    r"(?:(?:民事|刑事|行政|懲戒)(?:判決|裁定)?)?)"
)


def _run(coroutine: Coroutine[Any, Any, _T]) -> _T:
    """Run provider coroutine from the synchronous stdio research service."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    raise RuntimeError("SYNC_RESEARCH_SERVICE_CALLED_FROM_ASYNC_LOOP")


def _compact_identifier(value: str) -> str:
    return re.sub(r"[\s　]+", "", value)


@dataclass(frozen=True)
class ProviderSet:
    laws: OfficialLawProvider
    constitutional: OfficialConstitutionalProvider
    judgments: JudgmentProviderPort
    candidate_recall: CandidateRecallProvider | None = None
    lineage_candidates: LineageCandidateProvider | None = None
    # Deprecated compatibility slot for v0.11 constructors.  New deployments
    # inject provider-neutral candidate ports above.
    tlr: TlrSemanticRecallProvider | None = None

    @property
    def candidate_recall_provider(self) -> CandidateRecallProvider | None:
        return self.candidate_recall or self.tlr

    @property
    def lineage_candidate_provider(self) -> LineageCandidateProvider | None:
        if self.lineage_candidates is not None:
            return self.lineage_candidates
        if isinstance(self.candidate_recall, LineageCandidateProvider):
            return self.candidate_recall
        return self.tlr


class ProviderObligationExecutor:
    def __init__(self, store: SqliteStore, providers: ProviderSet):
        self.store = store
        self.providers = providers

    def execute(
        self,
        run: ResearchRun,
        obligation: ResearchObligation,
    ) -> dict[str, Any]:
        handlers = {
            ResearchObligationKind.QUERY_UNDERSTANDING: self._understand,
            ResearchObligationKind.PRIVACY_SCREEN: self._privacy,
            ResearchObligationKind.LAW_RESEARCH: self._laws,
            ResearchObligationKind.JUDGMENT_RECALL: self._judgment_recall,
            ResearchObligationKind.JUDGMENT_OFFICIAL_VERIFICATION: self._verify_judgment,
            ResearchObligationKind.CONSTITUTIONAL_RESEARCH: self._constitutional,
            ResearchObligationKind.COUNTER_AUTHORITY: self._counter_authority,
            ResearchObligationKind.LEGAL_TIME_CONTEXT: self._time_context,
            ResearchObligationKind.EVIDENCE_SUFFICIENCY: self._sufficiency,
        }
        handler = handlers.get(obligation.kind)
        if handler is None:
            return self._outcome(obligation, warnings=["OBLIGATION_HAS_NO_PROVIDER_ACTION"])
        return handler(run, obligation)

    def lookup(self, text: str, *, run_id: str | None = None) -> dict[str, Any]:
        law_citations = _run(self.providers.laws.resolve_citations(text, limit=1))
        if law_citations:
            law_name, article_no = law_citations[0]

            def fetch() -> tuple[ProviderResult, SourceRecord | None, EvidenceSpan | None]:
                return _run(self.providers.laws.exact_lookup(law_name, article_no))

            result, source, evidence_items = self._cached_lookup(
                run_id,
                f"law:{law_name.strip()}:{article_no.strip()}",
                fetch,
                expected_provider_id=self.providers.laws.provider_id,
            )
        else:
            jid = self._jid_from_text(text)
            formal_citation = self._formal_citation_from_text(text)
            constitutional = self.providers.constitutional.normalize_identifier(text)
            if jid:
                result, source, evidence_items = self._cached_lookup(
                    run_id,
                    f"judgment:{jid}",
                    lambda: _run(self.providers.judgments.exact_lookup(jid)),
                    expected_provider_id=self.providers.judgments.provider_id,
                )
            elif formal_citation:
                result, source, evidence_items = self._cached_lookup(
                    run_id,
                    f"judgment-formal:{_compact_identifier(formal_citation)}",
                    lambda: _run(self.providers.judgments.exact_lookup(formal_citation)),
                    expected_provider_id=self.providers.judgments.provider_id,
                )
            elif constitutional:
                result, source, evidence_items = self._cached_lookup(
                    run_id,
                    f"constitutional:{constitutional}",
                    lambda: _run(self.providers.constitutional.exact_lookup(constitutional)),
                    expected_provider_id=self.providers.constitutional.provider_id,
                )
            else:
                return {
                    "schema_version": "alr-tw.legal-source-lookup/v1",
                    "status": "error",
                    "error_code": "INVALID_IDENTIFIER",
                    "claim_verified": False,
                }
        return {
            "schema_version": "alr-tw.legal-source-lookup/v1",
            "status": result.status.value,
            "error_code": result.error_code.value if result.error_code else None,
            "source": source.model_dump(mode="json") if source is not None else None,
            "evidence": [item.model_dump(mode="json") for item in evidence_items],
            "claim_verified": False,
        }

    def inspect_judgment_lineage(
        self,
        run_id: str,
        jid: str,
        *,
        max_related_nodes: int = 8,
    ) -> dict[str, Any]:
        """Inspect one verified judgment's TLR history and verify related nodes officially."""

        normalized_jid = OfficialJudgmentProvider.normalize_jid(jid)
        if normalized_jid is None:
            return self._lineage_blocked(jid, "INVALID_IDENTIFIER")
        if not 1 <= max_related_nodes <= 20:
            raise ValueError("max_related_nodes must be between 1 and 20")

        run_sources = self.store.list_sources(run_id)
        root_source = self._lineage_root_source(run_sources, normalized_jid)
        if root_source is None:
            return self._lineage_blocked(
                normalized_jid,
                "JUDGMENT_LINEAGE_ROOT_SOURCE_NOT_IN_RUN",
            )
        now = datetime.now(UTC)
        if root_source.expires_at <= now:
            return self._lineage_blocked(normalized_jid, "JUDGMENT_LINEAGE_ROOT_SOURCE_STALE")
        if self.providers.lineage_candidate_provider is None:
            return self._lineage_blocked(
                normalized_jid,
                "LINEAGE_CANDIDATE_PROVIDER_UNAVAILABLE",
            )

        candidates = self.store.list_candidates(run_id)
        origin_candidate_id = root_source.metadata.get("origin_candidate_id")
        candidate = self._lineage_candidate(
            candidates,
            normalized_jid,
            preferred_candidate_id=(
                str(origin_candidate_id) if isinstance(origin_candidate_id, str) else None
            ),
        )
        provider_calls: list[dict[str, Any]] = []
        history_result, history = self._fetch_lineage_history(
            root_source,
            normalized_jid,
            candidate,
            provider_calls,
        )
        if history is None:
            error_code = (
                history_result.error_code.value
                if history_result.error_code is not None
                else "TLR_CASE_HISTORY_UNAVAILABLE"
            )
            return {
                **self._lineage_blocked(normalized_jid, error_code),
                "provider_calls": provider_calls,
            }
        if history.root_canonical_jid not in {None, normalized_jid}:
            return {
                **self._lineage_blocked(normalized_jid, "TLR_CASE_HISTORY_ROOT_MISMATCH"),
                "provider_calls": provider_calls,
            }

        root_evidence = tuple(
            item
            for item in self.store.list_evidence(run_id)
            if item.source_id == root_source.source_id
        )
        selected_entries = list(history.entries[:max_related_nodes])
        truncated = len(history.entries) > len(selected_entries)
        verified: list[VerifiedLineageSource] = []
        verified_identities: dict[str, str] = {}
        verification_by_doc_id: dict[str, dict[str, Any]] = {}
        for entry in selected_entries:
            identifier = entry.canonical_jid or entry.provider_document_id

            def fetch_related(
                identifier: str = identifier,
            ) -> tuple[ProviderResult, SourceRecord | None, list[EvidenceSpan]]:
                return _run(self.providers.judgments.exact_lookup(identifier))

            result, source, evidence = fetch_related()
            provider_calls.append(self._provider_call(result))
            verification_error = self._lineage_verification_error(
                result,
                source,
                evidence,
                entry.provider_document_id,
                root_jid=normalized_jid,
                now=now,
                expected_provider_id=self.providers.judgments.provider_id,
            )
            if verification_error is None and source is not None:
                identity_key = (
                    OfficialJudgmentProvider.normalize_jid(
                        source.official_identifier or ""
                    )
                    or source.source_id
                )
                previous_direction = verified_identities.get(identity_key)
                if previous_direction is not None:
                    verification_error = (
                        "JUDGMENT_LINEAGE_OFFICIAL_DIRECTION_CONFLICT"
                        if previous_direction != entry.direction
                        else "JUDGMENT_LINEAGE_DUPLICATE_OFFICIAL_IDENTITY"
                    )
            if verification_error is not None or source is None:
                verification_by_doc_id[entry.provider_document_id] = {
                    "direction": entry.direction,
                    "provider_history": entry.model_dump(mode="json"),
                    "official_verification_status": "failed",
                    "error_code": verification_error,
                    "disposition_codes": [],
                    "all_evidence_ids": [],
                    "disposition_evidence_ids": [],
                    "court_view_evidence_ids": [],
                }
                continue
            verified_identities[identity_key] = entry.direction
            self.store.save_source(run_id, source)
            for evidence_item in evidence:
                self.store.save_evidence(run_id, evidence_item)
            item = VerifiedLineageSource(
                history=entry,
                source=source,
                evidence=tuple(evidence),
            )
            verified.append(item)
            verification_by_doc_id[entry.provider_document_id] = verified_node_payload(
                entry,
                source,
                evidence,
            )

        related_nodes: list[dict[str, Any]] = []
        for entry in history.entries:
            payload = verification_by_doc_id.get(entry.provider_document_id)
            if payload is None:
                payload = {
                    "direction": entry.direction,
                    "provider_history": entry.model_dump(mode="json"),
                    "official_verification_status": "not_attempted_budget",
                    "error_code": "JUDGMENT_LINEAGE_VERIFICATION_BUDGET_TRUNCATED",
                    "disposition_codes": [],
                    "all_evidence_ids": [],
                    "disposition_evidence_ids": [],
                    "court_view_evidence_ids": [],
                }
            related_nodes.append(payload)

        contract, validation = build_lineage_contract(
            run_id=run_id,
            root_source=root_source,
            root_evidence=root_evidence,
            history=history,
            related=verified,
            max_related_nodes=max_related_nodes,
        )
        limitations = list(contract.limitations)
        failed_count = len(selected_entries) - len(verified)
        if failed_count:
            limitations.append("JUDGMENT_LINEAGE_OFFICIAL_VERIFICATION_INCOMPLETE")
        if truncated:
            limitations.append("JUDGMENT_LINEAGE_VERIFICATION_BUDGET_TRUNCATED")
        verified_upper_dispositions = sorted(
            {
                code
                for item in verified
                if item.history.direction == "upper"
                for code in disposition_codes(item.source, item.evidence)
                if code != "unknown"
            }
        )
        return {
            "schema_version": "alr-tw.judgment-lineage-inspection/v1",
            "status": "qualified",
            "run_id": run_id,
            "jid": normalized_jid,
            "root": {
                "source_id": root_source.source_id,
                "official_identifier": root_source.official_identifier,
                "citation": root_source.citation,
                "official_url": root_source.official_url,
                "disposition_codes": disposition_codes(root_source, root_evidence),
                **evidence_summary(root_evidence),
            },
            "provider_history": history.model_dump(mode="json"),
            "related_nodes": related_nodes,
            "authority_lineage": contract.model_dump(mode="json"),
            "authority_lineage_validation": validation,
            "treatment_summary": {
                "upper_record_count": sum(
                    item.direction == "upper" for item in history.entries
                ),
                "lower_record_count": sum(
                    item.direction == "lower" for item in history.entries
                ),
                "upper_vacated_marker_count": sum(
                    item.direction == "upper" and item.vacated_marker
                    for item in history.entries
                ),
                "official_upper_disposition_codes": verified_upper_dispositions,
                "officially_verified_appeal_dismissal": (
                    "appeal_dismissed" in verified_upper_dispositions
                ),
                "officially_verified_affirmance": (
                    "affirmed" in verified_upper_dispositions
                ),
                "officially_confirmed_reversal": any(
                    record.status is NegativeTreatmentStatus.REVERSED
                    for record in contract.negative_treatments
                ),
                "establishes_finality": False,
            },
            "official_verified_related_count": len(verified),
            "official_verification_failed_count": failed_count,
            "history_entry_count": len(history.entries),
            "truncated": truncated,
            "max_related_nodes": max_related_nodes,
            "establishes_finality": False,
            "semantic_opinion_comparison_performed": False,
            "provider_calls": provider_calls,
            "limitations": sorted(set(limitations)),
        }

    @staticmethod
    def _plan_locators(
        run: ResearchRun,
        material_type: MaterialType,
    ) -> list[AuthorityLocatorProposal]:
        if run.registered_plan is None:
            return []
        return [
            item
            for item in run.registered_plan.proposal.authority_locators
            if item.material_type is material_type
        ]

    def _understand(self, run: ResearchRun, obligation: ResearchObligation) -> dict[str, Any]:
        return self._outcome(
            obligation,
            metadata={
                "law_citations": [match.group(0) for match in _LAW_CITATION.finditer(run.query)],
                "constitutional_identifier": (
                    self.providers.constitutional.normalize_identifier(run.query)
                ),
                "jid_present": self._jid_from_text(run.query) is not None,
                "formal_judgment_citation": self._formal_citation_from_text(run.query),
                "discovery_mode": run.responsibility.discovery_mode.value,
                "registered_plan_id": (
                    run.registered_plan.proposal.plan_id
                    if run.registered_plan is not None
                    else None
                ),
            },
        )

    def _privacy(self, run: ResearchRun, obligation: ResearchObligation) -> dict[str, Any]:
        decision = screen_external_query(run.query)
        updates: dict[str, Any] = {"privacy_status": decision.status}
        warnings: list[str] = []
        if not decision.allowed:
            updates.update(
                {
                    "effective_mode": DataMode.OFFICIAL_ONLY,
                    "semantic_recall_degraded": True,
                }
            )
            warnings.append("PRIVACY_EXTERNAL_QUERY_BLOCKED")
        return self._outcome(
            obligation,
            warnings=warnings,
            metadata=decision.model_dump(mode="json", exclude={"query_to_send"}),
            updates=updates,
        )

    def _laws(self, run: ResearchRun, obligation: ResearchObligation) -> dict[str, Any]:
        calls: list[dict[str, Any]] = []
        warnings: list[str] = []
        added_sources = 0
        added_evidence = 0
        plan_locators = self._plan_locators(run, MaterialType.LAW)
        client_assisted = run.responsibility.discovery_mode is DiscoveryMode.CLIENT_ASSISTED
        lookup_texts = (
            [item.lookup_text for item in plan_locators] if client_assisted else [run.query]
        )
        citations: list[tuple[str, str]] = []
        for lookup_text in lookup_texts:
            citations.extend(_run(self.providers.laws.resolve_citations(lookup_text, limit=5)))
        citations = list(dict.fromkeys(citations))
        if citations:
            for law_name, article_no in citations:

                def fetch_law(
                    law_name: str = law_name,
                    article_no: str = article_no,
                ) -> tuple[ProviderResult, SourceRecord | None, EvidenceSpan | None]:
                    return _run(self.providers.laws.exact_lookup(law_name, article_no))

                result, source, evidence_items = self._cached_lookup(
                    run.run_id,
                    f"law:{law_name.strip()}:{article_no.strip()}",
                    fetch_law,
                    expected_provider_id=self.providers.laws.provider_id,
                )
                calls.append(self._provider_call(result))
                if source is not None:
                    added_sources += 1
                added_evidence += sum(item.eligible_for_claim_support for item in evidence_items)
                if result.status != ProviderResultStatus.FOUND:
                    warnings.append(result.error_code.value if result.error_code else result.status.value)
        else:
            if client_assisted:
                warnings.append("CLIENT_ASSISTED_LAW_LOCATOR_UNRESOLVED")
            else:
                result = _run(self.providers.laws.search(run.query, limit=10))
                calls.append(self._provider_call(result))
                warnings.append("LAW_KEYWORD_RESULTS_REQUIRE_EXACT_LOOKUP")
        limitations = list(run.coverage.limitations)
        if not citations:
            limitations.append(
                "CLIENT_ASSISTED_LAW_LOCATOR_UNRESOLVED"
                if client_assisted
                else "LAW_KEYWORD_RESULTS_REQUIRE_EXACT_LOOKUP"
            )
        elif added_evidence == 0:
            limitations.append("LAW_OFFICIAL_VERIFICATION_INCOMPLETE")
        coverage = run.coverage.model_copy(
            update={
                "law_checked": added_evidence > 0,
                "limitations": sorted(set(limitations)),
            }
        )
        return self._outcome(
            obligation,
            calls=calls,
            warnings=warnings,
            added_sources=added_sources,
            added_evidence=added_evidence,
            metadata={
                "discovery_mode": run.responsibility.discovery_mode.value,
                "registered_locator_count": len(plan_locators),
                "resolved_citation_count": len(citations),
            },
            updates={"coverage": coverage},
        )

    def _judgment_recall(
        self,
        run: ResearchRun,
        obligation: ResearchObligation,
    ) -> dict[str, Any]:
        if run.responsibility.discovery_mode is DiscoveryMode.CLIENT_ASSISTED:
            registered_plan = run.registered_plan
            if registered_plan is None:
                return self._outcome(
                    obligation,
                    warnings=["EXTERNAL_RESEARCH_PLAN_REQUIRED"],
                    updates={"judgment_recall_incomplete": True},
                )
            locators = self._plan_locators(run, MaterialType.JUDGMENT)
            client_warnings: list[str] = []
            for rank, locator in enumerate(locators, start=1):
                lookup_text = locator.lookup_text
                canonical_jid = OfficialJudgmentProvider.normalize_jid(lookup_text)
                formal_citation = self._formal_citation_from_text(lookup_text)
                candidate = ProviderCandidate(
                    candidate_id=(
                        f"external-plan:{registered_plan.proposal.plan_id}:{locator.locator_id}"
                    ),
                    provider_id="external_research_plan",
                    title=locator.citation,
                    official_identifier=lookup_text,
                    identity=CandidateIdentity(
                        canonical_jid=canonical_jid,
                        provider_document_id=lookup_text,
                        formal_citation=formal_citation,
                    ),
                    candidate_rank=rank,
                    metadata={
                        "plan_id": registered_plan.proposal.plan_id,
                        "locator_id": locator.locator_id,
                        "purpose": locator.purpose.value,
                        "candidate_only": True,
                    },
                )
                self.store.save_candidate(
                    run.run_id,
                    candidate,
                    expires_at=run.expires_at,
                )
            if locators:
                client_warnings.append("CLIENT_AUTHORITY_LOCATORS_CANDIDATE_ONLY")
            else:
                client_warnings.append("CLIENT_ASSISTED_JUDGMENT_LOCATOR_MISSING")
            incomplete = not locators
            return self._outcome(
                obligation,
                warnings=client_warnings,
                added_candidates=len(locators),
                metadata={
                    "discovery_mode": DiscoveryMode.CLIENT_ASSISTED.value,
                    "registered_locator_count": len(locators),
                    "provider_search_skipped": True,
                },
                updates={"judgment_recall_incomplete": incomplete},
            )
        if (
            self._jid_from_text(run.query) is not None
            or self._formal_citation_from_text(run.query) is not None
        ):
            return self._outcome(
                obligation,
                warnings=["EXACT_JUDGMENT_IDENTIFIER_WILL_USE_OFFICIAL_PROVIDER"],
            )
        calls: list[dict[str, Any]] = []
        warnings: list[str] = []
        added_sources = 0
        added_candidates = 0
        usable_candidate_count = 0
        updates: dict[str, Any] = {}
        candidate_provider = self.providers.candidate_recall_provider

        def recall_official() -> None:
            nonlocal added_candidates, usable_candidate_count
            official = _run(self.providers.judgments.search(run.query, limit=5))
            calls.append(self._provider_call(official))
            provider_matches = official.provider_id == self.providers.judgments.provider_id
            accepted = [
                candidate
                for candidate in official.candidates[:5]
                if candidate.provider_id == self.providers.judgments.provider_id
            ]
            if (
                official.status == ProviderResultStatus.FOUND
                and official.error_code is None
                and provider_matches
                and len(accepted) == len(official.candidates)
            ):
                for candidate in accepted:
                    self.store.save_candidate(run.run_id, candidate, expires_at=run.expires_at)
                added_candidates += len(accepted)
                usable_candidate_count += sum(
                    resolve_judgment_candidate(candidate) is not None for candidate in accepted
                )
            elif official.status == ProviderResultStatus.FOUND:
                warnings.append(ProviderErrorCode.PROVIDER_RESULT_CONTRACT_VIOLATION.value)
            elif official.status == ProviderResultStatus.ERROR:
                warnings.append(
                    official.error_code.value
                    if official.error_code
                    else "OFFICIAL_SOURCE_UNAVAILABLE"
                )

        def recall_external_candidates() -> None:
            nonlocal added_candidates, added_sources, usable_candidate_count
            assert candidate_provider is not None
            try:
                result, sources, privacy = _run(
                    candidate_provider.search(
                        run.query,
                        top_k=run.max_judgment_verifications,
                    )
                )
            except Exception as exc:
                result = ProviderResult(
                    status=ProviderResultStatus.ERROR,
                    provider_id=candidate_provider.provider_id,
                    error_code=ProviderErrorCode.PROVIDER_RESULT_CONTRACT_VIOLATION,
                    message=f"CANDIDATE_RECALL_CONTRACT_ERROR:{type(exc).__name__}",
                    coverage_complete=False,
                )
                sources = []
                privacy = None
            calls.append(self._provider_call(result))
            privacy_status: PrivacyStatus | None = None
            privacy_allowed = False
            if isinstance(privacy, CandidatePrivacyDecision):
                raw_status = getattr(privacy.status, "value", privacy.status)
                try:
                    privacy_status = PrivacyStatus(str(raw_status))
                except ValueError:
                    privacy_status = None
                privacy_allowed = privacy.allowed is True
            if privacy_status is not None:
                updates["privacy_status"] = privacy_status
            provider_matches = result.provider_id == candidate_provider.provider_id
            candidate_contract_valid = (
                privacy_status is not None
                and privacy_allowed
                and provider_matches
                and result.error_code is None
                and not result.evidence_ids
                and len(result.candidates) <= run.max_judgment_verifications
                and all(
                    candidate.provider_id == candidate_provider.provider_id
                    for candidate in result.candidates
                )
                and all(
                    source.provider_id == candidate_provider.provider_id
                    and source.source_tier is SourceTier.EXTERNAL_SEMANTIC_RECALL
                    and source.trust_status is TrustStatus.EXTERNAL_CANDIDATE
                    for source in sources
                )
                and set(result.source_ids) == {source.source_id for source in sources}
            )
            if result.status is ProviderResultStatus.FOUND and not result.candidates:
                candidate_contract_valid = False
            if result.status is ProviderResultStatus.NOT_FOUND and (
                result.candidates or sources or result.source_ids
            ):
                candidate_contract_valid = False
            if result.status is not ProviderResultStatus.ERROR and not candidate_contract_valid:
                result = ProviderResult(
                    status=ProviderResultStatus.ERROR,
                    provider_id=candidate_provider.provider_id,
                    error_code=ProviderErrorCode.PROVIDER_RESULT_CONTRACT_VIOLATION,
                    message="CANDIDATE_RECALL_RESULT_CONTRACT_VIOLATION",
                    coverage_complete=False,
                )
                calls[-1] = self._provider_call(result)
                sources = []
            if result.status == ProviderResultStatus.ERROR:
                updates.update(
                    {
                        "effective_mode": DataMode.OFFICIAL_ONLY,
                        "semantic_recall_degraded": True,
                    }
                )
                warnings.extend(
                    [
                        result.error_code.value
                        if result.error_code
                        else "EXTERNAL_PROVIDER_UNAVAILABLE",
                        "SEMANTIC_RECALL_DEGRADED",
                    ]
                )
            else:
                for source in sources:
                    self.store.save_source(run.run_id, source)
                for candidate in result.candidates:
                    self.store.save_candidate(run.run_id, candidate, expires_at=run.expires_at)
                added_sources += len(sources)
                added_candidates += len(result.candidates)
                usable_candidate_count += sum(
                    resolve_judgment_candidate(candidate) is not None
                    for candidate in result.candidates
                )

        quick_external_first = (
            run.research_depth is ResearchDepth.QUICK
            and run.effective_mode is DataMode.HYBRID_VERIFIED
            and candidate_provider is not None
        )
        if quick_external_first:
            # Quick judgment research follows the explicit TLR-first contract:
            # fuzzy recall once, then exact official verification.  The slower
            # official keyword search remains a fail-safe only when the
            # candidate provider returns no usable identity.
            recall_external_candidates()
            if usable_candidate_count == 0:
                recall_official()
        else:
            recall_official()
            if run.effective_mode is DataMode.HYBRID_VERIFIED and candidate_provider is not None:
                recall_external_candidates()

        if run.research_depth is ResearchDepth.QUICK and added_candidates:
            warnings.append("QUICK_JUDGMENT_RECALL_BOUNDED")

        updates["judgment_recall_incomplete"] = usable_candidate_count == 0
        return self._outcome(
            obligation,
            calls=calls,
            warnings=warnings,
            added_sources=added_sources,
            added_candidates=added_candidates,
            updates=updates,
        )

    def _verify_judgment(
        self,
        run: ResearchRun,
        obligation: ResearchObligation,
    ) -> dict[str, Any]:
        candidates = self.store.list_candidates(run.run_id)
        resolved: list[ResolvedJudgmentIdentity] = []
        direct = self._jid_from_text(run.query)
        if direct:
            resolved.append(direct_judgment_identity(direct))
        else:
            formal = self._formal_citation_from_text(run.query)
            if formal:
                resolved.append(direct_judgment_identity(formal))
        for candidate in candidates:
            identity = resolve_judgment_candidate(candidate)
            if identity is not None:
                resolved.append(identity)

        targets = rank_and_dedupe_judgment_identities(resolved, query=run.query)
        direct_count = int(bool(direct or self._formal_citation_from_text(run.query)))
        candidate_count = len(candidates) + direct_count
        resolved_count = len(resolved)
        unresolved_count = max(0, candidate_count - resolved_count)
        if not targets:
            missing_limitations = ["JUDGMENT_RECALL_INCOMPLETE"]
            if unresolved_count:
                missing_limitations.append("JUDGMENT_CANDIDATE_RESOLUTION_INCOMPLETE")
            coverage = run.coverage.model_copy(
                update={
                    "judgment_checked": False,
                    "limitations": sorted(
                        set(run.coverage.limitations + missing_limitations)
                    ),
                }
            )
            return self._outcome(
                obligation,
                warnings=missing_limitations,
                metadata={
                    "candidate_count": candidate_count,
                    "resolved_count": resolved_count,
                    "attempted_count": 0,
                    "verified_source_count": 0,
                    "eligible_evidence_count": 0,
                    "partial_parse_count": 0,
                    "failed_count": unresolved_count,
                    "truncated": False,
                    "limitations": missing_limitations,
                },
                updates={"coverage": coverage, "judgment_recall_incomplete": True},
            )
        calls: list[dict[str, Any]] = []
        warnings: list[str] = []
        source_count = 0
        evidence_count = 0
        partial_parse_count = 0
        failed_count = unresolved_count
        failed_reason_codes: list[str] = []
        attempted_targets = targets[: run.max_judgment_verifications]
        truncated = len(targets) > len(attempted_targets)
        for target in attempted_targets:
            identifier = target.lookup_identifier

            def fetch_judgment(
                identifier: str = identifier,
            ) -> tuple[ProviderResult, SourceRecord | None, list[EvidenceSpan]]:
                return _run(self.providers.judgments.exact_lookup(identifier))

            if target.candidate is None:
                result, source, evidence = self._cached_lookup(
                    run.run_id,
                    (
                        f"judgment:{identifier}"
                        if OfficialJudgmentProvider.normalize_jid(identifier)
                        else f"judgment-formal:{_compact_identifier(identifier)}"
                    ),
                    fetch_judgment,
                    expected_provider_id=self.providers.judgments.provider_id,
                )
            else:
                result, source, evidence = fetch_judgment()
                result, source, evidence = self._validated_exact_material(
                    result,
                    source,
                    evidence,
                    expected_provider_id=self.providers.judgments.provider_id,
                )
                if result.error_code is ProviderErrorCode.OFFICIAL_IDENTIFIER_MISMATCH:
                    result = result.model_copy(
                        update={
                            "error_code": ProviderErrorCode.CANDIDATE_OFFICIAL_ID_MISMATCH,
                            "message": "CANDIDATE_OFFICIAL_ID_MISMATCH",
                            "metadata": {
                                **result.metadata,
                                "candidate_id": target.candidate.candidate_id,
                                "resolution_method": target.resolution_method,
                                "requested_identifier": target.canonical_jid,
                            },
                        }
                    )
                if (
                    source is not None
                    and target.canonical_jid is not None
                    and source.official_identifier != target.canonical_jid
                ):
                    result = ProviderResult(
                        status=ProviderResultStatus.ERROR,
                        provider_id=self.providers.judgments.provider_id,
                        error_code=ProviderErrorCode.CANDIDATE_OFFICIAL_ID_MISMATCH,
                        message="CANDIDATE_OFFICIAL_ID_MISMATCH",
                        coverage_complete=False,
                        metadata={
                            "candidate_id": target.candidate.candidate_id,
                            "resolution_method": target.resolution_method,
                            "requested_identifier": target.canonical_jid,
                            "resolved_identifier": source.official_identifier,
                        },
                    )
                    source = None
                    evidence = []
                elif source is not None:
                    source = source.model_copy(
                        update={
                            "metadata": {
                                **source.metadata,
                                "origin_provider_id": target.candidate.provider_id,
                                "origin_candidate_id": target.candidate.candidate_id,
                                "origin_candidate_rank": target.candidate.candidate_rank,
                                "provider_document_id": (
                                    target.candidate.identity.provider_document_id
                                    if target.candidate.identity is not None
                                    else target.candidate.metadata.get("doc_id")
                                ),
                                "identity_resolution_method": target.resolution_method,
                                "resolved_official_identifier": source.official_identifier,
                                "resolved_canonical_jid": (
                                    OfficialJudgmentProvider.normalize_jid(
                                        source.official_identifier or ""
                                    )
                                ),
                                "merged_candidate_ids": list(target.merged_candidate_ids),
                            }
                        }
                    )
                    self.store.save_source(run.run_id, source)
                    for item in evidence:
                        self.store.save_evidence(run.run_id, item)
            calls.append(self._provider_call(result))
            if source is not None:
                source_count += 1
                partial_parse_count += int(source.metadata.get("parse_status") == "partial")
                for item in evidence:
                    evidence_count += int(item.eligible_for_claim_support)
            else:
                failed_count += 1
                failed_reason_codes.append(
                    result.error_code.value if result.error_code else result.status.value
                )
        limitations: list[str] = []
        if unresolved_count:
            limitations.append("JUDGMENT_CANDIDATE_RESOLUTION_INCOMPLETE")
        if truncated:
            limitations.append("JUDGMENT_VERIFICATION_BUDGET_TRUNCATED")
        if partial_parse_count:
            limitations.append("JUDGMENT_PARSE_PARTIAL")
        if failed_count:
            limitations.append("JUDGMENT_OFFICIAL_VERIFICATION_INCOMPLETE")
        # A rejected candidate is not itself answer evidence.  Once at least
        # one different candidate is officially verified, preserve individual
        # failures in metadata and expose the bounded incompleteness warning;
        # zero verified sources still surfaces the underlying hard failures.
        if source_count == 0:
            warnings.extend(failed_reason_codes)
        warnings.extend(limitations)
        coverage = run.coverage.model_copy(
            update={
                "judgment_checked": bool(attempted_targets),
                "limitations": sorted(set(run.coverage.limitations + limitations)),
            }
        )
        verification_summary = {
            "candidate_count": candidate_count,
            "resolved_count": resolved_count,
            "attempted_count": len(attempted_targets),
            "verified_source_count": source_count,
            "eligible_evidence_count": evidence_count,
            "partial_parse_count": partial_parse_count,
            "failed_count": failed_count,
            "failed_reason_codes": sorted(set(failed_reason_codes)),
            "truncated": truncated,
            "limitations": sorted(set(limitations)),
        }
        return self._outcome(
            obligation,
            calls=calls,
            warnings=warnings,
            added_sources=source_count,
            added_evidence=evidence_count,
            metadata=verification_summary,
            updates={
                "coverage": coverage,
                # A verified subset is usable with explicit bounded-scope
                # qualifications.  Zero promoted sources remains a hard
                # authenticity failure.
                "judgment_recall_incomplete": source_count == 0,
            },
        )

    def _constitutional(
        self,
        run: ResearchRun,
        obligation: ResearchObligation,
    ) -> dict[str, Any]:
        calls: list[dict[str, Any]] = []
        warnings: list[str] = []
        source_count = 0
        evidence_count = 0
        plan_locators = self._plan_locators(run, MaterialType.CONSTITUTIONAL)
        client_assisted = run.responsibility.discovery_mode is DiscoveryMode.CLIENT_ASSISTED
        lookup_texts = (
            [item.lookup_text for item in plan_locators] if client_assisted else [run.query]
        )
        identifiers = list(
            dict.fromkeys(
                identifier
                for text in lookup_texts
                if (identifier := self.providers.constitutional.normalize_identifier(text))
            )
        )
        if identifiers:
            for identifier in identifiers:

                def fetch_constitutional(
                    identifier: str = identifier,
                ) -> tuple[ProviderResult, SourceRecord | None, list[EvidenceSpan]]:
                    return _run(
                        self.providers.constitutional.exact_lookup(identifier)
                    )

                result, source, evidence = self._cached_lookup(
                    run.run_id,
                    f"constitutional:{identifier}",
                    fetch_constitutional,
                    expected_provider_id=self.providers.constitutional.provider_id,
                )
                calls.append(self._provider_call(result))
                if source is not None:
                    source_count += 1
                    for item in evidence:
                        evidence_count += int(item.eligible_for_claim_support)
                else:
                    warnings.append(
                        result.error_code.value if result.error_code else result.status.value
                    )
        else:
            if client_assisted:
                warnings.append("CLIENT_ASSISTED_CONSTITUTIONAL_LOCATOR_UNRESOLVED")
            else:
                result = _run(self.providers.constitutional.search(run.query, limit=10))
                calls.append(self._provider_call(result))
                warnings.append("CONSTITUTIONAL_KEYWORD_RESULTS_REQUIRE_EXACT_LOOKUP")
        limitations = list(run.coverage.limitations)
        if not identifiers:
            limitations.append(
                "CLIENT_ASSISTED_CONSTITUTIONAL_LOCATOR_UNRESOLVED"
                if client_assisted
                else "CONSTITUTIONAL_KEYWORD_RESULTS_REQUIRE_EXACT_LOOKUP"
            )
        elif evidence_count == 0:
            limitations.append("CONSTITUTIONAL_OFFICIAL_VERIFICATION_INCOMPLETE")
        coverage = run.coverage.model_copy(
            update={
                "constitutional_checked": evidence_count > 0,
                "limitations": sorted(set(limitations)),
            }
        )
        return self._outcome(
            obligation,
            calls=calls,
            warnings=warnings,
            added_sources=source_count,
            added_evidence=evidence_count,
            metadata={
                "discovery_mode": run.responsibility.discovery_mode.value,
                "registered_locator_count": len(plan_locators),
                "resolved_identifier_count": len(identifiers),
            },
            updates={"coverage": coverage},
        )

    def _counter_authority(
        self,
        run: ResearchRun,
        obligation: ResearchObligation,
    ) -> dict[str, Any]:
        calls: list[dict[str, Any]] = []
        warnings: list[str] = []
        if not hasattr(self.providers.judgments, "search"):
            limitation = "COUNTER_AUTHORITY_SEARCH_UNSUPPORTED"
            coverage = run.coverage.model_copy(
                update={
                    "counter_authority_checked": False,
                    "counter_authority_status": CounterAuthorityStatus.UNSUPPORTED.value,
                    "counter_authority_coverage_complete": False,
                    "limitations": sorted(set(run.coverage.limitations + [limitation])),
                }
            )
            return self._outcome(
                obligation,
                warnings=[limitation],
                metadata={
                    "status": CounterAuthorityStatus.UNSUPPORTED.value,
                    "reason_codes": [limitation],
                    "provider_call_count": 0,
                    "candidate_count": 0,
                    "attempted_count": 0,
                    "verified_count": 0,
                    "absence_claim_allowed": False,
                    "global_consensus_claim_allowed": False,
                },
                updates={"coverage": coverage},
            )

        issue_proposals: list[tuple[str, str]] = []
        registered_locators: list[str] = []
        if run.registered_plan is not None:
            issue_proposals = [
                (item.issue_id, item.proposition)
                for item in run.registered_plan.proposal.issues
                if item.category.value == "counter_authority"
            ]
            registered_locators = [
                item.lookup_text
                for item in run.registered_plan.proposal.authority_locators
                if item.material_type is MaterialType.JUDGMENT
                and item.purpose.value == "counter_authority"
            ]
        plan = build_counter_authority_plan(
            run.query,
            issue_proposals=issue_proposals,
            registered_locators=registered_locators,
            as_of_date=run.as_of_date.isoformat() if run.as_of_date else None,
            provider_id=self.providers.judgments.provider_id,
        )
        resume: CounterAuthorityProgress | None = None
        if obligation.counter_authority_progress is not None:
            try:
                resume = CounterAuthorityProgress.model_validate(
                    obligation.counter_authority_progress
                )
            except Exception as exc:
                limitation = "COUNTER_AUTHORITY_PROGRESS_INVALID"
                coverage = run.coverage.model_copy(
                    update={
                        "counter_authority_checked": False,
                        "counter_authority_status": CounterAuthorityStatus.BLOCKED.value,
                        "counter_authority_coverage_complete": False,
                        "limitations": sorted(
                            set(run.coverage.limitations + [limitation])
                        ),
                    }
                )
                return self._outcome(
                    obligation,
                    warnings=[f"{limitation}:{type(exc).__name__}"],
                    metadata={
                        "status": CounterAuthorityStatus.BLOCKED.value,
                        "reason_codes": [limitation],
                        "provider_call_count": 0,
                        "candidate_count": 0,
                        "attempted_count": 0,
                        "verified_count": 0,
                    },
                    updates={"coverage": coverage},
                )

        def search(query: str, limit: int) -> ProviderResult:
            result = _run(self.providers.judgments.search(query, limit=limit))
            calls.append(self._provider_call(result))
            return result

        existing_verified: dict[str, tuple[SourceRecord, tuple[EvidenceSpan, ...]]] = {}
        existing_evidence = self.store.list_evidence(run.run_id)
        for source in self.store.list_sources(run.run_id):
            if source.trust_status not in {
                TrustStatus.OFFICIAL_VERIFIED,
                TrustStatus.EVIDENCE_ELIGIBLE,
            }:
                continue
            spans = tuple(item for item in existing_evidence if item.source_id == source.source_id)
            identifier = source.official_identifier or ""
            normalized = OfficialJudgmentProvider.normalize_jid(identifier)
            if normalized:
                existing_verified[f"jid:{normalized}"] = (source, spans)
            elif identifier:
                existing_verified[f"raw:{identifier}"] = (source, spans)

        def verify(candidate: ProviderCandidate) -> CounterAuthorityVerification:
            identity = resolve_judgment_candidate(candidate)
            if identity is None:
                result = ProviderResult(
                    status=ProviderResultStatus.ERROR,
                    provider_id=self.providers.judgments.provider_id,
                    error_code=ProviderErrorCode.INVALID_IDENTIFIER,
                    message="COUNTER_AUTHORITY_CANDIDATE_IDENTITY_UNRESOLVED",
                    coverage_complete=False,
                )
                calls.append(self._provider_call(result))
                return CounterAuthorityVerification(
                    candidate_id=candidate.candidate_id,
                    result=result,
                )
            identifier = identity.lookup_identifier

            # A prior official-verification obligation may already have
            # promoted this exact judgment in the same run.  Reuse that
            # server-owned source/evidence rather than issuing a duplicate
            # detail request; the candidate still remains untrusted until the
            # existing official identity is matched.
            normalized_identifier = OfficialJudgmentProvider.normalize_jid(identifier)
            existing_key = (
                f"jid:{normalized_identifier}"
                if normalized_identifier
                else f"raw:{identifier}"
            )
            reused = existing_verified.get(existing_key)
            if reused is not None:
                existing_source, existing_evidence = reused
                result = ProviderResult(
                    status=ProviderResultStatus.FOUND,
                    provider_id=self.providers.judgments.provider_id,
                    source_ids=[existing_source.source_id],
                    evidence_ids=[item.evidence_id for item in existing_evidence],
                    coverage_complete=True,
                    metadata={"reused_official_verification": True},
                )
                calls.append(self._provider_call(result))
                return CounterAuthorityVerification(
                    candidate_id=candidate.candidate_id,
                    result=result,
                    source=existing_source,
                    evidence=existing_evidence,
                )

            def fetch_judgment(
                identifier: str = identifier,
            ) -> tuple[ProviderResult, SourceRecord | None, list[EvidenceSpan]]:
                return _run(self.providers.judgments.exact_lookup(identifier))

            cache_key = (
                f"judgment:{identifier}"
                if OfficialJudgmentProvider.normalize_jid(identifier)
                else f"judgment-formal:{_compact_identifier(identifier)}"
            )
            result, source, evidence = self._cached_lookup(
                run.run_id,
                cache_key,
                fetch_judgment,
                expected_provider_id=self.providers.judgments.provider_id,
            )
            calls.append(self._provider_call(result))
            if source is not None and source.trust_status in {
                TrustStatus.OFFICIAL_VERIFIED,
                TrustStatus.EVIDENCE_ELIGIBLE,
            }:
                existing_verified[existing_key] = (source, tuple(evidence))
            return CounterAuthorityVerification(
                candidate_id=candidate.candidate_id,
                result=result,
                source=source,
                evidence=tuple(evidence),
            )

        def verification_cost(candidate: ProviderCandidate) -> bool:
            """Return whether verifying this candidate needs a new exact fetch.

            Existing server-owned official material in this run is reusable and
            must not consume the bounded exact-lookup budget.  Unresolved or
            otherwise unknown identities conservatively consume the budget.
            """

            identity = resolve_judgment_candidate(candidate)
            if identity is None:
                return True
            identifier = identity.lookup_identifier
            normalized_identifier = OfficialJudgmentProvider.normalize_jid(identifier)
            existing_key = (
                f"jid:{normalized_identifier}"
                if normalized_identifier
                else f"raw:{identifier}"
            )
            return existing_key not in existing_verified

        def save_candidate(candidate: ProviderCandidate) -> None:
            self.store.save_candidate(run.run_id, candidate, expires_at=run.expires_at)

        # The bounded runner owns query ordering/deduplication.  Candidate
        # persistence happens before exact promotion and remains untrusted.
        original_search = search

        def search_and_store(query: str, limit: int) -> ProviderResult:
            result = original_search(query, limit)
            for candidate in result.candidates[:limit]:
                save_candidate(candidate)
            return result

        counter_result, verifications = execute_bounded_counter_authority(
            plan,
            search=search_and_store,
            verify=verify,
            verification_cost=verification_cost,
            resume=resume,
        )
        # Preserve provider/error diagnostics for the coverage receipt while
        # keeping ordinary unverified candidates from being misclassified as
        # transport errors by the service-level reason splitter.
        warnings.extend(
            reason
            for reason in counter_result.reason_codes
            if any(
                marker in reason.upper()
                for marker in (
                    "ERROR",
                    "TIMEOUT",
                    "UNAVAILABLE",
                    "BLOCKED",
                    "PARTIAL",
                    "RETRY",
                    "NOT_FOUND_IN_SCOPE",
                    "INCOMPLETE",
                    "TRUNCATED",
                )
            )
        )
        if counter_result.status is CounterAuthorityStatus.NOT_FOUND_IN_SCOPE:
            warnings.append("COUNTER_AUTHORITY_NOT_FOUND_IN_SCOPE")
        elif counter_result.status is CounterAuthorityStatus.PARTIAL:
            warnings.append("COUNTER_AUTHORITY_PARTIAL")
        elif counter_result.status is CounterAuthorityStatus.RETRY_REQUIRED:
            warnings.append("COUNTER_AUTHORITY_RETRY_REQUIRED")
        elif counter_result.status is CounterAuthorityStatus.BLOCKED:
            warnings.append("COUNTER_AUTHORITY_BLOCKED")

        # The current preview has no server-owned semantic opposition classifier.  Even an
        # officially verified judgment remains relation-unclassified, so only
        # a clean scoped miss completes the counter-authority obligation.
        completed = counter_result.status is CounterAuthorityStatus.NOT_FOUND_IN_SCOPE
        limitations = list(run.coverage.limitations)
        if not completed:
            limitations.extend(counter_result.reason_codes)
        coverage_updates: dict[str, Any] = {
            "counter_authority_checked": completed,
            "counter_authority_status": counter_result.status.value,
            "counter_authority_coverage_complete": counter_result.coverage_complete,
            "limitations": sorted(set(limitations)),
        }
        # Coverage v2 fields are additive.  Keeping these updates in the
        # executor makes the result useful to direct callers while older
        # CoverageState payloads remain compatible during rolling upgrades.
        coverage_fields = getattr(type(run.coverage), "model_fields", {})
        if "bounded_query_scope" in coverage_fields:
            coverage_updates["bounded_query_scope"] = (
                f"provider={','.join(counter_result.plan.scope.provider_ids)};"
                f"material={','.join(item.value for item in counter_result.plan.scope.material_types)};"
                f"max_queries={counter_result.plan.scope.max_queries};"
                f"max_candidates={counter_result.plan.scope.max_candidates_per_query};"
                f"max_verifications={counter_result.plan.scope.max_verifications}"
            )
        if "bounded_time_scope" in coverage_fields:
            coverage_updates["bounded_time_scope"] = counter_result.plan.scope.time_scope
        coverage = run.coverage.model_copy(update=coverage_updates)
        return self._outcome(
            obligation,
            calls=calls,
            warnings=sorted(set(warnings)),
            metadata={
                "schema_version": "alr-tw.counter-authority-result/v1",
                "status": counter_result.status.value,
                "reason_codes": list(counter_result.reason_codes),
                "plan_id": counter_result.plan.plan_id,
                "plan": counter_result.plan.model_dump(mode="json"),
                "progress": counter_result.progress.model_dump(mode="json"),
                "scope": counter_result.plan.scope.model_dump(mode="json"),
                "provider_call_count": len(calls),
                "candidate_count": counter_result.candidate_count,
                "attempted_count": len(counter_result.progress.queries),
                "verified_count": counter_result.verified_count,
                "verified_source_ids": list(counter_result.verified_source_ids),
                "verified_evidence_ids": list(counter_result.verified_evidence_ids),
                "verification_attempts": counter_result.verification_attempts,
                "verification_budget": counter_result.plan.scope.max_verifications,
                "verification_budget_exhausted": (
                    counter_result.verification_budget_exhausted
                ),
                "coverage_complete": counter_result.coverage_complete,
                "relation_status": counter_result.relation_status.value,
                "absence_claim_allowed": counter_result.absence_claim_allowed,
                "global_consensus_claim_allowed": (
                    counter_result.global_consensus_claim_allowed
                ),
                "verified_candidate_count": len(verifications),
            },
            added_sources=len(counter_result.verified_source_ids),
            added_evidence=len(counter_result.verified_evidence_ids),
            updates={"coverage": coverage},
        )

    def _time_context(
        self,
        run: ResearchRun,
        obligation: ResearchObligation,
    ) -> dict[str, Any]:
        coverage = run.coverage.model_copy(
            update={
                "time_context_checked": True,
                "limitations": sorted(
                    set(run.coverage.limitations + ["HISTORICAL_LAW_VERSION_UNSUPPORTED"])
                ),
            }
        )
        return self._outcome(
            obligation,
            warnings=["HISTORICAL_LAW_VERSION_UNSUPPORTED"],
            updates={"coverage": coverage},
        )

    def _sufficiency(
        self,
        run: ResearchRun,
        obligation: ResearchObligation,
    ) -> dict[str, Any]:
        eligible = sum(item.eligible_for_claim_support for item in self.store.list_evidence(run.run_id))
        warnings = [] if eligible else ["NO_ELIGIBLE_EVIDENCE"]
        return self._outcome(
            obligation,
            warnings=warnings,
            metadata={"eligible_evidence_count": eligible},
        )

    def _cached_lookup(
        self,
        run_id: str | None,
        cache_key: str,
        fetch: Callable[
            [],
            tuple[
                ProviderResult,
                SourceRecord | None,
                EvidenceSpan | list[EvidenceSpan] | None,
            ],
        ],
        *,
        expected_provider_id: str,
    ) -> tuple[ProviderResult, SourceRecord | None, list[EvidenceSpan]]:
        existing_cache = run_id is not None and self.store.has_cache_entry(cache_key)
        if run_id is not None:
            cached = self.store.get_fresh_cache_entry(cache_key)
            if cached is not None:
                cached_source, evidence = cached
                cached_result, validated_source, evidence = self._validated_exact_material(
                    ProviderResult(
                        status=ProviderResultStatus.FOUND,
                        provider_id=cached_source.provider_id,
                        source_ids=[cached_source.source_id],
                        evidence_ids=[item.evidence_id for item in evidence],
                        coverage_complete=True,
                        metadata={"cache_hit": True},
                    ),
                    cached_source,
                    evidence,
                    expected_provider_id=expected_provider_id,
                )
                if validated_source is not None:
                    self.store.save_source(run_id, validated_source)
                    for item in evidence:
                        self.store.save_evidence(run_id, item)
                    return cached_result, validated_source, evidence

        result, source, raw_evidence = fetch()
        if existing_cache and result.status != ProviderResultStatus.FOUND:
            original_error = result.error_code.value if result.error_code else None
            result = result.model_copy(
                update={
                    "error_code": ProviderErrorCode.SOURCE_REVALIDATION_FAILED,
                    "message": "SOURCE_REVALIDATION_FAILED",
                    "metadata": {
                        **result.metadata,
                        "original_error_code": original_error,
                    },
                }
            )
        result, source, evidence = self._validated_exact_material(
            result,
            source,
            raw_evidence,
            expected_provider_id=expected_provider_id,
        )
        if run_id is not None and source is not None:
            self.store.save_source(run_id, source)
            for item in evidence:
                self.store.save_evidence(run_id, item)
            if result.status == ProviderResultStatus.FOUND and evidence:
                self.store.save_cache_entry(cache_key, source, evidence)
        return result, source, evidence

    @staticmethod
    def _validated_exact_material(
        result: ProviderResult,
        source: SourceRecord | None,
        raw_evidence: EvidenceSpan | list[EvidenceSpan] | None,
        *,
        expected_provider_id: str,
    ) -> tuple[ProviderResult, SourceRecord | None, list[EvidenceSpan]]:
        """Reject inconsistent exact-provider material before it reaches storage."""

        evidence = (
            raw_evidence
            if isinstance(raw_evidence, list)
            else [raw_evidence]
            if raw_evidence is not None
            else []
        )
        if result.status is not ProviderResultStatus.FOUND or result.error_code is not None:
            return result, None, []

        evidence_ids = [item.evidence_id for item in evidence if isinstance(item, EvidenceSpan)]
        contract_valid = bool(
            source is not None
            and isinstance(source, SourceRecord)
            and result.provider_id == expected_provider_id
            and source.provider_id == expected_provider_id
            and result.source_ids == [source.source_id]
            and len(evidence_ids) == len(evidence)
            and len(evidence_ids) == len(set(evidence_ids))
            and set(result.evidence_ids) == set(evidence_ids)
            and all(item.source_id == source.source_id for item in evidence)
            and source.source_tier in {SourceTier.OFFICIAL, SourceTier.VERIFIED_CACHE}
            and source.trust_status
            in {
                TrustStatus.OFFICIAL_FETCHED,
                TrustStatus.OFFICIAL_VERIFIED,
                TrustStatus.EVIDENCE_ELIGIBLE,
            }
        )
        if contract_valid:
            return result, source, evidence
        return (
            ProviderResult(
                status=ProviderResultStatus.ERROR,
                provider_id=expected_provider_id,
                error_code=ProviderErrorCode.PROVIDER_RESULT_CONTRACT_VIOLATION,
                message="EXACT_PROVIDER_RESULT_CONTRACT_VIOLATION",
                coverage_complete=False,
                metadata={"reported_provider_id": result.provider_id},
            ),
            None,
            [],
        )

    @staticmethod
    def _provider_call(result: Any) -> dict[str, Any]:
        return {
            "provider_id": result.provider_id,
            "status": result.status.value,
            "error_code": result.error_code.value if result.error_code else None,
            "source_count": len(result.source_ids),
            "evidence_count": len(result.evidence_ids),
            "candidate_count": len(result.candidates),
        }

    def _fetch_lineage_history(
        self,
        root_source: SourceRecord,
        jid: str,
        candidate: ProviderCandidate | None,
        provider_calls: list[dict[str, Any]],
    ) -> tuple[ProviderResult, TlrCaseHistoryRecord | None]:
        provider = self.providers.lineage_candidate_provider
        assert provider is not None
        if candidate is not None:
            doc_id = self._candidate_doc_id(candidate)
            result_handle = candidate.metadata.get("result_token")
            if doc_id is not None and isinstance(result_handle, str) and result_handle.strip():
                result, history = _run(provider.case_history(doc_id, result_handle))
                provider_calls.append(self._provider_call(result))
                if result.error_code is not ProviderErrorCode.TLR_RESULT_TOKEN_INVALID_OR_EXPIRED:
                    return result, history

        refresh_query = root_source.citation
        if candidate is not None:
            for value in (
                candidate.identity.formal_citation if candidate.identity is not None else None,
                candidate.title,
            ):
                if isinstance(value, str) and value.strip():
                    refresh_query = value.strip()
                    break
        search_result, _, _ = _run(provider.search(refresh_query, top_k=10))
        provider_calls.append(self._provider_call(search_result))
        if search_result.status is ProviderResultStatus.ERROR:
            return search_result, None
        refreshed = self._lineage_candidate(search_result.candidates, jid)
        if refreshed is None:
            return (
                ProviderResult(
                    status=ProviderResultStatus.NOT_FOUND,
                    provider_id=provider.provider_id,
                    error_code=ProviderErrorCode.TLR_DOCUMENT_NOT_FOUND,
                    message="TLR_LINEAGE_ROOT_NOT_FOUND",
                    coverage_complete=False,
                ),
                None,
            )
        doc_id = self._candidate_doc_id(refreshed)
        result_handle = refreshed.metadata.get("result_token")
        if doc_id is None or not isinstance(result_handle, str) or not result_handle.strip():
            return (
                ProviderResult(
                    status=ProviderResultStatus.ERROR,
                    provider_id=provider.provider_id,
                    error_code=ProviderErrorCode.EXTERNAL_PROVIDER_SCHEMA_CHANGED,
                    message="TLR_LINEAGE_RESULT_HANDLE_MISSING",
                    coverage_complete=False,
                ),
                None,
            )
        result, history = _run(provider.case_history(doc_id, result_handle))
        provider_calls.append(self._provider_call(result))
        return result, history

    @staticmethod
    def _lineage_root_source(
        sources: list[SourceRecord],
        jid: str,
    ) -> SourceRecord | None:
        eligible = [
            source
            for source in sources
            if source.material_type is MaterialType.JUDGMENT
            and source.source_tier in {SourceTier.OFFICIAL, SourceTier.VERIFIED_CACHE}
            and source.trust_status
            in {TrustStatus.OFFICIAL_VERIFIED, TrustStatus.EVIDENCE_ELIGIBLE}
            and OfficialJudgmentProvider.normalize_jid(source.official_identifier or "") == jid
        ]
        return max(
            eligible,
            key=lambda source: source.verified_at or source.fetched_at,
            default=None,
        )

    @classmethod
    def _lineage_candidate(
        cls,
        candidates: list[ProviderCandidate],
        jid: str,
        *,
        preferred_candidate_id: str | None = None,
    ) -> ProviderCandidate | None:
        matches = [
            candidate
            for candidate in candidates
            if candidate.provider_id == TlrSemanticRecallProvider.provider_id
            and cls._candidate_matches_jid(candidate, jid)
        ]
        if preferred_candidate_id is not None:
            preferred = next(
                (
                    candidate
                    for candidate in matches
                    if candidate.candidate_id == preferred_candidate_id
                ),
                None,
            )
            if preferred is not None:
                return preferred
        return min(
            matches,
            key=lambda candidate: candidate.candidate_rank or 2**31,
            default=None,
        )

    @staticmethod
    def _candidate_doc_id(candidate: ProviderCandidate) -> str | None:
        value = (
            candidate.identity.provider_document_id
            if candidate.identity is not None
            else candidate.metadata.get("doc_id")
        )
        return str(value).strip() if isinstance(value, str) and value.strip() else None

    @classmethod
    def _candidate_matches_jid(cls, candidate: ProviderCandidate, jid: str) -> bool:
        if candidate.identity is not None and candidate.identity.canonical_jid == jid:
            return True
        doc_id = cls._candidate_doc_id(candidate)
        partial = OfficialJudgmentProvider.normalize_partial_jid(doc_id or "")
        return partial is not None and jid.startswith(f"{partial},")

    @staticmethod
    def _lineage_identity_matches(
        actual_identifier: str | None,
        provider_document_id: str,
    ) -> bool:
        actual = OfficialJudgmentProvider.normalize_jid(actual_identifier or "")
        if actual is None:
            return False
        expected = OfficialJudgmentProvider.normalize_jid(provider_document_id)
        if expected is not None:
            return actual == expected
        partial = OfficialJudgmentProvider.normalize_partial_jid(provider_document_id)
        return partial is not None and actual.startswith(f"{partial},")

    @classmethod
    def _lineage_verification_error(
        cls,
        result: ProviderResult,
        source: SourceRecord | None,
        evidence: list[EvidenceSpan],
        provider_document_id: str,
        *,
        root_jid: str,
        now: datetime,
        expected_provider_id: str,
    ) -> str | None:
        if result.status is not ProviderResultStatus.FOUND:
            return (
                result.error_code.value
                if result.error_code is not None
                else "JUDGMENT_LINEAGE_OFFICIAL_VERIFICATION_FAILED"
            )
        if result.error_code is not None:
            return "JUDGMENT_LINEAGE_PROVIDER_RESULT_CONTRACT_VIOLATION"
        if source is None:
            return "JUDGMENT_LINEAGE_OFFICIAL_SOURCE_MISSING"
        if (
            result.provider_id != expected_provider_id
            or source.provider_id != expected_provider_id
        ):
            return "JUDGMENT_LINEAGE_PROVIDER_RESULT_CONTRACT_VIOLATION"
        if not cls._lineage_identity_matches(
            source.official_identifier,
            provider_document_id,
        ):
            return "JUDGMENT_LINEAGE_OFFICIAL_ID_MISMATCH"
        if OfficialJudgmentProvider.normalize_jid(source.official_identifier or "") == root_jid:
            return "JUDGMENT_LINEAGE_OFFICIAL_SELF_REFERENCE"
        if (
            source.material_type is not MaterialType.JUDGMENT
            or source.source_tier not in {SourceTier.OFFICIAL, SourceTier.VERIFIED_CACHE}
            or source.trust_status
            not in {TrustStatus.OFFICIAL_VERIFIED, TrustStatus.EVIDENCE_ELIGIBLE}
        ):
            return "JUDGMENT_LINEAGE_SOURCE_NOT_OFFICIALLY_VERIFIED"
        if source.expires_at <= now:
            return "JUDGMENT_LINEAGE_OFFICIAL_SOURCE_STALE"
        if not evidence:
            return "JUDGMENT_LINEAGE_OFFICIAL_EVIDENCE_MISSING"
        evidence_ids = {item.evidence_id for item in evidence}
        if (
            set(result.source_ids) != {source.source_id}
            or set(result.evidence_ids) != evidence_ids
            or any(item.source_id != source.source_id for item in evidence)
        ):
            return "JUDGMENT_LINEAGE_OFFICIAL_EVIDENCE_NOT_BOUND"
        return None

    @staticmethod
    def _lineage_blocked(jid: str, reason_code: str) -> dict[str, Any]:
        return {
            "schema_version": "alr-tw.judgment-lineage-inspection/v1",
            "status": "blocked",
            "jid": jid,
            "reason_codes": [reason_code],
            "establishes_finality": False,
            "semantic_opinion_comparison_performed": False,
            "related_nodes": [],
            "limitations": ["NO_UPPER_HISTORY_DOES_NOT_ESTABLISH_FINALITY"],
        }

    @staticmethod
    def _outcome(
        obligation: ResearchObligation,
        *,
        calls: list[dict[str, Any]] | None = None,
        warnings: list[str] | None = None,
        added_sources: int = 0,
        added_evidence: int = 0,
        added_candidates: int = 0,
        metadata: dict[str, Any] | None = None,
        updates: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "status": "completed",
            "obligation": obligation.kind.value,
            "provider_calls": calls or [],
            "added_source_count": added_sources,
            "added_eligible_evidence_count": added_evidence,
            "added_candidate_count": added_candidates,
            "warnings": warnings or [],
            "metadata": metadata or {},
            "_run_updates": updates or {},
        }

    @staticmethod
    def _jid_from_text(text: str) -> str | None:
        match = _JID.search(text)
        if match is None:
            return None
        return OfficialJudgmentProvider.normalize_jid(match.group("jid"))

    @staticmethod
    def _formal_citation_from_text(text: str) -> str | None:
        match = _FORMAL_JUDGMENT_CITATION.search(text)
        if match is None:
            return None
        citation = match.group("citation")
        return (
            citation
            if OfficialJudgmentProvider.normalize_formal_citation(citation) is not None
            else None
        )

    @staticmethod
    def _jid_from_url(url: str | None) -> str | None:
        if not url:
            return None
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != "judgment.judicial.gov.tw":
            return None
        query = parse_qs(parsed.query)
        for key in ("id", "jid", "j"):
            for value in query.get(key, []):
                normalized = OfficialJudgmentProvider.normalize_jid(unquote(value))
                if normalized:
                    return normalized
        return None
