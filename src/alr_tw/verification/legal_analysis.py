"""Fail-closed structural validation for unified legal-analysis proposals."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from alr_tw.contracts.civil_analysis import (
    AnalysisValidationSeverity,
    BurdenBearer,
    BurdenShiftStatus,
    CounterAuthorityStatus,
    ElementAssessmentStatus,
    FindingState,
    ProceduralStage,
    StandardOfProof,
)
from alr_tw.contracts.legal_analysis import (
    AnalysisCoverageScope,
    CivilSubstantiveAnalysis,
    DomainDefense,
    DomainBurdenOfProof,
    LegalAnalysisDecision,
    LegalAnalysisEnvelope,
    LegalAnalysisProfile,
    LegalAnalysisValidationFinding,
    LegalAnalysisValidationResult,
)
from alr_tw.contracts.legal_context import (
    AuthorityStatus,
    LegalContextResult,
    LegalValidityStatus,
    TemporalApplicabilityStatus,
)
from alr_tw.contracts.sources import EvidenceSpan, SourceRecord, TrustStatus

_SUPPORTIVE_FACT_STATES = {
    FindingState.ADMITTED,
    FindingState.SUPPORTED,
    FindingState.PROVEN,
}

_CORE_DIMENSIONS: dict[LegalAnalysisProfile, frozenset[str]] = {
    LegalAnalysisProfile.CIVIL_PROCEDURE: frozenset(
        {
            "jurisdiction",
            "party_capacity",
            "standing",
            "claim_subject",
            "procedural_prerequisite",
        }
    ),
    LegalAnalysisProfile.CRIMINAL_SUBSTANTIVE: frozenset(
        {"offense_elements", "unlawfulness", "culpability"}
    ),
    LegalAnalysisProfile.CRIMINAL_PROCEDURE: frozenset(
        {
            "proceeding_stage",
            "prosecution_prerequisite",
            "evidence_admissibility",
            "burden_and_standard",
        }
    ),
    LegalAnalysisProfile.ADMINISTRATIVE: frozenset(
        {
            "action_classification",
            "authority_basis",
            "competence",
            "procedure",
            "substantive_legality",
            "discretion_and_purpose",
            "remedy_type",
            "standing",
            "prior_proceeding",
            "filing_period",
            "remedy_interest",
        }
    ),
    LegalAnalysisProfile.CONSTITUTIONAL_REVIEW: frozenset(
        {
            "protected_right",
            "interference",
            "legal_reservation",
            "legitimate_aim",
            "proportionality",
        }
    ),
}

_REFUSAL_CODES: dict[LegalAnalysisProfile, dict[str, str]] = {
    LegalAnalysisProfile.CIVIL_PROCEDURE: {
        "jurisdiction": "CIVIL_PROCEDURE_JURISDICTION_UNRESOLVED",
        "standing": "CIVIL_PROCEDURE_STANDING_UNRESOLVED",
        "procedural_prerequisite": "CIVIL_PROCEDURE_PREREQUISITE_UNRESOLVED",
        "appeal": "CIVIL_PROCEDURE_APPEAL_POSTURE_UNRESOLVED",
    },
    LegalAnalysisProfile.CRIMINAL_SUBSTANTIVE: {
        "offense_elements": "CRIMINAL_OFFENSE_ELEMENTS_UNRESOLVED",
        "unlawfulness": "CRIMINAL_UNLAWFULNESS_UNRESOLVED",
        "culpability": "CRIMINAL_CULPABILITY_UNRESOLVED",
        "intent_or_negligence": "CRIMINAL_MENS_REA_UNRESOLVED",
    },
    LegalAnalysisProfile.CRIMINAL_PROCEDURE: {
        "proceeding_stage": "CRIMINAL_PROCEDURE_STAGE_UNRESOLVED",
        "prosecution_prerequisite": "CRIMINAL_PROSECUTION_PREREQUISITE_UNRESOLVED",
        "evidence_admissibility": "CRIMINAL_EVIDENCE_ADMISSIBILITY_UNRESOLVED",
        "coercive_measure": "CRIMINAL_COERCIVE_MEASURE_UNRESOLVED",
    },
    LegalAnalysisProfile.ADMINISTRATIVE: {
        "action_classification": "ADMINISTRATIVE_ACTION_CLASSIFICATION_UNRESOLVED",
        "authority_basis": "ADMINISTRATIVE_AUTHORITY_BASIS_UNRESOLVED",
        "competence": "ADMINISTRATIVE_COMPETENCE_UNRESOLVED",
        "procedure": "ADMINISTRATIVE_PROCEDURE_UNRESOLVED",
        "form": "ADMINISTRATIVE_FORM_UNRESOLVED",
        "substantive_legality": "ADMINISTRATIVE_SUBSTANTIVE_LEGALITY_UNRESOLVED",
        "discretion_and_purpose": "ADMINISTRATIVE_DISCRETION_UNRESOLVED",
        "remedy_type": "ADMINISTRATIVE_REMEDY_TYPE_UNRESOLVED",
        "standing": "ADMINISTRATIVE_STANDING_UNRESOLVED",
        "prior_proceeding": "ADMINISTRATIVE_PRIOR_PROCEEDING_UNRESOLVED",
        "filing_period": "ADMINISTRATIVE_FILING_PERIOD_UNRESOLVED",
        "remedy_interest": "ADMINISTRATIVE_REMEDY_INTEREST_UNRESOLVED",
        "proportionality": "ADMINISTRATIVE_PROPORTIONALITY_UNRESOLVED",
        "legitimate_expectation": "ADMINISTRATIVE_LEGITIMATE_EXPECTATION_UNRESOLVED",
    },
    LegalAnalysisProfile.CONSTITUTIONAL_REVIEW: {
        "review_admissibility": "CONSTITUTIONAL_REVIEW_ADMISSIBILITY_UNRESOLVED",
        "protected_right": "CONSTITUTIONAL_PROTECTED_RIGHT_UNRESOLVED",
        "proportionality": "CONSTITUTIONAL_PROPORTIONALITY_UNRESOLVED",
        "judgment_effect": "CONSTITUTIONAL_JUDGMENT_EFFECT_UNRESOLVED",
    },
}


def validate_legal_analysis(
    analysis: LegalAnalysisEnvelope,
    *,
    server_sources: Sequence[SourceRecord],
    server_evidence: Sequence[EvidenceSpan],
    legal_context: LegalContextResult,
    server_fact_states: Mapping[str, FindingState] | None = None,
    validated_at: datetime | None = None,
) -> LegalAnalysisValidationResult:
    """Validate all selected branches without performing substantive legal reasoning."""

    timestamp = validated_at or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("validated_at must be timezone-aware")

    profiles = [LegalAnalysisProfile(branch.profile) for branch in analysis.analyses]
    sources = {source.source_id: source for source in server_sources}
    evidence = {item.evidence_id: item for item in server_evidence}
    fact_states = dict(server_fact_states or {})
    contexts = {record.source_id: record for record in legal_context.records}
    findings: list[LegalAnalysisValidationFinding] = []
    seen_findings: set[tuple[str, str]] = set()

    source_groups: list[tuple[str, list[str]]] = []
    normative_groups: list[tuple[str, list[str]]] = []
    evidence_groups: list[tuple[str, list[str]]] = []
    fact_groups: list[tuple[str, list[str]]] = []
    support_targets: list[tuple[str, list[str], list[str]]] = []
    issue_count = 0
    claim_count = 0
    element_count = 0
    defense_count = 0

    def add(
        code: str,
        severity: AnalysisValidationSeverity,
        path: str,
        message: str,
    ) -> None:
        key = (code, path)
        if key in seen_findings:
            return
        seen_findings.add(key)
        findings.append(
            LegalAnalysisValidationFinding(
                code=code,
                severity=severity,
                path=path,
                message=message,
            )
        )

    for branch_index, branch in enumerate(analysis.analyses):
        branch_path = f"analyses[{branch_index}]"
        profile = LegalAnalysisProfile(branch.profile)

        if branch.scope is AnalysisCoverageScope.ISSUE_LIMITED:
            add(
                "DOMAIN_ANALYSIS_SCOPE_LIMITED",
                AnalysisValidationSeverity.QUALIFICATION,
                f"{branch_path}.scope",
                f"The {profile.value} branch covers selected issues only.",
            )

        if isinstance(branch, CivilSubstantiveAnalysis):
            claim_count += len(branch.claims)
            element_count += len(branch.elements)
            defense_count += len(branch.defenses)

            for index, claim in enumerate(branch.claims):
                path = f"{branch_path}.claims[{index}].legal_basis_source_ids"
                source_groups.append((path, claim.legal_basis_source_ids))
                normative_groups.append((path, claim.legal_basis_source_ids))
                if not claim.legal_basis_source_ids:
                    add(
                        "CIVIL_CLAIM_LEGAL_BASIS_REQUIRED",
                        AnalysisValidationSeverity.BLOCKER,
                        path,
                        "Every civil claim requires a server-owned legal basis.",
                    )

            burdens_by_element = {
                item.element_id: item for item in branch.burden_of_proof
            }
            for index, element in enumerate(branch.elements):
                item_path = f"{branch_path}.elements[{index}]"
                source_path = f"{item_path}.normative_source_ids"
                evidence_path = f"{item_path}.evidence_ids"
                fact_path = f"{item_path}.fact_ids"
                source_groups.append((source_path, element.normative_source_ids))
                normative_groups.append((source_path, element.normative_source_ids))
                evidence_groups.append((evidence_path, element.evidence_ids))
                fact_groups.append((fact_path, element.fact_ids))

                if element.element_id not in burdens_by_element:
                    add(
                        "ELEMENT_BURDEN_RECORD_REQUIRED",
                        AnalysisValidationSeverity.BLOCKER,
                        item_path,
                        "Every civil element requires one burden-of-proof record.",
                    )
                _validate_determinate_item(
                    status=element.status,
                    source_ids=element.normative_source_ids,
                    fact_ids=element.fact_ids,
                    evidence_ids=element.evidence_ids,
                    item_path=item_path,
                    source_path=source_path,
                    missing_source_code="DETERMINATE_ELEMENT_NORMATIVE_SOURCE_REQUIRED",
                    unresolved_code="CIVIL_ELEMENT_UNRESOLVED",
                    add=add,
                    support_targets=support_targets,
                )

            for index, burden in enumerate(branch.burden_of_proof):
                item_path = f"{branch_path}.burden_of_proof[{index}]"
                path = f"{item_path}.normative_source_ids"
                source_groups.append((path, burden.normative_source_ids))
                normative_groups.append((path, burden.normative_source_ids))
                if not burden.normative_source_ids:
                    add(
                        "BURDEN_NORMATIVE_SOURCE_REQUIRED",
                        AnalysisValidationSeverity.BLOCKER,
                        path,
                        "A burden allocation requires a server-owned normative source.",
                    )
                if (
                    burden.burden_bearer
                    in {BurdenBearer.DISPUTED, BurdenBearer.UNKNOWN}
                    or burden.burden_shift
                    in {
                        BurdenShiftStatus.DISPUTED,
                        BurdenShiftStatus.UNKNOWN,
                        BurdenShiftStatus.MAY_SHIFT,
                    }
                    or burden.standard_of_proof is StandardOfProof.UNKNOWN
                ):
                    add(
                        "BURDEN_ALLOCATION_UNRESOLVED",
                        AnalysisValidationSeverity.QUALIFICATION,
                        item_path,
                        "The burden allocation or proof standard remains unresolved.",
                    )

            for index, defense in enumerate(branch.defenses):
                item_path = f"{branch_path}.defenses[{index}]"
                source_path = f"{item_path}.normative_source_ids"
                evidence_path = f"{item_path}.evidence_ids"
                fact_path = f"{item_path}.fact_ids"
                source_groups.append((source_path, defense.normative_source_ids))
                normative_groups.append((source_path, defense.normative_source_ids))
                evidence_groups.append((evidence_path, defense.evidence_ids))
                fact_groups.append((fact_path, defense.fact_ids))
                _validate_determinate_item(
                    status=defense.status,
                    source_ids=defense.normative_source_ids,
                    fact_ids=defense.fact_ids,
                    evidence_ids=defense.evidence_ids,
                    item_path=item_path,
                    source_path=source_path,
                    missing_source_code="DETERMINATE_DEFENSE_NORMATIVE_SOURCE_REQUIRED",
                    unresolved_code="CIVIL_DEFENSE_UNRESOLVED",
                    add=add,
                    support_targets=support_targets,
                )
            _validate_domain_branch_extras(
                profile=profile,
                branch_path=branch_path,
                issues=[],
                burden_of_proof=[],
                defenses=[],
                procedural_posture=getattr(branch, "procedural_posture", None),
                refusal_constraints=getattr(branch, "refusal_constraints", []),
                source_groups=source_groups,
                normative_groups=normative_groups,
                evidence_groups=evidence_groups,
                fact_groups=fact_groups,
                support_targets=support_targets,
                add=add,
                validate_issue_extras=False,
            )
            continue

        issue_count += len(branch.issues)
        if branch.scope is AnalysisCoverageScope.COMPLETE:
            included = {issue.issue_type.value for issue in branch.issues}
            for missing in sorted(_CORE_DIMENSIONS[profile] - included):
                add(
                    "DOMAIN_PROFILE_CORE_DIMENSION_MISSING",
                    AnalysisValidationSeverity.BLOCKER,
                    f"{branch_path}.issues",
                    f"Complete {profile.value} analysis is missing: {missing}",
                )

        for index, issue in enumerate(branch.issues):
            item_path = f"{branch_path}.issues[{index}]"
            source_path = f"{item_path}.normative_source_ids"
            evidence_path = f"{item_path}.evidence_ids"
            fact_path = f"{item_path}.fact_ids"
            source_groups.append((source_path, issue.normative_source_ids))
            normative_groups.append((source_path, issue.normative_source_ids))
            evidence_groups.append((evidence_path, issue.evidence_ids))
            fact_groups.append((fact_path, issue.fact_ids))
            _validate_determinate_item(
                status=issue.status,
                source_ids=issue.normative_source_ids,
                fact_ids=issue.fact_ids,
                evidence_ids=issue.evidence_ids,
                item_path=item_path,
                source_path=source_path,
                missing_source_code="DOMAIN_ISSUE_NORMATIVE_SOURCE_REQUIRED",
                unresolved_code="DOMAIN_ISSUE_UNRESOLVED",
                add=add,
                support_targets=support_targets,
                source_required_for_all=True,
            )
        _validate_domain_branch_extras(
            profile=profile,
            branch_path=branch_path,
            issues=branch.issues,
            burden_of_proof=getattr(branch, "burden_of_proof", []),
            defenses=getattr(branch, "defenses", []),
            procedural_posture=getattr(branch, "procedural_posture", None),
            refusal_constraints=getattr(branch, "refusal_constraints", []),
            source_groups=source_groups,
            normative_groups=normative_groups,
            evidence_groups=evidence_groups,
            fact_groups=fact_groups,
            support_targets=support_targets,
            add=add,
        )

    for index, fact in enumerate(analysis.facts):
        fact_groups.append((f"facts[{index}].fact_id", [fact.fact_id]))
        evidence_groups.append((f"facts[{index}].evidence_ids", fact.evidence_ids))
        server_state = fact_states.get(fact.fact_id)
        if server_state is not None and server_state is not fact.status:
            add(
                "CLIENT_FACT_STATE_NOT_AUTHORITATIVE",
                AnalysisValidationSeverity.QUALIFICATION,
                f"facts[{index}].status",
                "The client fact status differs from the server-owned fact state.",
            )

    for index, assessment in enumerate(analysis.evidence_assessments):
        evidence_groups.append(
            (f"evidence_assessments[{index}].evidence_id", [assessment.evidence_id])
        )
        fact_groups.append(
            (
                f"evidence_assessments[{index}].supports_fact_ids",
                assessment.supports_fact_ids,
            )
        )

    source_groups.extend(
        (
            ("counter_authority.source_ids", analysis.counter_authority.source_ids),
            ("procedural_posture.source_ids", analysis.procedural_posture.source_ids),
        )
    )
    fact_groups.append(("procedural_posture.fact_ids", analysis.procedural_posture.fact_ids))

    for path, source_ids in source_groups:
        for source_id in source_ids:
            source = sources.get(source_id)
            if source is None:
                add(
                    "ANALYSIS_SOURCE_NOT_SERVER_OWNED",
                    AnalysisValidationSeverity.BLOCKER,
                    path,
                    f"Source reference is not owned by this research run: {source_id}",
                )
                continue
            if source.expires_at <= timestamp:
                add(
                    "ANALYSIS_SOURCE_STALE",
                    AnalysisValidationSeverity.BLOCKER,
                    path,
                    f"Source reference is stale: {source_id}",
                )
            if source.trust_status is not TrustStatus.EVIDENCE_ELIGIBLE:
                add(
                    "ANALYSIS_SOURCE_NOT_EVIDENCE_ELIGIBLE",
                    AnalysisValidationSeverity.BLOCKER,
                    path,
                    f"Source reference is not evidence eligible: {source_id}",
                )

    eligible_evidence_ids: set[str] = set()
    for path, evidence_ids in evidence_groups:
        for evidence_id in evidence_ids:
            evidence_span = evidence.get(evidence_id)
            if evidence_span is None:
                add(
                    "ANALYSIS_EVIDENCE_NOT_SERVER_OWNED",
                    AnalysisValidationSeverity.BLOCKER,
                    path,
                    f"Evidence reference is not owned by this research run: {evidence_id}",
                )
                continue
            source = sources.get(evidence_span.source_id)
            if (
                source is None
                or source.expires_at <= timestamp
                or source.trust_status is not TrustStatus.EVIDENCE_ELIGIBLE
                or not evidence_span.eligible_for_claim_support
            ):
                add(
                    "ANALYSIS_EVIDENCE_NOT_ELIGIBLE",
                    AnalysisValidationSeverity.BLOCKER,
                    path,
                    f"Evidence reference is not eligible for analysis support: {evidence_id}",
                )
                continue
            eligible_evidence_ids.add(evidence_id)

    for path, fact_ids in fact_groups:
        for fact_id in fact_ids:
            if fact_id not in fact_states:
                add(
                    "ANALYSIS_FACT_NOT_SERVER_OWNED",
                    AnalysisValidationSeverity.BLOCKER,
                    path,
                    f"Fact reference is not owned by the server context: {fact_id}",
                )

    for path, fact_ids, evidence_ids in support_targets:
        has_supported_fact = any(
            fact_states.get(fact_id) in _SUPPORTIVE_FACT_STATES for fact_id in fact_ids
        )
        has_eligible_evidence = any(
            evidence_id in eligible_evidence_ids for evidence_id in evidence_ids
        )
        if not (has_supported_fact or has_eligible_evidence):
            add(
                "DETERMINATE_ANALYSIS_SUPPORT_NOT_ESTABLISHED",
                AnalysisValidationSeverity.BLOCKER,
                path,
                "Referenced facts or evidence do not establish server-owned support.",
            )

    for path, source_ids in normative_groups:
        if not source_ids:
            continue
        binding_source_found = False
        for source_id in source_ids:
            context = contexts.get(source_id)
            if context is None:
                add(
                    "LEGAL_CONTEXT_NOT_VERIFIED",
                    AnalysisValidationSeverity.BLOCKER,
                    path,
                    f"No server-owned legal context exists for source: {source_id}",
                )
                continue
            if not context.coverage_complete:
                add(
                    "LEGAL_CONTEXT_INCOMPLETE",
                    AnalysisValidationSeverity.BLOCKER,
                    path,
                    f"Legal-context coverage is incomplete for source: {source_id}",
                )
            if context.temporal.status is not TemporalApplicabilityStatus.APPLICABLE:
                add(
                    "LEGAL_TIME_NOT_APPLICABLE",
                    AnalysisValidationSeverity.BLOCKER,
                    path,
                    f"Source is not verified as applicable at the requested time: {source_id}",
                )
            if context.validity.status is not LegalValidityStatus.VALID:
                add(
                    "LEGAL_VALIDITY_NOT_CONFIRMED",
                    AnalysisValidationSeverity.BLOCKER,
                    path,
                    f"Source legal validity is not confirmed: {source_id}",
                )
            if context.authority.status is AuthorityStatus.BINDING:
                binding_source_found = True
            elif context.authority.status in {
                AuthorityStatus.SUPERSEDED,
                AuthorityStatus.UNKNOWN,
            }:
                add(
                    "NORMATIVE_AUTHORITY_UNUSABLE",
                    AnalysisValidationSeverity.BLOCKER,
                    path,
                    f"Normative authority is superseded or unknown: {source_id}",
                )
        if not binding_source_found:
            add(
                "NORMATIVE_AUTHORITY_NOT_BINDING",
                AnalysisValidationSeverity.BLOCKER,
                path,
                "At least one binding server-assessed authority is required.",
            )

    counter_status = analysis.counter_authority.status
    if counter_status is CounterAuthorityStatus.NOT_FOUND_IN_SCOPE:
        add(
            "COUNTER_AUTHORITY_ABSENCE_NOT_ESTABLISHED",
            AnalysisValidationSeverity.QUALIFICATION,
            "counter_authority",
            "A bounded search with no result does not prove that no opposing view exists.",
        )
    elif counter_status in {
        CounterAuthorityStatus.NOT_SEARCHED,
        CounterAuthorityStatus.SEARCH_INCOMPLETE,
        CounterAuthorityStatus.PROVIDER_ERROR,
    }:
        add(
            "COUNTER_AUTHORITY_COVERAGE_INCOMPLETE",
            AnalysisValidationSeverity.QUALIFICATION,
            "counter_authority",
            "Counter-authority coverage is incomplete and must be disclosed.",
        )

    if analysis.procedural_posture.stage is ProceduralStage.UNKNOWN:
        add(
            "PROCEDURAL_POSTURE_UNRESOLVED",
            AnalysisValidationSeverity.QUALIFICATION,
            "procedural_posture.stage",
            "Procedural posture remains unresolved.",
        )

    blockers = sorted(
        {
            item.code
            for item in findings
            if item.severity is AnalysisValidationSeverity.BLOCKER
        }
    )
    qualifications = sorted(
        {
            item.code
            for item in findings
            if item.severity is AnalysisValidationSeverity.QUALIFICATION
        }
    )
    if blockers:
        decision = LegalAnalysisDecision.BLOCKED
    elif qualifications:
        decision = LegalAnalysisDecision.QUALIFIED
    else:
        decision = LegalAnalysisDecision.VALIDATED

    return LegalAnalysisValidationResult(
        analysis_id=analysis.analysis_id,
        profiles=profiles,
        decision=decision,
        eligible_for_answer_validation=decision
        in {LegalAnalysisDecision.VALIDATED, LegalAnalysisDecision.QUALIFIED},
        findings=findings,
        blockers=blockers,
        qualifications=qualifications,
        coverage={
            "profiles": [profile.value for profile in profiles],
            "branches": len(analysis.analyses),
            "issues": issue_count,
            "claims": claim_count,
            "elements": element_count,
            "defenses": defense_count,
            "server_sources": len(sources),
            "server_evidence": len(evidence),
            "server_facts": len(fact_states),
            "legal_context_records": len(contexts),
        },
    )


def _validate_domain_branch_extras(
    *,
    profile: LegalAnalysisProfile,
    branch_path: str,
    issues: Sequence[Any],
    burden_of_proof: Sequence[DomainBurdenOfProof],
    defenses: Sequence[DomainDefense],
    procedural_posture: Any,
    refusal_constraints: Sequence[Any],
    source_groups: list[tuple[str, list[str]]],
    normative_groups: list[tuple[str, list[str]]],
    evidence_groups: list[tuple[str, list[str]]],
    fact_groups: list[tuple[str, list[str]]],
    support_targets: list[tuple[str, list[str], list[str]]],
    add: Callable[[str, AnalysisValidationSeverity, str, str], None],
    validate_issue_extras: bool = True,
) -> None:
    """Validate additive burden/defense/procedure fields without trusting them.

    The fields are proposals.  Their references enter the same server-owned
    source/evidence gates as the legacy issue fields; the refusal declarations
    are never used to waive a blocker.
    """

    if validate_issue_extras and not burden_of_proof:
        add(
            "DOMAIN_BURDEN_NOT_DECLARED",
            AnalysisValidationSeverity.INFO,
            f"{branch_path}.burden_of_proof",
            "This branch did not declare issue-level burden allocation.",
        )
    for index, burden in enumerate(burden_of_proof if validate_issue_extras else []):
        item_path = f"{branch_path}.burden_of_proof[{index}]"
        source_path = f"{item_path}.normative_source_ids"
        source_groups.append((source_path, burden.normative_source_ids))
        normative_groups.append((source_path, burden.normative_source_ids))
        if not burden.normative_source_ids:
            add(
                "DOMAIN_BURDEN_NORMATIVE_SOURCE_REQUIRED",
                AnalysisValidationSeverity.BLOCKER,
                source_path,
                "A domain burden allocation requires a server-owned normative source.",
            )
        unresolved = (
            burden.burden_bearer in {BurdenBearer.UNKNOWN, BurdenBearer.DISPUTED}
            or burden.burden_shift
            in {
                BurdenShiftStatus.UNKNOWN,
                BurdenShiftStatus.DISPUTED,
                BurdenShiftStatus.MAY_SHIFT,
            }
            or burden.standard_of_proof is StandardOfProof.UNKNOWN
        )
        if unresolved:
            add(
                "DOMAIN_BURDEN_ALLOCATION_UNRESOLVED",
                AnalysisValidationSeverity.QUALIFICATION,
                item_path,
                "The domain burden allocation remains unresolved.",
            )
            _require_declared_refusal_constraint(
                refusal_constraints,
                code=f"{profile.value.upper()}_BURDEN_UNRESOLVED",
                path=item_path,
                add=add,
            )

    if validate_issue_extras and not defenses:
        add(
            "DOMAIN_DEFENSES_NOT_DECLARED",
            AnalysisValidationSeverity.INFO,
            f"{branch_path}.defenses",
            "This branch did not declare domain defenses or exceptions.",
        )
    for index, defense in enumerate(defenses if validate_issue_extras else []):
        item_path = f"{branch_path}.defenses[{index}]"
        source_path = f"{item_path}.normative_source_ids"
        evidence_path = f"{item_path}.evidence_ids"
        fact_path = f"{item_path}.fact_ids"
        source_groups.append((source_path, defense.normative_source_ids))
        normative_groups.append((source_path, defense.normative_source_ids))
        evidence_groups.append((evidence_path, defense.evidence_ids))
        fact_groups.append((fact_path, defense.fact_ids))
        _validate_determinate_item(
            status=defense.status,
            source_ids=defense.normative_source_ids,
            fact_ids=defense.fact_ids,
            evidence_ids=defense.evidence_ids,
            item_path=item_path,
            source_path=source_path,
            missing_source_code="DOMAIN_DEFENSE_NORMATIVE_SOURCE_REQUIRED",
            unresolved_code="DOMAIN_DEFENSE_UNRESOLVED",
            add=add,
            support_targets=support_targets,
            source_required_for_all=True,
        )

    if procedural_posture is None:
        add(
            "DOMAIN_PROCEDURAL_POSTURE_NOT_DECLARED",
            AnalysisValidationSeverity.INFO,
            f"{branch_path}.procedural_posture",
            "This branch did not declare a branch-specific procedural posture.",
        )
    else:
        source_path = f"{branch_path}.procedural_posture.source_ids"
        fact_path = f"{branch_path}.procedural_posture.fact_ids"
        source_groups.append((source_path, procedural_posture.source_ids))
        fact_groups.append((fact_path, procedural_posture.fact_ids))
        if procedural_posture.stage is ProceduralStage.UNKNOWN:
            add(
                "DOMAIN_PROCEDURAL_POSTURE_UNRESOLVED",
                AnalysisValidationSeverity.QUALIFICATION,
                f"{branch_path}.procedural_posture.stage",
                "The branch-specific procedural posture remains unresolved.",
            )
            _require_declared_refusal_constraint(
                refusal_constraints,
                code=f"{profile.value.upper()}_PROCEDURE_UNRESOLVED",
                path=f"{branch_path}.procedural_posture",
                add=add,
            )

    for index, issue in enumerate(issues):
        if issue.status not in {
            ElementAssessmentStatus.UNCERTAIN,
            ElementAssessmentStatus.DISPUTED,
        }:
            continue
        issue_type = getattr(issue.issue_type, "value", str(issue.issue_type))
        code = _REFUSAL_CODES.get(profile, {}).get(issue_type)
        if code is not None:
            _require_declared_refusal_constraint(
                refusal_constraints,
                code=code,
                path=f"{branch_path}.issues[{index}]",
                add=add,
            )


def _require_declared_refusal_constraint(
    constraints: Sequence[Any],
    *,
    code: str,
    path: str,
    add: Callable[[str, AnalysisValidationSeverity, str, str], None],
) -> None:
    if any(item.code == code for item in constraints):
        return
    add(
        "DOMAIN_REFUSAL_CONSTRAINT_NOT_DECLARED",
        AnalysisValidationSeverity.QUALIFICATION,
        path,
        f"Unresolved domain condition should declare refusal constraint {code}.",
    )


def _validate_determinate_item(
    *,
    status: ElementAssessmentStatus,
    source_ids: list[str],
    fact_ids: list[str],
    evidence_ids: list[str],
    item_path: str,
    source_path: str,
    missing_source_code: str,
    unresolved_code: str,
    add: Callable[[str, AnalysisValidationSeverity, str, str], None],
    support_targets: list[tuple[str, list[str], list[str]]],
    source_required_for_all: bool = False,
) -> None:
    if source_required_for_all and not source_ids:
            add(
                missing_source_code,
                AnalysisValidationSeverity.BLOCKER,
                source_path,
                "Every determinate analysis item requires a server-owned normative source.",
            )
    if status in {ElementAssessmentStatus.MET, ElementAssessmentStatus.NOT_MET}:
        if not source_ids and not source_required_for_all:
            add(
                missing_source_code,
                AnalysisValidationSeverity.BLOCKER,
                source_path,
                "A determinate assessment requires a server-owned normative source.",
            )
        if not (fact_ids or evidence_ids):
            add(
                "DETERMINATE_ANALYSIS_FACT_OR_EVIDENCE_REQUIRED",
                AnalysisValidationSeverity.BLOCKER,
                item_path,
                "A determinate assessment requires a server-owned fact or evidence reference.",
            )
        else:
            support_targets.append((item_path, fact_ids, evidence_ids))
    elif status in {
        ElementAssessmentStatus.UNCERTAIN,
        ElementAssessmentStatus.DISPUTED,
    }:
        add(
            unresolved_code,
            AnalysisValidationSeverity.QUALIFICATION,
            f"{item_path}.status",
            "The proposed assessment remains unresolved.",
        )
