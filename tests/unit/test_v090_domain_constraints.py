from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from alr_tw.contracts.civil_analysis import (
    BurdenBearer,
    BurdenShiftStatus,
    BurdenType,
    CounterAuthorityStatus,
    ElementAssessmentStatus,
    LegalEffectType,
    PresumptionStatus,
    ProceduralPosture,
    ProceduralStage,
    RebuttalStatus,
    StandardOfProof,
)
from alr_tw.contracts.legal_analysis import (
    AnalysisCoverageScope,
    CounterAuthorityAssessment,
    CriminalSubstantiveAnalysis,
    CriminalSubstantiveDimension,
    CriminalSubstantiveIssue,
    CriminalProcedureAnalysis,
    CriminalProcedureIssue,
    CriminalProcedureIssueType,
    DomainBurdenOfProof,
    DomainDefense,
    DomainRefusalConstraint,
    LegalAnalysisEnvelope,
)
from alr_tw.contracts.sources import EvidenceSpan, MaterialType, SourceRecord, SourceTier, TrustStatus
from alr_tw.providers.synthetic import SyntheticLegalContextProvider
from alr_tw.verification.legal_analysis import validate_legal_analysis


NOW = datetime(2026, 8, 14, 10, 0, tzinfo=UTC)


def _source_and_evidence() -> tuple[SourceRecord, EvidenceSpan]:
    text = "合成刑法規範與程序事實。"
    digest = EvidenceSpan.hash_text(text)
    source = SourceRecord(
        source_id="source-domain",
        source_key="law:domain:v1",
        source_version_id="law:domain:v1",
        material_type=MaterialType.LAW,
        provider_id="synthetic-law",
        source_tier=SourceTier.OFFICIAL,
        trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
        official_identifier="DOMAIN-LAW",
        official_url="https://example.test/domain-law",
        citation="合成刑法第1條",
        fetched_at=NOW,
        verified_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        content_hash=digest,
        normalized_content_hash=digest,
        normalized_text=text,
        metadata={"synthetic_fixture": True},
    )
    evidence = EvidenceSpan.from_exact_text(
        evidence_id="evidence-domain",
        source_id=source.source_id,
        section_id="section-domain",
        section_type="law_text",
        exact_text=text,
        eligible_for_claim_support=True,
    )
    return source, evidence


def _branch(*, issue_status: ElementAssessmentStatus = ElementAssessmentStatus.MET):
    issues = [
        CriminalSubstantiveIssue(
            issue_id=f"issue-{dimension.value}",
            issue_type=dimension,
            label=dimension.value,
            proposition=f"是否符合 {dimension.value}？",
            status=issue_status,
            normative_source_ids=["source-domain"],
            evidence_ids=["evidence-domain"]
            if issue_status in {ElementAssessmentStatus.MET, ElementAssessmentStatus.NOT_MET}
            else [],
        )
        for dimension in (
            CriminalSubstantiveDimension.OFFENSE_ELEMENTS,
            CriminalSubstantiveDimension.UNLAWFULNESS,
            CriminalSubstantiveDimension.CULPABILITY,
        )
    ]
    return CriminalSubstantiveAnalysis(
        scope=AnalysisCoverageScope.COMPLETE,
        issues=issues,
        burden_of_proof=[
            DomainBurdenOfProof(
                issue_id=issues[0].issue_id,
                burden_type=BurdenType.PERSUASION,
                burden_bearer=BurdenBearer.PROSECUTION,
                presumption=PresumptionStatus.NONE,
                burden_shift=BurdenShiftStatus.NONE,
                standard_of_proof=StandardOfProof.HEIGHTENED,
                rebuttal_status=RebuttalStatus.NOT_APPLICABLE,
                normative_source_ids=["source-domain"],
            )
        ],
        defenses=[
            DomainDefense(
                defense_id="defense-unlawfulness",
                issue_id=issues[1].issue_id,
                label="阻卻違法事由",
                legal_effect=LegalEffectType.DEFENSE,
                status=ElementAssessmentStatus.UNCERTAIN,
                normative_source_ids=["source-domain"],
                evidence_ids=["evidence-domain"],
            )
        ],
        procedural_posture=ProceduralPosture(
            stage=ProceduralStage.FIRST_INSTANCE,
            description="合成刑事第一審",
            source_ids=["source-domain"],
        ),
        refusal_constraints=[
            DomainRefusalConstraint(
                code="CRIMINAL_OFFENSE_ELEMENTS_UNRESOLVED",
                trigger="unresolved_issue",
                message="構成要件未釐清時拒答",
            )
        ],
    )


def _envelope(branch: CriminalSubstantiveAnalysis) -> LegalAnalysisEnvelope:
    return LegalAnalysisEnvelope(
        analysis_id="analysis-domain",
        analyses=[branch],
        counter_authority=CounterAuthorityAssessment(status=CounterAuthorityStatus.NOT_SEARCHED),
        procedural_posture=ProceduralPosture(
            stage=ProceduralStage.FIRST_INSTANCE,
            description="合成程序",
            source_ids=["source-domain"],
        ),
    )


