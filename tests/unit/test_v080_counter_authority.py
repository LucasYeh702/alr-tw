from __future__ import annotations

from datetime import UTC, datetime, timedelta

from alr_tw.contracts.providers import (
    CandidateIdentity,
    ProviderCandidate,
    ProviderErrorCode,
    ProviderResult,
    ProviderResultStatus,
)
from alr_tw.contracts.sources import (
    EvidenceSectionType,
    EvidenceSpan,
    MaterialType,
    SourceRecord,
    SourceTier,
    TrustStatus,
)
from alr_tw.research.counter_authority import (
    MAX_COUNTER_QUERY_CHARS,
    CounterAuthorityPlan,
    CounterQueryStatus,
    CounterAuthorityStatus,
    CounterAuthorityVerification,
    build_counter_authority_plan,
    execute_bounded_counter_authority,
)


def _candidate(identifier: str = "DEMO,130,民,1,20990101,1") -> ProviderCandidate:
    return ProviderCandidate(
        candidate_id=f"candidate-{identifier}",
        provider_id="synthetic-judgment-search",
        title="合成相反見解裁判",
        official_identifier=identifier,
        identity=CandidateIdentity(canonical_jid=identifier),
        candidate_rank=1,
        metadata={"candidate_only": True},
    )


def _verified(candidate: ProviderCandidate) -> CounterAuthorityVerification:
    now = datetime.now(UTC)
    text = "本院認定合成反面見解。"
    source = SourceRecord(
        source_id=f"source-{candidate.candidate_id}",
        source_key=f"judgment:{candidate.official_identifier}",
        source_version_id=f"judgment:{candidate.official_identifier}:v1",
        material_type=MaterialType.JUDGMENT,
        provider_id="official_judicial_yuan_judgments",
        source_tier=SourceTier.OFFICIAL,
        trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
        official_identifier=candidate.official_identifier,
        official_url="https://judgment.judicial.gov.tw/FJUD/data.aspx?id=synthetic",
        citation="合成法院130年度民字第1號判決",
        fetched_at=now,
        verified_at=now,
        expires_at=now + timedelta(hours=1),
        content_hash=EvidenceSpan.hash_text(text),
        normalized_content_hash=EvidenceSpan.hash_text(text),
        normalized_text=text,
    )
    evidence = EvidenceSpan.from_exact_text(
        evidence_id=f"evidence-{candidate.candidate_id}",
        source_id=source.source_id,
        section_id="reasoning-1",
        section_type=EvidenceSectionType.COURT_REASONING,
        exact_text=text,
        eligible_for_claim_support=True,
    )
    return CounterAuthorityVerification(
        candidate_id=candidate.candidate_id,
        result=ProviderResult(
            status=ProviderResultStatus.FOUND,
            provider_id="official_judicial_yuan_judgments",
            source_ids=[source.source_id],
            evidence_ids=[evidence.evidence_id],
            coverage_complete=True,
        ),
        source=source,
        evidence=(evidence,),
    )


def _plan() -> CounterAuthorityPlan:
    return build_counter_authority_plan("侵權行為舉證責任")


def test_plan_is_deterministic_and_bounded() -> None:
    first = _plan()
    second = _plan()

    assert first == second
    assert len(first.queries) <= 4
    assert first.plan_id == second.plan_id
    assert first.scope.global_absence_claim_allowed is False


def test_plan_compresses_long_natural_language_into_official_search_queries() -> None:
    query = (
        "以下是純合成情境，涉及示範法第27條的爭點詞擷取與查詢長度限制，"
        "並且還有事件順序、通知時間、文件種類等用來測試壓縮的大量虛構敘述。"
        * 3
    )

    plan = build_counter_authority_plan(query)

    assert all(len(item.text) <= MAX_COUNTER_QUERY_CHARS for item in plan.queries)
    assert all(
        "相反見解" in item.text or "不同見解" in item.text
        for item in plan.queries
    )
    assert any("示範法第27條" in item.text for item in plan.queries)


