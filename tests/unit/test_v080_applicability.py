"""Bounded, provider-neutral applicability resolver coverage for the current preview."""

from datetime import date

from alr_tw.contracts import (
    ApplicabilityRelationType,
    ApplicabilityRequest,
    ApplicabilityResolutionStatus,
    ApplicabilityResolver,
    ApplicabilitySourceRecord,
    ApplicabilityStatus,
    ApplicabilityValidationDecision,
    AuthorityLevel,
    TemporalApplicabilityStatus,
    TrustStatus,
    validate_applicability_resolution,
)


def _source(
    source_id: str,
    *,
    authority_level: AuthorityLevel = AuthorityLevel.STATUTE,
    effective_from: date | None = date(2020, 1, 1),
    effective_until: date | None = None,
    repealed_on: date | None = None,
    specializes_source_ids: list[str] | None = None,
    superior_source_ids: list[str] | None = None,
    supersedes_source_ids: list[str] | None = None,
    server_owned: bool = True,
    trust_status: TrustStatus = TrustStatus.EVIDENCE_ELIGIBLE,
    scope_key: str | None = "employment",
) -> ApplicabilitySourceRecord:
    return ApplicabilitySourceRecord(
        source_id=source_id,
        provider_id="official-law",
        authority_level=authority_level,
        effective_from=effective_from,
        effective_until=effective_until,
        repealed_on=repealed_on,
        specializes_source_ids=specializes_source_ids or [],
        superior_source_ids=superior_source_ids or [],
        supersedes_source_ids=supersedes_source_ids or [],
        server_owned=server_owned,
        trust_status=trust_status,
        scope_key=scope_key,
    )


def _request(*source_ids: str, as_of_date: date = date(2024, 1, 1)) -> ApplicabilityRequest:
    return ApplicabilityRequest(source_ids=list(source_ids), as_of_date=as_of_date)


def _resolver(*records: ApplicabilitySourceRecord) -> ApplicabilityResolver:
    """Build the normal server fixture with an independent catalog binding."""

    return ApplicabilityResolver(
        list(records),
        server_source_ids=[record.source_id for record in records],
    )


def test_special_law_explicitly_controls_general_law() -> None:
    general = _source("law-general")
    special = _source("law-special", specializes_source_ids=["law-general"])
    request = _request("law-general", "law-special")

    resolution = _resolver(general, special).resolve(request)

    assert resolution.resolution_status is ApplicabilityResolutionStatus.RESOLVED
    assert resolution.status is ApplicabilityStatus.APPLICABLE
    assert resolution.selected_source_ids == ["law-special"]
    assert resolution.controlling_source_id == "law-special"
    finding = resolution.relation_findings[0]
    assert finding.relation_type is ApplicabilityRelationType.SPECIAL_TO_GENERAL
    assert finding.stronger_source_id == "law-special"
    assert finding.weaker_source_id == "law-general"
    assert finding.active is True


def test_superior_source_controls_inferior_source() -> None:
    statute = _source("law-statute")
    constitution = _source(
        "law-constitution",
        authority_level=AuthorityLevel.CONSTITUTION,
        superior_source_ids=["law-statute"],
    )

    resolution = _resolver(statute, constitution).resolve(
        _request("law-statute", "law-constitution")
    )

    assert resolution.status is ApplicabilityStatus.APPLICABLE
    assert resolution.selected_source_ids == ["law-constitution"]
    assert resolution.relation_findings[0].relation_type is (
        ApplicabilityRelationType.SUPERIOR_TO_INFERIOR
    )


def test_temporal_successor_selects_new_version_only_when_effective() -> None:
    old = _source(
        "law-old",
        effective_from=date(2018, 1, 1),
        effective_until=None,
    )
    new = _source(
        "law-new",
        effective_from=date(2022, 1, 1),
        supersedes_source_ids=["law-old"],
    )
    resolver = _resolver(old, new)

    old_resolution = resolver.resolve(
        _request("law-old", "law-new", as_of_date=date(2021, 12, 31))
    )
    new_resolution = resolver.resolve(
        _request("law-old", "law-new", as_of_date=date(2023, 1, 1))
    )

    assert old_resolution.status is ApplicabilityStatus.APPLICABLE
    assert old_resolution.selected_source_ids == ["law-old"]
    assert any(
        assessment.temporal_status is TemporalApplicabilityStatus.NOT_YET_EFFECTIVE
        for assessment in old_resolution.candidate_assessments
    )
    assert new_resolution.status is ApplicabilityStatus.APPLICABLE
    assert new_resolution.selected_source_ids == ["law-new"]
    assert any(
        finding.relation_type is ApplicabilityRelationType.TEMPORAL_SUCCESSOR
        and finding.active
        for finding in new_resolution.relation_findings
    )


def test_historical_version_unavailable_fails_closed() -> None:
    future = _source("law-future", effective_from=date(2030, 1, 1))

    resolution = _resolver(future).resolve(
        _request("law-future", as_of_date=date(2024, 1, 1))
    )

    assert resolution.resolution_status is ApplicabilityResolutionStatus.BLOCKED
    assert resolution.status is ApplicabilityStatus.HISTORICAL_VERSION_UNAVAILABLE
    assert "APPLICABILITY_HISTORICAL_VERSION_UNAVAILABLE" in resolution.reason_codes


