"""Provider-neutral bounded counter-authority search contracts.

This module deliberately separates lexical candidate discovery from official
verification.  A query result is never evidence by itself: only a successful
server-owned exact lookup with a verified source and an eligible evidence span
may be reported as ``found_verified``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from enum import Enum
import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from alr_tw.contracts.providers import ProviderCandidate, ProviderResult, ProviderResultStatus
from alr_tw.contracts.sources import EvidenceSpan, MaterialType, SourceRecord, TrustStatus


MAX_COUNTER_QUERIES = 4
MAX_COUNTER_CANDIDATES_PER_QUERY = 5
MAX_COUNTER_VERIFICATIONS = 5
MAX_COUNTER_QUERY_CHARS = 128
_TOKEN_RE = re.compile(r"[\u3400-\u9fffA-Za-z0-9]{2,}")
_LAW_REFERENCE_RE = re.compile(
    r"[\u3400-\u9fff]{1,30}?(?:法|條例|規則|辦法)第\s*"
    r"\d+(?:\s*(?:之|-)\s*\d+)*\s*條"
)
_QUERY_FILLERS = (
    "請問",
    "是否",
    "有沒有",
    "如何",
    "關於",
    "針對",
    "本案",
)


class CounterAuthorityStatus(str, Enum):
    """Terminal status of a bounded counter-authority attempt."""

    FOUND_VERIFIED = "found_verified"
    NOT_FOUND_IN_SCOPE = "not_found_in_scope"
    PARTIAL = "partial"
    RETRY_REQUIRED = "retry_required"
    UNSUPPORTED = "unsupported"
    BLOCKED = "blocked"


class CounterAuthorityRelationStatus(str, Enum):
    """Relation between a verified judgment and the issue.

    The current preview verifies only official identity/content.  It intentionally does not
    infer that a judgment is opposing, supporting, or unrelated to the issue.
    """

    UNCLASSIFIED = "relation_unclassified"
    NOT_APPLICABLE = "not_applicable"


class CounterQueryStatus(str, Enum):
    PENDING = "pending"
    FOUND = "found"
    NOT_FOUND = "not_found"
    PARTIAL = "partial"
    FAILED = "failed"
    BLOCKED = "blocked"


class CounterAuthorityQuery(BaseModel):
    """One transparent lexical query in the bounded plan."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query_id: str = Field(pattern=r"^counter-q-[0-9a-f]{12}$")
    text: str = Field(min_length=1, max_length=MAX_COUNTER_QUERY_CHARS)
    purpose: Literal["issue", "lexical_variant", "registered_locator"]
    source_issue_id: str | None = Field(default=None, max_length=80)
    ordinal: int = Field(ge=1, le=MAX_COUNTER_QUERIES)