def test_verified_hit_requires_exact_server_evidence() -> None:
    calls: list[str] = []
    candidate = _candidate()

    def search(query: str, limit: int) -> ProviderResult:
        del limit
        calls.append(query)
        return ProviderResult(
            status=ProviderResultStatus.FOUND,
            provider_id="official_judicial_yuan_judgments",
            candidates=[candidate],
            coverage_complete=True,
        )

    result, verifications = execute_bounded_counter_authority(
        _plan(),
        search=search,
        verify=_verified,
    )

    assert result.status is CounterAuthorityStatus.PARTIAL
    assert result.absence_claim_allowed is False
    assert result.global_consensus_claim_allowed is False
    assert result.relation_status.value == "relation_unclassified"
    assert "COUNTER_AUTHORITY_RELATION_UNCLASSIFIED" in result.reason_codes
    assert result.verified_count == 1
    assert len(verifications) == 1
    assert len(calls) == 2


def test_clean_scoped_miss_allows_only_bounded_absence_language() -> None:
    def search(query: str, limit: int) -> ProviderResult:
        del query, limit
        return ProviderResult(
            status=ProviderResultStatus.NOT_FOUND,
            provider_id="official_judicial_yuan_judgments",
            coverage_complete=True,
        )

    result, _ = execute_bounded_counter_authority(
        _plan(),
        search=search,
        verify=lambda candidate: _verified(candidate),
    )

    assert result.status is CounterAuthorityStatus.NOT_FOUND_IN_SCOPE
    assert result.absence_claim_allowed is True
    assert result.global_consensus_claim_allowed is False
    assert result.relation_status.value == "not_applicable"
    assert "COUNTER_AUTHORITY_NOT_FOUND_IN_SCOPE" in result.reason_codes


def test_provider_failure_is_partial_and_never_absence() -> None:
    calls = 0

    def search(query: str, limit: int) -> ProviderResult:
        nonlocal calls
        del query, limit
        calls += 1
        if calls == 2:
            return ProviderResult(
                status=ProviderResultStatus.ERROR,
                provider_id="official_judicial_yuan_judgments",
                error_code=ProviderErrorCode.OFFICIAL_SOURCE_UNAVAILABLE,
                coverage_complete=False,
            )
        return ProviderResult(
            status=ProviderResultStatus.NOT_FOUND,
            provider_id="official_judicial_yuan_judgments",
            coverage_complete=True,
        )

    result, _ = execute_bounded_counter_authority(
        _plan(),
        search=search,
        verify=lambda candidate: _verified(candidate),
    )

    assert result.status is CounterAuthorityStatus.PARTIAL
    assert result.absence_claim_allowed is False
    assert "OFFICIAL_SOURCE_UNAVAILABLE" in result.reason_codes


def test_mixed_verified_and_unverified_candidates_never_becomes_verified_scope() -> None:
    good = _candidate("DEMO,130,民,1,20990101,1")
    bad = _candidate("DEMO,130,民,2,20990101,1")

    def search(query: str, limit: int) -> ProviderResult:
        del query, limit
        return ProviderResult(
            status=ProviderResultStatus.FOUND,
            provider_id="official_judicial_yuan_judgments",
            candidates=[good, bad],
            coverage_complete=True,
        )

    def verify(item: ProviderCandidate) -> CounterAuthorityVerification:
        if item.candidate_id == good.candidate_id:
            return _verified(item)
        return CounterAuthorityVerification(
            candidate_id=item.candidate_id,
            result=ProviderResult(
                status=ProviderResultStatus.ERROR,
                provider_id="official_judicial_yuan_judgments",
                error_code=ProviderErrorCode.OFFICIAL_PARSE_ERROR,
                coverage_complete=False,
            ),
        )

    result, verifications = execute_bounded_counter_authority(
        _plan(),
        search=search,
        verify=verify,
    )

    assert result.status is CounterAuthorityStatus.PARTIAL
    assert result.absence_claim_allowed is False
    assert result.verified_count == 1
    assert len(verifications) == 1
    assert "COUNTER_AUTHORITY_RELATION_UNCLASSIFIED" in result.reason_codes
    assert "OFFICIAL_PARSE_ERROR" in result.reason_codes


def test_unverified_candidate_is_not_promoted() -> None:
    candidate = _candidate()

    def search(query: str, limit: int) -> ProviderResult:
        del query, limit
        return ProviderResult(
            status=ProviderResultStatus.FOUND,
            provider_id="synthetic-judgment-search",
            candidates=[candidate],
            coverage_complete=True,
        )

    def reject(candidate: ProviderCandidate) -> CounterAuthorityVerification:
        return CounterAuthorityVerification(
            candidate_id=candidate.candidate_id,
            result=ProviderResult(
                status=ProviderResultStatus.FOUND,
                provider_id="official_judicial_yuan_judgments",
                coverage_complete=True,
            ),
        )

    result, verifications = execute_bounded_counter_authority(
        _plan(),
        search=search,
        verify=reject,
    )

    assert result.status is CounterAuthorityStatus.PARTIAL
    assert result.verified_count == 0
    assert verifications == []
    assert result.absence_claim_allowed is False