def test_unrelated_active_sources_are_indeterminate() -> None:
    first = _source("law-first")
    second = _source("law-second")

    resolution = _resolver(first, second).resolve(
        _request("law-first", "law-second")
    )

    assert resolution.resolution_status is ApplicabilityResolutionStatus.BLOCKED
    assert resolution.status is ApplicabilityStatus.INDETERMINATE
    assert "APPLICABILITY_RELATION_UNRESOLVED" in resolution.reason_codes


def test_untrusted_or_caller_owned_source_cannot_be_resolved() -> None:
    untrusted = _source("law-untrusted", trust_status=TrustStatus.EXTERNAL_CANDIDATE)

    resolution = _resolver(untrusted).resolve(
        _request("law-untrusted")
    )

    assert resolution.resolution_status is ApplicabilityResolutionStatus.BLOCKED
    assert resolution.status is ApplicabilityStatus.INDETERMINATE
    assert resolution.reason_codes == ["APPLICABILITY_SOURCE_NOT_VERIFIED"]

    caller_owned = _source("law-caller-owned", server_owned=False)
    caller_resolution = _resolver(caller_owned).resolve(
        _request("law-caller-owned")
    )
    assert caller_resolution.reason_codes == ["APPLICABILITY_SOURCE_NOT_SERVER_OWNED"]


def test_resolution_validator_recomputes_server_owned_facts() -> None:
    general = _source("law-general")
    special = _source("law-special", specializes_source_ids=["law-general"])
    request = _request("law-general", "law-special")
    resolver = _resolver(general, special)
    resolution = resolver.resolve(request)

    result = validate_applicability_resolution(
        resolution,
        request=request,
        server_sources=[general, special],
        server_source_ids=["law-general", "law-special"],
    )
    forged = resolution.model_copy(
        update={
            "selected_source_ids": ["law-general"],
            "controlling_source_id": "law-general",
        }
    )
    forged_result = validate_applicability_resolution(
        forged,
        request=request,
        server_sources=[general, special],
        server_source_ids=["law-general", "law-special"],
    )

    assert result.decision is ApplicabilityValidationDecision.ACCEPTED
    assert result.selected_source_ids == ["law-special"]
    assert forged_result.decision is ApplicabilityValidationDecision.BLOCKED
    assert "APPLICABILITY_SERVER_RESOLUTION_MISMATCH" in forged_result.reason_codes


def test_resolution_round_trip_and_scope_mismatch_are_safe() -> None:
    source = _source("law-scope")
    request = ApplicabilityRequest(
        source_ids=["law-scope"], as_of_date=date(2024, 1, 1), scope_key="unrelated"
    )
    resolution = _resolver(source).resolve(request)

    assert resolution.status is ApplicabilityStatus.NOT_APPLICABLE
    assert resolution.candidate_assessments[0].temporal_status is (
        TemporalApplicabilityStatus.INDETERMINATE
    )
    assert resolution.model_validate_json(resolution.model_dump_json()) == resolution


def test_missing_or_foreign_catalog_binding_fails_closed() -> None:
    source = _source("law-server")
    request = _request("law-server")

    missing = ApplicabilityResolver([source]).resolve(request)
    assert missing.resolution_status is ApplicabilityResolutionStatus.BLOCKED
    assert missing.reason_codes == ["APPLICABILITY_SERVER_CATALOG_BINDING_REQUIRED"]

    foreign = ApplicabilityResolver(
        [source], server_source_ids=["different-server-source"]
    ).resolve(request)
    assert foreign.resolution_status is ApplicabilityResolutionStatus.BLOCKED
    assert foreign.reason_codes == ["APPLICABILITY_SOURCE_NOT_SERVER_BOUND"]

    invalid = ApplicabilityResolver([source], server_source_ids=["law-server", "law-server"])
    invalid_resolution = invalid.resolve(request)
    assert invalid_resolution.reason_codes == [
        "APPLICABILITY_SERVER_CATALOG_BINDING_INVALID"
    ]


def test_model_copy_cannot_turn_external_record_into_bound_server_source() -> None:
    external = _source(
        "law-external",
        server_owned=False,
        trust_status=TrustStatus.EXTERNAL_CANDIDATE,
    )
    forged = external.model_copy(
        update={
            "server_owned": True,
            "trust_status": TrustStatus.OFFICIAL_VERIFIED,
        }
    )
    request = _request("law-external")

    resolution = ApplicabilityResolver(
        [forged], server_source_ids=["law-server-owned"]
    ).resolve(request)
    without_binding = ApplicabilityResolver([forged]).resolve(request)
    result = validate_applicability_resolution(
        without_binding,
        request=request,
        server_sources=[forged],
        server_source_ids=["law-server-owned"],
    )

    assert resolution.resolution_status is ApplicabilityResolutionStatus.BLOCKED
    assert resolution.reason_codes == ["APPLICABILITY_SOURCE_NOT_SERVER_BOUND"]
    assert result.decision is ApplicabilityValidationDecision.BLOCKED
    assert without_binding.reason_codes == ["APPLICABILITY_SERVER_CATALOG_BINDING_REQUIRED"]