class CounterAuthorityScope(BaseModel):
    """Explicit scope for the bounded search; it is not a global absence claim."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.counter-authority-scope/v1"] = (
        "alr-tw.counter-authority-scope/v1"
    )
    provider_ids: tuple[str, ...] = ("official_judicial_yuan_judgments",)
    material_types: tuple[MaterialType, ...] = (MaterialType.JUDGMENT,)
    max_queries: int = Field(default=MAX_COUNTER_QUERIES, ge=1, le=MAX_COUNTER_QUERIES)
    max_candidates_per_query: int = Field(
        default=MAX_COUNTER_CANDIDATES_PER_QUERY,
        ge=1,
        le=10,
    )
    max_verifications: int = Field(
        default=MAX_COUNTER_VERIFICATIONS,
        ge=1,
        le=MAX_COUNTER_VERIFICATIONS,
    )
    time_scope: str | None = Field(default=None, max_length=80)
    global_absence_claim_allowed: Literal[False] = False


class CounterAuthorityPlan(BaseModel):
    """Deterministic, serializable plan that can be persisted and resumed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.counter-authority-plan/v1"] = (
        "alr-tw.counter-authority-plan/v1"
    )
    plan_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    generator: Literal["lexical_counter_v2"] = "lexical_counter_v2"
    scope: CounterAuthorityScope
    queries: tuple[CounterAuthorityQuery, ...] = Field(
        min_length=1,
        max_length=MAX_COUNTER_QUERIES,
    )

    @model_validator(mode="after")
    def validate_ordinals_and_ids(self) -> CounterAuthorityPlan:
        if len({item.query_id for item in self.queries}) != len(self.queries):
            raise ValueError("counter authority query IDs must be unique")
        ordinals = [item.ordinal for item in self.queries]
        if ordinals != list(range(1, len(ordinals) + 1)):
            raise ValueError("counter authority query ordinals must be contiguous")
        if len(self.queries) > self.scope.max_queries:
            raise ValueError("counter authority query plan exceeds scope")
        return self

    @staticmethod
    def digest_payload(payload: dict[str, Any]) -> str:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class CounterAuthorityQueryProgress(BaseModel):
    """Serializable progress for one query, suitable for resumable clients."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query_id: str = Field(pattern=r"^counter-q-[0-9a-f]{12}$")
    status: CounterQueryStatus
    provider_status: str | None = None
    provider_error_code: str | None = None
    candidate_count: int = Field(default=0, ge=0)
    verified_count: int = Field(default=0, ge=0)
    verification_attempt_count: int = Field(default=0, ge=0)
    candidate_ids: tuple[str, ...] = ()
    verified_candidate_ids: tuple[str, ...] = ()
    verified_candidate_keys: tuple[str, ...] = ()
    verified_source_ids: tuple[str, ...] = ()
    verified_evidence_ids: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()


class CounterAuthorityProgress(BaseModel):
    """Plan progress plus a stable resumable cursor."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.counter-authority-progress/v1"] = (
        "alr-tw.counter-authority-progress/v1"
    )
    plan_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    total_queries: int = Field(ge=1, le=MAX_COUNTER_QUERIES)
    verification_attempts: int = Field(default=0, ge=0)
    next_ordinal: int = Field(ge=1)
    queries: tuple[CounterAuthorityQueryProgress, ...] = ()

    @model_validator(mode="after")
    def validate_cursor(self) -> CounterAuthorityProgress:
        if len(self.queries) > self.total_queries:
            raise ValueError("counter authority progress exceeds total queries")
        if self.next_ordinal > self.total_queries + 1:
            raise ValueError("counter authority cursor exceeds total queries")
        return self

    @property
    def complete(self) -> bool:
        return self.next_ordinal > self.total_queries


class CounterAuthorityVerification(BaseModel):
    """Result of one candidate's server-owned exact verification."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True, extra="forbid")

    candidate_id: str = Field(min_length=1)
    result: ProviderResult
    source: SourceRecord | None = None
    evidence: tuple[EvidenceSpan, ...] = ()
    relation_status: CounterAuthorityRelationStatus = (
        CounterAuthorityRelationStatus.UNCLASSIFIED
    )

    @property
    def evidence_eligible(self) -> bool:
        return bool(
            self.result.status is ProviderResultStatus.FOUND
            and self.source is not None
            and self.source.trust_status
            in {TrustStatus.OFFICIAL_VERIFIED, TrustStatus.EVIDENCE_ELIGIBLE}
            and self.source.content_hash.startswith("sha256:")
            and self.source.verified_at is not None
            and any(item.eligible_for_claim_support for item in self.evidence)
        )


class CounterAuthorityResult(BaseModel):
    """Bounded result; ``absence_claim_allowed`` never means global absence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.counter-authority-result/v1"] = (
        "alr-tw.counter-authority-result/v1"
    )
    status: CounterAuthorityStatus
    plan: CounterAuthorityPlan
    progress: CounterAuthorityProgress
    candidate_count: int = Field(default=0, ge=0)
    verified_count: int = Field(default=0, ge=0)
    verified_source_ids: tuple[str, ...] = ()
    verified_evidence_ids: tuple[str, ...] = ()
    verification_attempts: int = Field(default=0, ge=0)
    verification_budget_exhausted: bool = False
    coverage_complete: bool = False
    relation_status: CounterAuthorityRelationStatus = (
        CounterAuthorityRelationStatus.UNCLASSIFIED
    )
    absence_claim_allowed: bool = False
    global_consensus_claim_allowed: Literal[False] = False
    reason_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_absence_boundary(self) -> CounterAuthorityResult:
        if self.absence_claim_allowed and self.status is not CounterAuthorityStatus.NOT_FOUND_IN_SCOPE:
            raise ValueError("absence claim is valid only for a clean scoped miss")
        if self.absence_claim_allowed and self.verified_count:
            raise ValueError("verified hits invalidate absence claim")
        return self