def test_duplicate_candidates_are_verified_once_with_four_query_bound() -> None:
    candidate = _candidate()
    verify_calls = 0

    def search(query: str, limit: int) -> ProviderResult:
        del query, limit
        return ProviderResult(
            status=ProviderResultStatus.FOUND,
            provider_id="official_judicial_yuan_judgments",
            candidates=[candidate],
            coverage_complete=True,
        )

    def verify(item: ProviderCandidate) -> CounterAuthorityVerification:
        nonlocal verify_calls
        verify_calls += 1
        return _verified(item)

    result, _ = execute_bounded_counter_authority(
        build_counter_authority_plan("爭點", registered_locators=["同一裁判"]),
        search=search,
        verify=verify,
    )

    assert len(result.plan.queries) <= 4
    assert len(result.progress.queries) == len(result.plan.queries)
    assert verify_calls == 1
    assert result.verified_count == 1


def test_progress_is_serializable_and_can_resume_without_repeating_clean_queries() -> None:
    plan = _plan()
    first_query = plan.queries[0].query_id
    first_progress = {
        "schema_version": "alr-tw.counter-authority-progress/v1",
        "plan_id": plan.plan_id,
        "total_queries": len(plan.queries),
        "next_ordinal": 2,
        "queries": [
            {
                "query_id": first_query,
                "status": "not_found",
                "provider_status": "not_found",
                "candidate_count": 0,
                "verified_count": 0,
                "candidate_ids": [],
                "verified_source_ids": [],
                "verified_evidence_ids": [],
                "reason_codes": [],
            }
        ],
    }

    calls = 0

    def search(query: str, limit: int) -> ProviderResult:
        nonlocal calls
        del query, limit
        calls += 1
        return ProviderResult(
            status=ProviderResultStatus.NOT_FOUND,
            provider_id="official_judicial_yuan_judgments",
            coverage_complete=True,
        )

    from alr_tw.research.counter_authority import CounterAuthorityProgress

    result, _ = execute_bounded_counter_authority(
        plan,
        search=search,
        verify=lambda item: _verified(item),
        resume=CounterAuthorityProgress.model_validate(first_progress),
    )

    assert calls == len(plan.queries) - 1
    assert result.status is CounterAuthorityStatus.NOT_FOUND_IN_SCOPE


def test_partial_progress_cursor_retries_failed_query_only() -> None:
    plan = _plan()
    first_query = plan.queries[0].query_id
    completed_queries = [
        {
            "query_id": item.query_id,
            "status": "not_found",
            "provider_status": "not_found",
            "candidate_count": 0,
            "verified_count": 0,
            "candidate_ids": [],
            "verified_source_ids": [],
            "verified_evidence_ids": [],
            "reason_codes": [],
        }
        for item in plan.queries[1:]
    ]
    failed = {
        "schema_version": "alr-tw.counter-authority-progress/v1",
        "plan_id": plan.plan_id,
        "total_queries": len(plan.queries),
        "next_ordinal": 1,
        "queries": [
            {
                "query_id": first_query,
                "status": "failed",
                "provider_status": "error",
                "provider_error_code": "OFFICIAL_SOURCE_UNAVAILABLE",
                "candidate_count": 0,
                "verified_count": 0,
                "candidate_ids": [],
                "verified_source_ids": [],
                "verified_evidence_ids": [],
                "reason_codes": ["OFFICIAL_SOURCE_UNAVAILABLE"],
            },
            *completed_queries,
        ],
    }
    from alr_tw.research.counter_authority import CounterAuthorityProgress

    calls: list[str] = []

    def search(query: str, limit: int) -> ProviderResult:
        del limit
        calls.append(query)
        return ProviderResult(
            status=ProviderResultStatus.NOT_FOUND,
            provider_id="official_judicial_yuan_judgments",
            coverage_complete=True,
        )

    resume_progress = CounterAuthorityProgress.model_validate(failed)
    assert resume_progress.complete is False
    result, _ = execute_bounded_counter_authority(
        plan,
        search=search,
        verify=lambda item: _verified(item),
        resume=resume_progress,
    )

    assert result.progress.next_ordinal == len(plan.queries) + 1
    assert result.progress.complete is True
    assert len(calls) == 1
    assert result.status is CounterAuthorityStatus.NOT_FOUND_IN_SCOPE
    assert result.absence_claim_allowed is True


