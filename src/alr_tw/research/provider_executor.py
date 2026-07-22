"""Provider-backed execution of one server-owned research obligation."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, TypeVar
from urllib.parse import parse_qs, unquote, urlsplit

from alr_tw.contracts.providers import (
    DataMode,
    ProviderErrorCode,
    ProviderResult,
    ProviderResultStatus,
)
from alr_tw.contracts.research import (
    ResearchObligation,
    ResearchObligationKind,
    ResearchRun,
)
from alr_tw.contracts.sources import EvidenceSpan, SourceRecord
from alr_tw.providers.official import (
    OfficialConstitutionalProvider,
    OfficialJudgmentProvider,
    OfficialLawProvider,
)
from alr_tw.providers.tlr import TlrSemanticRecallProvider, screen_external_query
from alr_tw.research.judgment_identity import (
    ResolvedJudgmentIdentity,
    direct_judgment_identity,
    rank_and_dedupe_judgment_identities,
    resolve_judgment_candidate,
)
from alr_tw.storage.sqlite_store import SqliteStore

_T = TypeVar("_T")
_LAW_CITATION = re.compile(
    r"(?P<law>[\u4e00-\u9fff]{2,30}(?:法|條例|規則|辦法))第\s*"
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
    judgments: OfficialJudgmentProvider
    tlr: TlrSemanticRecallProvider | None = None


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
                )
            elif formal_citation:
                result, source, evidence_items = self._cached_lookup(
                    run_id,
                    f"judgment-formal:{_compact_identifier(formal_citation)}",
                    lambda: _run(self.providers.judgments.exact_lookup(formal_citation)),
                )
            elif constitutional:
                result, source, evidence_items = self._cached_lookup(
                    run_id,
                    f"constitutional:{constitutional}",
                    lambda: _run(self.providers.constitutional.exact_lookup(constitutional)),
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
        citations = _run(self.providers.laws.resolve_citations(run.query, limit=5))
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
                )
                calls.append(self._provider_call(result))
                if source is not None:
                    added_sources += 1
                added_evidence += sum(item.eligible_for_claim_support for item in evidence_items)
                if result.status != ProviderResultStatus.FOUND:
                    warnings.append(result.error_code.value if result.error_code else result.status.value)
        else:
            result = _run(self.providers.laws.search(run.query, limit=10))
            calls.append(self._provider_call(result))
            warnings.append("LAW_KEYWORD_RESULTS_REQUIRE_EXACT_LOOKUP")
        limitations = list(run.coverage.limitations)
        if not citations:
            limitations.append("LAW_KEYWORD_RESULTS_REQUIRE_EXACT_LOOKUP")
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
            updates={"coverage": coverage},
        )

    def _judgment_recall(
        self,
        run: ResearchRun,
        obligation: ResearchObligation,
    ) -> dict[str, Any]:
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
        updates: dict[str, Any] = {}

        official = _run(self.providers.judgments.search(run.query, limit=5))
        calls.append(self._provider_call(official))
        if official.status == ProviderResultStatus.FOUND:
            for candidate in official.candidates:
                self.store.save_candidate(run.run_id, candidate, expires_at=run.expires_at)
            added_candidates += len(official.candidates)
        elif official.status == ProviderResultStatus.ERROR:
            warnings.append(
                official.error_code.value
                if official.error_code
                else "OFFICIAL_SOURCE_UNAVAILABLE"
            )

        if run.effective_mode == DataMode.HYBRID_VERIFIED and self.providers.tlr is not None:
            result, sources, privacy = _run(self.providers.tlr.search(run.query))
            calls.append(self._provider_call(result))
            updates["privacy_status"] = privacy.status
            if result.status == ProviderResultStatus.ERROR:
                updates.update(
                    {
                        "effective_mode": DataMode.OFFICIAL_ONLY,
                        "semantic_recall_degraded": True,
                    }
                )
                warnings.extend(
                    [
                        result.error_code.value if result.error_code else "TLR_UNAVAILABLE",
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

        updates["judgment_recall_incomplete"] = added_candidates == 0
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

        targets = rank_and_dedupe_judgment_identities(resolved)
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
        attempted_targets = targets[:5]
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
                )
            else:
                result, source, evidence = fetch_judgment()
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
                                "resolved_canonical_jid": source.official_identifier,
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
                partial_parse_count += int(
                    source.metadata.get("parse_status") == "partial"
                )
                for item in evidence:
                    evidence_count += int(item.eligible_for_claim_support)
            else:
                failed_count += 1
                warnings.append(result.error_code.value if result.error_code else result.status.value)
        limitations: list[str] = []
        if unresolved_count:
            limitations.append("JUDGMENT_CANDIDATE_RESOLUTION_INCOMPLETE")
        if truncated:
            limitations.append("JUDGMENT_VERIFICATION_BUDGET_TRUNCATED")
        if partial_parse_count:
            limitations.append("JUDGMENT_PARSE_PARTIAL")
        if failed_count:
            limitations.append("JUDGMENT_OFFICIAL_VERIFICATION_INCOMPLETE")
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
                "judgment_recall_incomplete": source_count == 0 or bool(limitations),
            },
        )

    def _constitutional(
        self,
        run: ResearchRun,
        obligation: ResearchObligation,
    ) -> dict[str, Any]:
        identifier = self.providers.constitutional.normalize_identifier(run.query)
        calls: list[dict[str, Any]] = []
        warnings: list[str] = []
        source_count = 0
        evidence_count = 0
        if identifier:
            result, source, evidence = self._cached_lookup(
                run.run_id,
                f"constitutional:{identifier}",
                lambda: _run(self.providers.constitutional.exact_lookup(identifier)),
            )
            calls.append(self._provider_call(result))
            if source is not None:
                source_count = 1
                for item in evidence:
                    evidence_count += int(item.eligible_for_claim_support)
            else:
                warnings.append(result.error_code.value if result.error_code else result.status.value)
        else:
            result = _run(self.providers.constitutional.search(run.query, limit=10))
            calls.append(self._provider_call(result))
            warnings.append("CONSTITUTIONAL_KEYWORD_RESULTS_REQUIRE_EXACT_LOOKUP")
        limitations = list(run.coverage.limitations)
        if not identifier:
            limitations.append("CONSTITUTIONAL_KEYWORD_RESULTS_REQUIRE_EXACT_LOOKUP")
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
            updates={"coverage": coverage},
        )

    def _counter_authority(
        self,
        run: ResearchRun,
        obligation: ResearchObligation,
    ) -> dict[str, Any]:
        limitation = "COUNTER_AUTHORITY_SEARCH_NOT_IMPLEMENTED"
        coverage = run.coverage.model_copy(
            update={
                "counter_authority_checked": False,
                "limitations": sorted(set(run.coverage.limitations + [limitation])),
            }
        )
        return self._outcome(
            obligation,
            warnings=[limitation],
            metadata={
                "provider_call_count": 0,
                "candidate_count": 0,
                "attempted_count": 0,
                "verified_count": 0,
            },
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
    ) -> tuple[ProviderResult, SourceRecord | None, list[EvidenceSpan]]:
        existing_cache = run_id is not None and self.store.has_cache_entry(cache_key)
        if run_id is not None:
            cached = self.store.get_fresh_cache_entry(cache_key)
            if cached is not None:
                cached_source, evidence = cached
                self.store.save_source(run_id, cached_source)
                for item in evidence:
                    self.store.save_evidence(run_id, item)
                return (
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
                )

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
        evidence = (
            raw_evidence
            if isinstance(raw_evidence, list)
            else [raw_evidence]
            if raw_evidence is not None
            else []
        )
        if run_id is not None and source is not None:
            self.store.save_source(run_id, source)
            for item in evidence:
                self.store.save_evidence(run_id, item)
            if result.status == ProviderResultStatus.FOUND and evidence:
                self.store.save_cache_entry(cache_key, source, evidence)
        return result, source, evidence

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