def test_non_civil_branch_exposes_burden_defense_posture_and_refusal_contracts() -> None:
    branch = _branch()
    envelope = _envelope(branch)
    assert branch.burden_of_proof[0].issue_id == "issue-offense_elements"
    assert branch.defenses[0].legal_effect.value == "defense"
    assert branch.procedural_posture is not None
    assert envelope.analyses[0].refusal_constraints[0].code == (
        "CRIMINAL_OFFENSE_ELEMENTS_UNRESOLVED"
    )


def test_domain_defense_cannot_be_a_right_constituting_effect() -> None:
    with pytest.raises(ValidationError, match="cannot constitute"):
        DomainDefense(
            defense_id="defense-invalid",
            issue_id="issue-1",
            label="錯誤抗辯",
            legal_effect=LegalEffectType.RIGHT_CONSTITUTING,
            status=ElementAssessmentStatus.UNCERTAIN,
        )


def test_defense_ids_are_unique_across_analysis_branches() -> None:
    substantive = _branch()
    procedure = CriminalProcedureAnalysis(
        scope=AnalysisCoverageScope.ISSUE_LIMITED,
        issues=[
            CriminalProcedureIssue(
                issue_id="procedure-issue",
                issue_type=CriminalProcedureIssueType.PROCEEDING_STAGE,
                label="程序階段",
                proposition="程序階段為何？",
                status=ElementAssessmentStatus.UNCERTAIN,
            )
        ],
        defenses=[substantive.defenses[0].model_copy(update={"issue_id": "procedure-issue"})],
    )
    with pytest.raises(ValidationError, match="defense_id"):
        LegalAnalysisEnvelope(
            analysis_id="analysis-duplicate-defense",
            analyses=[substantive, procedure],
            counter_authority=CounterAuthorityAssessment(
                status=CounterAuthorityStatus.NOT_SEARCHED,
            ),
            procedural_posture=ProceduralPosture(
                stage=ProceduralStage.FIRST_INSTANCE,
                description="合成程序",
            ),
        )


def test_unresolved_issue_without_declared_refusal_constraint_is_qualified() -> None:
    source, evidence = _source_and_evidence()
    branch = _branch(issue_status=ElementAssessmentStatus.UNCERTAIN).model_copy(
        update={"refusal_constraints": []}
    )
    context = SyntheticLegalContextProvider({source.source_id}).assess(
        [source],
        as_of_date=NOW.date(),
        assessed_at=NOW,
    )
    result = validate_legal_analysis(
        _envelope(branch),
        server_sources=[source],
        server_evidence=[evidence],
        legal_context=context,
        validated_at=NOW,
    )
    assert result.decision.value == "qualified"
    assert "DOMAIN_REFUSAL_CONSTRAINT_NOT_DECLARED" in result.qualifications


def test_disputed_issue_also_requires_refusal_constraint_disclosure() -> None:
    source, evidence = _source_and_evidence()
    branch = _branch(issue_status=ElementAssessmentStatus.DISPUTED).model_copy(
        update={"refusal_constraints": []}
    )
    context = SyntheticLegalContextProvider({source.source_id}).assess(
        [source],
        as_of_date=NOW.date(),
        assessed_at=NOW,
    )
    result = validate_legal_analysis(
        _envelope(branch),
        server_sources=[source],
        server_evidence=[evidence],
        legal_context=context,
        validated_at=NOW,
    )
    assert result.decision.value == "qualified"
    assert "DOMAIN_REFUSAL_CONSTRAINT_NOT_DECLARED" in result.qualifications


def test_domain_burden_without_normative_source_is_blocked() -> None:
    source, evidence = _source_and_evidence()
    branch = _branch().model_copy(
        update={
            "burden_of_proof": [
                _branch().burden_of_proof[0].model_copy(update={"normative_source_ids": []})
            ]
        }
    )
    context = SyntheticLegalContextProvider({source.source_id}).assess(
        [source],
        as_of_date=NOW.date(),
        assessed_at=NOW,
    )
    result = validate_legal_analysis(
        _envelope(branch),
        server_sources=[source],
        server_evidence=[evidence],
        legal_context=context,
        validated_at=NOW,
    )
    assert result.decision.value == "blocked"
    assert "DOMAIN_BURDEN_NORMATIVE_SOURCE_REQUIRED" in result.blockers


def test_domain_defense_without_normative_source_is_blocked() -> None:
    source, evidence = _source_and_evidence()
    original = _branch()
    defense = original.defenses[0].model_copy(update={"normative_source_ids": []})
    branch = original.model_copy(update={"defenses": [defense]})
    context = SyntheticLegalContextProvider({source.source_id}).assess(
        [source],
        as_of_date=NOW.date(),
        assessed_at=NOW,
    )
    result = validate_legal_analysis(
        _envelope(branch),
        server_sources=[source],
        server_evidence=[evidence],
        legal_context=context,
        validated_at=NOW,
    )
    assert result.decision.value == "blocked"
    assert "DOMAIN_DEFENSE_NORMATIVE_SOURCE_REQUIRED" in result.blockers