def test_resume_retries_candidate_from_partial_exact_failure() -> None:
    plan = _plan()
    candidate = _candidate("DEMO,130,民,3,20990101,1")
    first_search_calls = 0
    first_verify_calls = 0

    def first_search(query: str, limit: int) -> ProviderResult:
        nonlocal first_search_calls
        del limit
        first_search_calls += 1
        if first_search_calls == 1:
            return ProviderResult(
                status=ProviderResultStatus.FOUND,
                provider_id="official_judicial_yuan_judgments",
                candidates=[candidate],
                coverage_complete=True,
            )
        return ProviderResult(
            status=ProviderResultStatus.NOT_FOUND,
            provider_id="official_judicial_yuan_judgments",
            coverage_complete=True,
        )

    def timeout_verify(item: ProviderCandidate) -> CounterAuthorityVerification:
        nonlocal first_verify_calls
        first_verify_calls += 1
        raise TimeoutError(item.candidate_id)

    first_result, _ = execute_bounded_counter_authority(
        plan,
        search=first_search,
        verify=timeout_verify,
    )
    assert first_result.status is CounterAuthorityStatus.PARTIAL
    assert first_result.progress.queries[0].status.value == "partial"

    from alr_tw.research.counter_authority import CounterAuthorityProgress

    resume = CounterAuthorityProgress.model_validate(
        first_result.progress.model_dump(mode="json")
    )
    resumed_search_calls = 0
    resumed_verify_calls = 0

    def resumed_search(query: str, limit: int) -> ProviderResult:
        nonlocal resumed_search_calls
        del query, limit
        resumed_search_calls += 1
        return ProviderResult(
            status=ProviderResultStatus.FOUND,
            provider_id="official_judicial_yuan_judgments",
            candidates=[candidate],
            coverage_complete=True,
        )

    def resumed_verify(item: ProviderCandidate) -> CounterAuthorityVerification:
        nonlocal resumed_verify_calls
        resumed_verify_calls += 1
        return _verified(item)

    resumed_result, verifications = execute_bounded_counter_authority(
        plan,
        search=resumed_search,
        verify=resumed_verify,
        resume=resume,
    )

    assert first_verify_calls == 1
    assert resumed_search_calls == 1
    assert resumed_verify_calls == 1
    assert len(verifications) == 1
    assert resumed_result.status is CounterAuthorityStatus.PARTIAL
    assert resumed_result.relation_status.value == "relation_unclassified"
    assert resumed_result.absence_claim_allowed is False


def test_resume_changed_search_cannot_turn_unresolved_candidate_into_clean_miss() -> None:
    plan = _plan()
    candidate = _candidate("DEMO,130,民,4,20990101,1")
    search_calls = 0

    def first_search(query: str, limit: int) -> ProviderResult:
        nonlocal search_calls
        del query, limit
        search_calls += 1
        if search_calls == 1:
            return ProviderResult(
                status=ProviderResultStatus.FOUND,
                provider_id="official_judicial_yuan_judgments",
                candidates=[candidate],
                coverage_complete=True,
            )
        return ProviderResult(
            status=ProviderResultStatus.NOT_FOUND,
            provider_id="official_judicial_yuan_judgments",
            coverage_complete=True,
        )

    first_result, _ = execute_bounded_counter_authority(
        plan,
        search=first_search,
        verify=lambda item: (_ for _ in ()).throw(TimeoutError(item.candidate_id)),
    )
    assert first_result.progress.queries[0].status.value == "partial"

    from alr_tw.research.counter_authority import CounterAuthorityProgress

    resume = CounterAuthorityProgress.model_validate(
        first_result.progress.model_dump(mode="json")
    )
    resumed_search_calls = 0

    def changed_search(query: str, limit: int) -> ProviderResult:
        nonlocal resumed_search_calls
        del query, limit
        resumed_search_calls += 1
        return ProviderResult(
            status=ProviderResultStatus.NOT_FOUND,
            provider_id="official_judicial_yuan_judgments",
            coverage_complete=True,
        )

    resumed, _ = execute_bounded_counter_authority(
        plan,
        search=changed_search,
        verify=lambda item: _verified(item),
        resume=resume,
    )

    assert resumed_search_calls == 1
    assert resumed.status is CounterAuthorityStatus.PARTIAL
    assert resumed.absence_claim_allowed is False
    assert "COUNTER_AUTHORITY_PRIOR_CANDIDATE_UNRESOLVED" in resumed.reason_codes