def build_counter_authority_plan(
    query: str,
    *,
    issue_proposals: Sequence[tuple[str, str]] = (),
    registered_locators: Sequence[str] = (),
    as_of_date: str | None = None,
    provider_id: str = "official_judicial_yuan_judgments",
    max_queries: int = MAX_COUNTER_QUERIES,
    max_verifications: int = MAX_COUNTER_VERIFICATIONS,
) -> CounterAuthorityPlan:
    """Build a deterministic lexical plan without semantic entailment.

    ``issue_proposals`` are ``(issue_id, proposition)`` pairs.  Duplicates are
    removed after Unicode whitespace compaction; the first four distinct
    entries are retained in stable source order.
    """

    bounded = max(1, min(max_queries, MAX_COUNTER_QUERIES))
    verification_budget = max(1, min(max_verifications, MAX_COUNTER_VERIFICATIONS))
    entries: list[
        tuple[str, Literal["issue", "lexical_variant", "registered_locator"], str | None]
    ] = []
    root = " ".join(query.split()).strip()
    for locator in registered_locators:
        value = " ".join(locator.split()).strip()
        if value:
            entries.append(
                (_compact_counter_query(value), "registered_locator", None)
            )
    for issue_key, proposition in issue_proposals:
        value = " ".join(proposition.split()).strip()
        if not value:
            continue
        for marker in ("相反見解", "不同見解"):
            entries.append(
                (_compact_counter_query(value, marker=marker), "issue", issue_key)
            )
    if root:
        for marker in ("相反見解", "不同見解"):
            entries.append(
                (_compact_counter_query(root, marker=marker), "lexical_variant", None)
            )

    selected: list[
        tuple[str, Literal["issue", "lexical_variant", "registered_locator"], str | None]
    ] = []
    seen: set[str] = set()
    for text, purpose, source_issue_id in entries:
        key = text.casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        selected.append((text, purpose, source_issue_id))
        if len(selected) == bounded:
            break
    if not selected:
        raise ValueError("COUNTER_AUTHORITY_QUERY_EMPTY")

    query_items: list[CounterAuthorityQuery] = []
    for ordinal, (text, purpose, source_issue_id) in enumerate(selected, start=1):
        query_id = "counter-q-" + hashlib.sha256(
            f"{ordinal}:{purpose}:{source_issue_id or ''}:{text}".encode("utf-8")
        ).hexdigest()[:12]
        query_items.append(
            CounterAuthorityQuery(
                query_id=query_id,
                text=text,
                purpose=purpose,
                source_issue_id=source_issue_id,
                ordinal=ordinal,
            )
        )
    scope = CounterAuthorityScope(
        provider_ids=(provider_id,),
        max_queries=len(query_items),
        max_verifications=verification_budget,
        time_scope=as_of_date,
    )
    payload = {
        "generator": "lexical_counter_v2",
        "scope": scope.model_dump(mode="json"),
        "queries": [item.model_dump(mode="json") for item in query_items],
    }
    return CounterAuthorityPlan(
        plan_id=CounterAuthorityPlan.digest_payload(payload),
        scope=scope,
        queries=tuple(query_items),
    )


