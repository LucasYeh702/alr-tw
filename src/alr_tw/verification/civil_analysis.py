"""Fail-closed structural validation for public civil-law analysis proposals."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from alr_tw.contracts.civil_analysis import (
    AnalysisValidationSeverity,
    BurdenBearer,
    BurdenShiftStatus,
    CivilAnalysisDecision,
    CivilAnalysisValidationFinding,
    CivilAnalysisValidationResult,
    CivilLawAnalysis,
    CounterAuthorityStatus,
    ElementAssessmentStatus,
    FindingState,
    ProceduralStage,
    StandardOfProof,
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


def validate_civil_analysis(
    analysis: CivilLawAnalysis,
    *,
    server_sources: Sequence[SourceRecord],
    server_evidence: Sequence[EvidenceSpan],
    legal_context: LegalContextResult,
    server_fact_states: Mapping[str, FindingState] | None = None,
    validated_at: datetime | None = None,
) -> CivilAnalysisValidationResult:
    """Validate references and legal-context gates without claiming legal reasoning."""

    timestamp = validated_at or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("validated_at must be timezone-aware")

    sources = {source.source_id: source for source in server_sources}
    evidence = {item.evidence_id: item for item in server_evidence}
    fact_states = dict(server_fact_states or {})
    contexts = {record.source_id: record for record in legal_context.records}
    findings: list[CivilAnalysisValidationFinding] = []
    seen_findings: set[tuple[str, str]] = set()

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
            CivilAnalysisValidationFinding(
                code=code,
                severity=severity,
                path=path,
                message=message,
            )
        )

    source_groups: list[tuple[str, list[str]]] = []
    normative_groups: list[tuple[str, list[str]]] = []
    evidence_groups: list[tuple[str, list[str]]] = []
    fact_groups: list[tuple[str, list[str]]] = []

    for index, claim in enumerate(analysis.claims):
        path = f"claims[{index}].legal_basis_source_ids"
        source_groups.append((path, claim.legal_basis_source_ids))
        normative_groups.append((path, claim.legal_basis_source_ids))
        if not claim.legal_basis_source_ids:
            add(
                "CLAIM_BASIS_SOURCE_REQUIRED",
                AnalysisValidationSeverity.BLOCKER,
                path,
                "Every civil claim requires a server-owned legal-basis source.",
            )

    burdens_by_element = {item.element_id: item for item in analysis.burden_of_proof}
    for index, element in enumerate(analysis.elements):
        source_path = f"elements[{index}].normative_source_ids"
        evidence_path = f"elements[{index}].evidence_ids"
        fact_path = f"elements[{index}].fact_ids"
        source_groups.append((source_path, element.normative_source_ids))
        normative_groups.append((source_path, element.normative_source_ids))
        evidence_groups.append((evidence_path, element.evidence_ids))
        fact_groups.append((fact_path, element.fact_ids))

        if element.element_id not in burdens_by_element:
            add(
                "ELEMENT_BURDEN_RECORD_REQUIRED",
                AnalysisValidationSeverity.BLOCKER,
                f"elements[{index}]",
                "Every element requires one explicit burden-of-proof record.",
            )
        if element.status is ElementAssessmentStatus.MET:
            if not element.normative_source_ids:
                add(
                    "MET_ELEMENT_NORMATIVE_SOURCE_REQUIRED",
                    AnalysisValidationSeverity.BLOCKER,
                    source_path,
                    "A met element requires at least one normative source.",
                )
            if not element.fact_ids and not element.evidence_ids:
                add(
                    "MET_ELEMENT_FACT_OR_EVIDENCE_REQUIRED",
                    AnalysisValidationSeverity.BLOCKER,
                    f"elements[{index}]",
                    "A met element requires a server-owned fact or evidence reference.",
                )

    for index, burden in enumerate(analysis.burden_of_proof):
        path = f"burden_of_proof[{index}].normative_source_ids"
        source_groups.append((path, burden.normative_source_ids))
        normative_groups.append((path, burden.normative_source_ids))
        if not burden.normative_source_ids:
            add(
                "BURDEN_NORMATIVE_SOURCE_REQUIRED",
                AnalysisValidationSeverity.BLOCKER,
                path,
                "A burden allocation requires at least one normative source.",
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
                f"burden_of_proof[{index}]",
                "The proposed burden allocation or proof standard remains unresolved.",
            )

    for index, defense in enumerate(analysis.defenses):
        source_path = f"defenses[{index}].normative_source_ids"
        evidence_path = f"defenses[{index}].evidence_ids"
        fact_path = f"defenses[{index}].fact_ids"
        source_groups.append((source_path, defense.normative_source_ids))
        normative_groups.append((source_path, defense.normative_source_ids))
        evidence_groups.append((evidence_path, defense.evidence_ids))
        fact_groups.append((fact_path, defense.fact_ids))
        if defense.status is ElementAssessmentStatus.MET:
            if not defense.normative_source_ids:
                add(
                    "MET_DEFENSE_NORMATIVE_SOURCE_REQUIRED",
                    AnalysisValidationSeverity.BLOCKER,
                    source_path,
                    "A met defense requires at least one normative source.",
                )
            if not defense.fact_ids and not defense.evidence_ids:
                add(
                    "MET_DEFENSE_FACT_OR_EVIDENCE_REQUIRED",
                    AnalysisValidationSeverity.BLOCKER,
                    f"defenses[{index}]",
                    "A met defense requires a server-owned fact or evidence reference.",
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

    source_groups.append(
        ("counter_authority.source_ids", analysis.counter_authority.source_ids)
    )
    source_groups.append(
        ("procedural_posture.source_ids", analysis.procedural_posture.source_ids)
    )
    fact_groups.append(
        ("procedural_posture.fact_ids", analysis.procedural_posture.fact_ids)
    )

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

    for index, element in enumerate(analysis.elements):
        if element.status is not ElementAssessmentStatus.MET:
            continue
        has_supported_fact = any(
            fact_states.get(fact_id) in _SUPPORTIVE_FACT_STATES
            for fact_id in element.fact_ids
        )
        has_eligible_evidence = any(
            evidence_id in eligible_evidence_ids for evidence_id in element.evidence_ids
        )
        if (element.fact_ids or element.evidence_ids) and not (
            has_supported_fact or has_eligible_evidence
        ):
            add(
                "MET_ELEMENT_SUPPORT_NOT_ESTABLISHED",
                AnalysisValidationSeverity.BLOCKER,
                f"elements[{index}]",
                "Referenced facts or evidence do not establish server-owned support.",
            )

    for index, defense in enumerate(analysis.defenses):
        if defense.status is not ElementAssessmentStatus.MET:
            continue
        has_supported_fact = any(
            fact_states.get(fact_id) in _SUPPORTIVE_FACT_STATES
            for fact_id in defense.fact_ids
        )
        has_eligible_evidence = any(
            evidence_id in eligible_evidence_ids for evidence_id in defense.evidence_ids
        )
        if (defense.fact_ids or defense.evidence_ids) and not (
            has_supported_fact or has_eligible_evidence
        ):
            add(
                "MET_DEFENSE_SUPPORT_NOT_ESTABLISHED",
                AnalysisValidationSeverity.BLOCKER,
                f"defenses[{index}]",
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
            "No result in a bounded search scope does not establish that no opposing view exists.",
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
        decision = CivilAnalysisDecision.BLOCKED
    elif qualifications:
        decision = CivilAnalysisDecision.QUALIFIED
    else:
        decision = CivilAnalysisDecision.VALIDATED

    return CivilAnalysisValidationResult(
        analysis_id=analysis.analysis_id,
        decision=decision,
        eligible_for_answer_validation=decision
        in {CivilAnalysisDecision.VALIDATED, CivilAnalysisDecision.QUALIFIED},
        findings=findings,
        blockers=blockers,
        qualifications=qualifications,
        coverage={
            "claims": len(analysis.claims),
            "elements": len(analysis.elements),
            "burden_records": len(analysis.burden_of_proof),
            "defenses": len(analysis.defenses),
            "server_sources": len(sources),
            "server_evidence": len(evidence),
            "server_facts": len(fact_states),
            "legal_context_records": len(contexts),
        },
    )