def test_unresolved_candidate_survives_error_then_miss_across_json_resumes() -> None:
    plan = _plan()
    candidate = _candidate("DEMO,130,民,5,20990101,1")
    phase = 1

    def search(query: str, limit: int) -> ProviderResult:
        del limit
        if query != plan.queries[0].text:
            return ProviderResult(
                status=ProviderResultStatus.NOT_FOUND,
                provider_id="official_judicial_yuan_judgments",
                coverage_complete=True,
            )
        if phase == 1:
            return ProviderResult(
                status=ProviderResultStatus.FOUND,
                provider_id="official_judicial_yuan_judgments",
                candidates=[candidate],
                coverage_complete=True,
            )
        if phase == 2:
            return ProviderResult(
                status=ProviderResultStatus.ERROR,
                provider_id="official_judicial_yuan_judgments",
                error_code=ProviderErrorCode.OFFICIAL_SOURCE_UNAVAILABLE,
                coverage_complete=False,
            )
        return ProviderResult(
            status=ProviderResultStatus.NOT_FOUND,
            provider_id="official_judicial_yuan_judgments",
            coverage_complete=True,
        )

    first, _ = execute_bounded_counter_authority(
        plan,
        search=search,
        verify=lambda item: (_ for _ in ()).throw(TimeoutError(item.candidate_id)),
    )
    first_q = first.progress.queries[0]
    assert first_q.status is CounterQueryStatus.PARTIAL
    assert first_q.candidate_ids == (candidate.candidate_id,)
    assert first.absence_claim_allowed is False

    from alr_tw.research.counter_authority import CounterAuthorityProgress

    phase = 2
    second, _ = execute_bounded_counter_authority(
        plan,
        search=search,
        verify=_verified,
        resume=CounterAuthorityProgress.model_validate(
            first.progress.model_dump(mode="json")
        ),
    )
    second_q = second.progress.queries[0]
    assert second_q.status is CounterQueryStatus.PARTIAL
    assert second_q.candidate_ids == (candidate.candidate_id,)
    assert "COUNTER_AUTHORITY_PRIOR_CANDIDATE_UNRESOLVED" in second.reason_codes
    assert second.absence_claim_allowed is False

    phase = 3
    third, _ = execute_bounded_counter_authority(
        plan,
        search=search,
        verify=_verified,
        resume=CounterAuthorityProgress.model_validate(
            second.progress.model_dump(mode="json")
        ),
    )
    third_q = third.progress.queries[0]
    assert third.status is CounterAuthorityStatus.PARTIAL
    assert third_q.status is CounterQueryStatus.PARTIAL
    assert third_q.candidate_ids == (candidate.candidate_id,)
    assert "COUNTER_AUTHORITY_PRIOR_CANDIDATE_UNRESOLVED" in third.reason_codes
    assert third.absence_claim_allowed is False


def test_verified_subset_survives_partial_then_repeated_clean_misses() -> None:
    plan = _plan()
    candidate = _candidate("DEMO,130,民,6,20990101,1")
    phase = 1

    def search(query: str, limit: int) -> ProviderResult:
        del query, limit
        if phase == 1:
            return ProviderResult(
                status=ProviderResultStatus.PARTIAL,
                provider_id="official_judicial_yuan_judgments",
                candidates=[candidate],
                coverage_complete=False,
            )
        return ProviderResult(
            status=ProviderResultStatus.NOT_FOUND,
            provider_id="official_judicial_yuan_judgments",
            coverage_complete=True,
        )

    first, _ = execute_bounded_counter_authority(
        plan,
        search=search,
        verify=_verified,
    )
    assert first.status is CounterAuthorityStatus.PARTIAL
    assert first.verified_count == 1
    assert first.absence_claim_allowed is False

    from alr_tw.research.counter_authority import CounterAuthorityProgress

    phase = 2
    second, _ = execute_bounded_counter_authority(
        plan,
        search=search,
        verify=_verified,
        resume=CounterAuthorityProgress.model_validate(
            first.progress.model_dump(mode="json")
        ),
    )
    assert second.status is CounterAuthorityStatus.PARTIAL
    assert second.verified_count == 1
    assert second.relation_status.value == "relation_unclassified"
    assert second.absence_claim_allowed is False

    third, _ = execute_bounded_counter_authority(
        plan,
        search=search,
        verify=_verified,
        resume=CounterAuthorityProgress.model_validate(
            second.progress.model_dump(mode="json")
        ),
    )
    assert third.status is CounterAuthorityStatus.PARTIAL
    assert third.verified_count == 1
    assert third.relation_status.value == "relation_unclassified"
    assert third.absence_claim_allowed is False