def _compact_counter_query(value: str, *, marker: str | None = None) -> str:
    """Build an official-search-safe lexical query without semantic inference."""

    normalized = " ".join(value.split()).strip()
    if not normalized:
        raise ValueError("COUNTER_AUTHORITY_QUERY_EMPTY")
    if marker is None:
        return normalized[:MAX_COUNTER_QUERY_CHARS]

    references: list[str] = []
    for match in _LAW_REFERENCE_RE.finditer(normalized):
        reference = re.sub(r"\s+", "", match.group(0))
        for filler in _QUERY_FILLERS:
            if reference.startswith(filler) and len(reference) > len(filler):
                reference = reference[len(filler) :]
                break
        if reference not in references:
            references.append(reference)
        if len(references) == 2:
            break

    issue = _LAW_REFERENCE_RE.sub(" ", normalized)
    issue = re.sub(r"[，。；;、！？?：:（）()]", " ", issue)
    issue = " ".join(issue.split()).strip()
    for filler in _QUERY_FILLERS:
        issue = issue.removeprefix(filler).strip()

    fixed = " ".join([*references, marker]).strip()
    issue_budget = max(0, MAX_COUNTER_QUERY_CHARS - len(fixed) - (1 if fixed else 0))
    if len(issue) > issue_budget:
        if issue_budget <= 1:
            issue = ""
        else:
            head = max(1, (issue_budget - 1) // 2)
            tail = max(1, issue_budget - head - 1)
            issue = f"{issue[:head]} {issue[-tail:]}"
    compact = " ".join(part for part in (*references, issue, marker) if part).strip()
    return compact[:MAX_COUNTER_QUERY_CHARS]


SearchCounter = Callable[[str, int], ProviderResult]
VerifyCounter = Callable[[ProviderCandidate], CounterAuthorityVerification]
VerificationCost = Callable[[ProviderCandidate], bool]


def execute_bounded_counter_authority(
    plan: CounterAuthorityPlan,
    *,
    search: SearchCounter,
    verify: VerifyCounter,
    verification_cost: VerificationCost | None = None,
    resume: CounterAuthorityProgress | None = None,
) -> tuple[CounterAuthorityResult, list[CounterAuthorityVerification]]:
    """Run a bounded plan with deterministic deduplication and fail-closed status."""

    if resume is not None and resume.plan_id != plan.plan_id:
        raise ValueError("COUNTER_AUTHORITY_RESUME_PLAN_MISMATCH")
    previous = {item.query_id: item for item in (resume.queries if resume else ())}
    progress_items: list[CounterAuthorityQueryProgress] = []
    verifications: list[CounterAuthorityVerification] = []
    seen_candidates: set[str] = set()
    prior_verified_source_ids: set[str] = set()
    prior_verified_evidence_ids: set[str] = set()
    for prior_item in previous.values():
        # Candidate IDs from retryable progress are deliberately not seeded:
        # an exact timeout/parse failure must be eligible for re-verification
        # on resume.  Only terminal-clean query results have exhausted their
        # candidate set safely.
        if prior_item.status in {CounterQueryStatus.FOUND, CounterQueryStatus.NOT_FOUND}:
            seen_candidates.update(prior_item.candidate_ids)
        else:
            # A partially completed query may contain both exact-verified and
            # failed candidates.  Reuse only the successful subset; failed or
            # unresolved candidates must remain eligible for retry.
            seen_candidates.update(prior_item.verified_candidate_ids)
            seen_candidates.update(prior_item.verified_candidate_keys)
        prior_verified_source_ids.update(prior_item.verified_source_ids)
        prior_verified_evidence_ids.update(prior_item.verified_evidence_ids)
    progress_attempts = sum(item.verification_attempt_count for item in previous.values())
    # Progress written by pre-budget clients has no attempt counter.  A
    # terminal ``found`` query can only be clean after its candidates passed
    # exact verification, so use its candidate count as a conservative legacy
    # floor rather than allowing a resume to silently reset the global cap.
    legacy_terminal_attempts = sum(
        item.candidate_count
        for item in previous.values()
        if item.status is CounterQueryStatus.FOUND
    )
    verification_attempts = max(
        resume.verification_attempts if resume is not None else 0,
        progress_attempts,
        legacy_terminal_attempts,
    )
    verification_budget_exhausted = verification_attempts >= plan.scope.max_verifications
    cost_fn = verification_cost or (lambda candidate: True)
    candidate_total = 0
    query_failures = 0
    query_completed = 0
    clean_misses = 0
    reason_codes: list[str] = []

    for item in plan.queries:
        prior = previous.get(item.query_id)
        prior_unresolved_candidate_ids: set[str] = set()
        prior_unresolved_state = False
        if prior is not None and prior.status in {
            CounterQueryStatus.PARTIAL,
            CounterQueryStatus.FAILED,
            CounterQueryStatus.BLOCKED,
        }:
            prior_unresolved_candidate_ids = set(prior.candidate_ids) - set(
                prior.verified_candidate_ids
            )
            if prior.candidate_count > 0 and not prior.verified_candidate_ids:
                # Legacy progress did not persist the verified subset.  Treat
                # every recorded candidate as unresolved until a later exact
                # verification proves it, rather than turning a changed
                # search ranking into a clean scoped miss.
                prior_unresolved_candidate_ids.update(prior.candidate_ids)
            prior_unresolved_state = bool(
                prior_unresolved_candidate_ids
                or prior.candidate_count > len(prior.verified_candidate_ids)
                or "COUNTER_AUTHORITY_PRIOR_CANDIDATE_UNRESOLVED"
                in prior.reason_codes
            )
        if prior is not None and prior.status in {
            CounterQueryStatus.NOT_FOUND,
            CounterQueryStatus.FOUND,
        }:
            progress_items.append(prior)
            query_completed += 1
            clean_misses += int(prior.status is CounterQueryStatus.NOT_FOUND)
            continue
        try:
            result = search(item.text, plan.scope.max_candidates_per_query)
        except TimeoutError:
            result = ProviderResult(
                status=ProviderResultStatus.ERROR,
                provider_id=plan.scope.provider_ids[0],
                message="COUNTER_AUTHORITY_PROVIDER_TIMEOUT",
                coverage_complete=False,
            )
            query_failures += 1
        except Exception as exc:  # provider boundary: preserve fail-closed semantics
            result = ProviderResult(
                status=ProviderResultStatus.ERROR,
                provider_id=plan.scope.provider_ids[0],
                message=f"COUNTER_AUTHORITY_PROVIDER_ERROR:{type(exc).__name__}",
                coverage_complete=False,
            )
            query_failures += 1

        provider_error = result.error_code.value if result.error_code else None
        if result.status is ProviderResultStatus.ERROR:
            query_failures += int(not isinstance(result.message, str) or not result.message.startswith("COUNTER_AUTHORITY_PROVIDER_"))
            query_status = (
                CounterQueryStatus.PARTIAL
                if prior_unresolved_state or (
                    prior is not None
                    and (
                        prior.candidate_count > 0
                        or prior.candidate_ids
                        or prior.verified_candidate_ids
                    )
                )
                else (
                    CounterQueryStatus.BLOCKED
                    if provider_error
                    in {"OFFICIAL_SOURCE_BLOCKED", "PRIVACY_EXTERNAL_QUERY_BLOCKED"}
                    else CounterQueryStatus.FAILED
                )
            )
            reason = provider_error or result.message or "COUNTER_AUTHORITY_PROVIDER_ERROR"
            error_reason_codes = [reason]
            if prior_unresolved_state:
                error_reason_codes.append("COUNTER_AUTHORITY_PRIOR_CANDIDATE_UNRESOLVED")
            reason_codes.extend(error_reason_codes)
            prior_candidate_ids = tuple(prior.candidate_ids) if prior is not None else ()
            prior_verified_candidate_ids = (
                tuple(prior.verified_candidate_ids) if prior is not None else ()
            )
            prior_verified_candidate_keys = (
                tuple(prior.verified_candidate_keys) if prior is not None else ()
            )
            prior_verified_sources = (
                tuple(prior.verified_source_ids) if prior is not None else ()
            )
            prior_verified_evidence = (
                tuple(prior.verified_evidence_ids) if prior is not None else ()
            )
            progress_items.append(
                CounterAuthorityQueryProgress(
                    query_id=item.query_id,
                    status=query_status,
                    provider_status=result.status.value,
                    provider_error_code=provider_error,
                    candidate_count=(prior.candidate_count if prior is not None else 0),
                    candidate_ids=prior_candidate_ids,
                    verified_candidate_ids=prior_verified_candidate_ids,
                    verified_candidate_keys=prior_verified_candidate_keys,
                    verified_count=len(prior_verified_sources),
                    verified_source_ids=prior_verified_sources,
                    verified_evidence_ids=prior_verified_evidence,
                    verification_attempt_count=(
                        prior.verification_attempt_count if prior is not None else 0
                    ),
                    reason_codes=tuple(error_reason_codes),
                )
            )
            continue

        candidates = list(result.candidates)[: plan.scope.max_candidates_per_query]
        verified_for_query: list[str] = []
        evidence_for_query: list[str] = []
        candidate_ids: list[str] = []
        verified_candidate_ids: list[str] = []
        verified_candidate_keys: list[str] = []
        query_reasons: list[str] = []
        verification_failures = False
        verification_attempt_count = 0
        for candidate in candidates:
            key = _candidate_key(candidate)
            if key in seen_candidates:
                continue
            candidate_ids.append(candidate.candidate_id)
            candidate_total += 1
            try:
                consumes_budget = bool(cost_fn(candidate))
            except Exception as exc:  # cost hooks are provider boundaries
                consumes_budget = True
                verification_failures = True
                query_reasons.append(
                    f"COUNTER_AUTHORITY_VERIFICATION_COST_ERROR:{type(exc).__name__}"
                )
            if consumes_budget and verification_attempts >= plan.scope.max_verifications:
                verification_budget_exhausted = True
                verification_failures = True
                query_reasons.append("COUNTER_AUTHORITY_VERIFICATION_BUDGET_EXHAUSTED")
                break
            if consumes_budget:
                verification_attempts += 1
                verification_attempt_count += 1
            seen_candidates.add(key)
            try:
                verification = verify(candidate)
            except TimeoutError:
                query_failures += 1
                verification_failures = True
                query_reasons.append("COUNTER_AUTHORITY_VERIFICATION_TIMEOUT")
                continue
            except Exception as exc:  # exact provider boundary
                query_failures += 1
                verification_failures = True
                query_reasons.append(f"COUNTER_AUTHORITY_VERIFICATION_ERROR:{type(exc).__name__}")
                continue
            if verification.evidence_eligible:
                verifications.append(verification)
                verified_candidate_ids.append(candidate.candidate_id)
                verified_candidate_keys.append(key)
                verified_for_query.append(verification.source.source_id if verification.source else "")
                evidence_for_query.extend(
                    item.evidence_id
                    for item in verification.evidence
                    if item.eligible_for_claim_support
                )
            else:
                verification_failures = True
                query_reasons.append(
                    verification.result.error_code.value
                    if verification.result.error_code
                    else "COUNTER_AUTHORITY_CANDIDATE_UNVERIFIED"
                )
        prior_candidate_ids = tuple(prior.candidate_ids) if prior is not None else ()
        merged_candidate_ids = tuple(
            dict.fromkeys([*prior_candidate_ids, *candidate_ids])
        )
        prior_verified_candidate_ids = (
            tuple(prior.verified_candidate_ids) if prior is not None else ()
        )
        prior_verified_candidate_keys = (
            tuple(prior.verified_candidate_keys) if prior is not None else ()
        )
        merged_verified_candidate_ids = tuple(
            dict.fromkeys([*prior_verified_candidate_ids, *verified_candidate_ids])
        )
        merged_verified_candidate_keys = tuple(
            dict.fromkeys([*prior_verified_candidate_keys, *verified_candidate_keys])
        )
        prior_verified_sources = (
            tuple(prior.verified_source_ids) if prior is not None else ()
        )
        prior_verified_evidence = (
            tuple(prior.verified_evidence_ids) if prior is not None else ()
        )
        merged_verified_sources = tuple(
            dict.fromkeys([*prior_verified_sources, *verified_for_query])
        )
        merged_verified_evidence = tuple(
            dict.fromkeys([*prior_verified_evidence, *evidence_for_query])
        )
        unresolved_after = prior_unresolved_state and (
            not prior_unresolved_candidate_ids
            or bool(
                prior_unresolved_candidate_ids
                - set(verified_candidate_ids)
            )
        )
        if unresolved_after:
            query_reasons.append("COUNTER_AUTHORITY_PRIOR_CANDIDATE_UNRESOLVED")
        if (
            result.status is ProviderResultStatus.PARTIAL
            or not result.coverage_complete
            or verification_failures
            or unresolved_after
        ):
            query_failures += 1
            query_status = CounterQueryStatus.PARTIAL
            query_reasons.append("COUNTER_AUTHORITY_SCOPE_PARTIAL")
        elif result.status is ProviderResultStatus.NOT_FOUND:
            query_status = CounterQueryStatus.NOT_FOUND
            clean_misses += 1
        else:
            query_status = CounterQueryStatus.FOUND
        if query_reasons:
            reason_codes.extend(query_reasons)
        progress_items.append(
            CounterAuthorityQueryProgress(
                query_id=item.query_id,
                status=query_status,
                provider_status=result.status.value,
                provider_error_code=provider_error,
                candidate_count=max(
                    prior.candidate_count if prior is not None else 0,
                    len(merged_candidate_ids),
                    len(candidates),
                ),
                verified_count=len(merged_verified_sources),
                candidate_ids=merged_candidate_ids,
                verified_candidate_ids=merged_verified_candidate_ids,
                verified_candidate_keys=merged_verified_candidate_keys,
                verified_source_ids=merged_verified_sources,
                verified_evidence_ids=merged_verified_evidence,
                verification_attempt_count=(
                    (prior.verification_attempt_count if prior is not None else 0)
                    + verification_attempt_count
                ),
                reason_codes=tuple(dict.fromkeys(query_reasons)),
            )
        )
        query_completed += int(query_status in {CounterQueryStatus.FOUND, CounterQueryStatus.NOT_FOUND})

    progress = CounterAuthorityProgress(
        plan_id=plan.plan_id,
        total_queries=len(plan.queries),
        verification_attempts=verification_attempts,
        next_ordinal=_next_retry_ordinal(plan, progress_items),
        queries=tuple(progress_items),
    )
    verified_source_ids = tuple(
        dict.fromkeys(
            [*prior_verified_source_ids]
            + [item.source.source_id for item in verifications if item.source is not None]
        )
    )
    verified_evidence_ids = tuple(
        dict.fromkeys(
            [*prior_verified_evidence_ids]
            + [
                evidence.evidence_id
                for item in verifications
                for evidence in item.evidence
                if evidence.eligible_for_claim_support
            ]
        )
    )
    all_clean = query_completed == len(plan.queries) and query_failures == 0
    overall_status: CounterAuthorityStatus
    relation_unclassified = bool(verified_source_ids)
    if relation_unclassified:
        # Identity/content verification is not semantic opposition
        # classification in the current preview, therefore it cannot produce a terminal
        # ``found_verified`` counter-authority decision.
        overall_status = CounterAuthorityStatus.PARTIAL
    elif verification_budget_exhausted:
        # A global exact-lookup cap is a coverage truncation, even when no
        # verified candidate survived the gate.  Never downgrade it to a
        # clean scoped miss or an opaque retry-only status.
        overall_status = CounterAuthorityStatus.PARTIAL
    elif all_clean and clean_misses == len(plan.queries):
        overall_status = CounterAuthorityStatus.NOT_FOUND_IN_SCOPE
    elif query_completed > 0 or verified_source_ids:
        overall_status = CounterAuthorityStatus.PARTIAL
    elif any(item.status is CounterQueryStatus.BLOCKED for item in progress_items):
        overall_status = CounterAuthorityStatus.BLOCKED
    else:
        overall_status = CounterAuthorityStatus.RETRY_REQUIRED
    final_reasons = tuple(dict.fromkeys(reason_codes))
    if relation_unclassified:
        final_reasons = tuple(
            dict.fromkeys((*final_reasons, "COUNTER_AUTHORITY_RELATION_UNCLASSIFIED"))
        )
    if overall_status is CounterAuthorityStatus.NOT_FOUND_IN_SCOPE:
        final_reasons = tuple(
            dict.fromkeys((*final_reasons, "COUNTER_AUTHORITY_NOT_FOUND_IN_SCOPE"))
        )
    elif overall_status is CounterAuthorityStatus.PARTIAL:
        final_reasons = tuple(dict.fromkeys((*final_reasons, "COUNTER_AUTHORITY_PARTIAL")))
    elif overall_status is CounterAuthorityStatus.RETRY_REQUIRED:
        final_reasons = tuple(
            dict.fromkeys((*final_reasons, "COUNTER_AUTHORITY_RETRY_REQUIRED"))
        )
    if verification_budget_exhausted:
        final_reasons = tuple(
            dict.fromkeys(
                (*final_reasons, "COUNTER_AUTHORITY_VERIFICATION_BUDGET_TRUNCATED")
            )
        )
    final_result = CounterAuthorityResult(
        status=overall_status,
        plan=plan,
        progress=progress,
        candidate_count=candidate_total,
        verified_count=len(verified_source_ids),
        verified_source_ids=verified_source_ids,
        verified_evidence_ids=verified_evidence_ids,
        verification_attempts=verification_attempts,
        verification_budget_exhausted=verification_budget_exhausted,
        coverage_complete=bool(all_clean and not verification_budget_exhausted),
        relation_status=(
            CounterAuthorityRelationStatus.UNCLASSIFIED
            if verified_source_ids
            else CounterAuthorityRelationStatus.NOT_APPLICABLE
        ),
        absence_claim_allowed=overall_status is CounterAuthorityStatus.NOT_FOUND_IN_SCOPE,
        reason_codes=final_reasons,
    )
    return final_result, verifications


def _next_retry_ordinal(
    plan: CounterAuthorityPlan,
    progress_items: Sequence[CounterAuthorityQueryProgress],
) -> int:
    """Return the first missing/retryable ordinal for a resumable cursor."""

    by_query_id = {item.query_id: item for item in progress_items}
    retryable = {
        CounterQueryStatus.PENDING,
        CounterQueryStatus.PARTIAL,
        CounterQueryStatus.FAILED,
        CounterQueryStatus.BLOCKED,
    }
    for query in plan.queries:
        current = by_query_id.get(query.query_id)
        if current is None or current.status in retryable:
            return query.ordinal
    return len(plan.queries) + 1


def _candidate_key(candidate: ProviderCandidate) -> str:
    identity = candidate.identity
    for value in (
        identity.canonical_jid if identity else None,
        identity.provider_document_id if identity else None,
        candidate.official_identifier,
        candidate.official_url,
        candidate.candidate_id,
    ):
        if value:
            return " ".join(str(value).split()).casefold()
    return candidate.candidate_id


__all__ = [
    "CounterAuthorityPlan",
    "CounterAuthorityProgress",
    "CounterAuthorityQuery",
    "CounterAuthorityQueryProgress",
    "CounterAuthorityResult",
    "CounterAuthorityRelationStatus",
    "CounterAuthorityScope",
    "CounterAuthorityStatus",
    "CounterAuthorityVerification",
    "CounterQueryStatus",
    "MAX_COUNTER_QUERIES",
    "MAX_COUNTER_VERIFICATIONS",
    "VerificationCost",
    "build_counter_authority_plan",
    "execute_bounded_counter_authority",
]