def test_global_verification_budget_truncates_worst_case_and_resume_cannot_bypass() -> None:
    plan = build_counter_authority_plan(
        "核心反向見解",
        issue_proposals=[("issue-a", "要件甲"), ("issue-b", "要件乙")],
        registered_locators=["法院判決丁"],
        max_queries=4,
        max_verifications=5,
    )
    search_calls = 0
    verify_calls = 0

    def search(query: str, limit: int) -> ProviderResult:
        nonlocal search_calls
        del query
        search_calls += 1
        candidates = [
            _candidate(f"DEMO,130,民,{search_calls * 10 + index},20990101,1")
            for index in range(limit)
        ]
        return ProviderResult(
            status=ProviderResultStatus.FOUND,
            provider_id="official_judicial_yuan_judgments",
            candidates=candidates,
            coverage_complete=True,
        )

    def verify(item: ProviderCandidate) -> CounterAuthorityVerification:
        nonlocal verify_calls
        verify_calls += 1
        return _verified(item)

    first, _ = execute_bounded_counter_authority(
        plan,
        search=search,
        verify=verify,
    )

    assert len(plan.queries) == 4
    assert search_calls == 4
    assert verify_calls == 5
    assert first.verification_attempts == 5
    assert first.verification_budget_exhausted is True
    assert first.status is CounterAuthorityStatus.PARTIAL
    assert first.absence_claim_allowed is False
    assert "COUNTER_AUTHORITY_VERIFICATION_BUDGET_TRUNCATED" in first.reason_codes

    # A resumable client may retry the partial query set, but the persisted
    # whole-plan budget prevents another exact verification attempt.
    resume = type(first.progress).model_validate(first.progress.model_dump(mode="json"))
    resumed_search_calls = 0
    resumed_verify_calls = 0

    def resumed_search(query: str, limit: int) -> ProviderResult:
        nonlocal resumed_search_calls
        del query
        resumed_search_calls += 1
        return search("resume", limit)

    def resumed_verify(item: ProviderCandidate) -> CounterAuthorityVerification:
        nonlocal resumed_verify_calls
        resumed_verify_calls += 1
        return _verified(item)

    resumed, _ = execute_bounded_counter_authority(
        plan,
        search=resumed_search,
        verify=resumed_verify,
        resume=resume,
    )
    assert resumed_search_calls == 3
    assert resumed_verify_calls == 0
    assert resumed.verification_attempts == 5
    assert resumed.verification_budget_exhausted is True
    assert resumed.status is CounterAuthorityStatus.PARTIAL
    assert resumed.absence_claim_allowed is False


def test_reused_server_verified_candidate_does_not_consume_exact_budget() -> None:
    plan = build_counter_authority_plan(
        "可重用官方來源",
        issue_proposals=[("issue-a", "要件甲"), ("issue-b", "要件乙")],
        registered_locators=["法院判決丁"],
        max_queries=4,
        max_verifications=1,
    )
    search_calls = 0
    verify_calls = 0

    def search(query: str, limit: int) -> ProviderResult:
        nonlocal search_calls
        del limit
        search_calls += 1
        return ProviderResult(
            status=ProviderResultStatus.FOUND,
            provider_id="official_judicial_yuan_judgments",
            candidates=[_candidate(f"DEMO,130,民,{search_calls},20990101,1")],
            coverage_complete=True,
        )

    def verify(item: ProviderCandidate) -> CounterAuthorityVerification:
        nonlocal verify_calls
        verify_calls += 1
        return _verified(item)

    result, verifications = execute_bounded_counter_authority(
        plan,
        search=search,
        verify=verify,
        # The provider executor supplies this callback only for a source that
        # is already server-verified in the same run.
        verification_cost=lambda candidate: False,
    )

    assert verify_calls == len(plan.queries)
    assert len(verifications) == len(plan.queries)
    assert result.verification_attempts == 0
    assert result.verification_budget_exhausted is False
    assert result.status is CounterAuthorityStatus.PARTIAL
    assert result.absence_claim_allowed is False
