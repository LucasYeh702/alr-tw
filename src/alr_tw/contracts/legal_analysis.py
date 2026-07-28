"""Unified legal-analysis envelope proposed by an external reasoning client."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .civil_analysis import (
    AnalysisValidationSeverity,
    CivilClaim,
    CivilDefense,
    CivilElement,
    CounterAuthorityAssessment,
    ElementAssessmentStatus,
    ElementBurdenOfProof,
    EvidenceAssessment,
    FactAssessment,
    ProceduralPosture,
)

_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$"


class LegalAnalysisProfile(str, Enum):
    CIVIL_SUBSTANTIVE = "civil_substantive"
    CIVIL_PROCEDURE = "civil_procedure"
    CRIMINAL_SUBSTANTIVE = "criminal_substantive"
    CRIMINAL_PROCEDURE = "criminal_procedure"
    ADMINISTRATIVE = "administrative"
    CONSTITUTIONAL_REVIEW = "constitutional_review"


class AnalysisCoverageScope(str, Enum):
    COMPLETE = "complete"
    ISSUE_LIMITED = "issue_limited"


class CivilProcedureIssueType(str, Enum):
    JURISDICTION = "jurisdiction"
    PARTY_CAPACITY = "party_capacity"
    STANDING = "standing"
    CLAIM_SUBJECT = "claim_subject"
    PROCEDURAL_PREREQUISITE = "procedural_prerequisite"
    BURDEN_OF_PROOF = "burden_of_proof"
    RES_JUDICATA = "res_judicata"
    APPEAL = "appeal"
    PROVISIONAL_RELIEF = "provisional_relief"


class CriminalSubstantiveDimension(str, Enum):
    OFFENSE_ELEMENTS = "offense_elements"
    UNLAWFULNESS = "unlawfulness"
    CULPABILITY = "culpability"
    INTENT_OR_NEGLIGENCE = "intent_or_negligence"
    ATTEMPT = "attempt"
    PARTICIPATION = "participation"
    CONCURRENCE = "concurrence"
    SENTENCING = "sentencing"


class CriminalProcedureIssueType(str, Enum):
    PROCEEDING_STAGE = "proceeding_stage"
    JURISDICTION = "jurisdiction"
    PROSECUTION_PREREQUISITE = "prosecution_prerequisite"
    COERCIVE_MEASURE = "coercive_measure"
    EVIDENCE_ADMISSIBILITY = "evidence_admissibility"
    PROBATIVE_WEIGHT = "probative_weight"
    CONFESSION = "confession"
    HEARSAY = "hearsay"
    BURDEN_AND_STANDARD = "burden_and_standard"
    APPEAL_OR_REMEDY = "appeal_or_remedy"


class AdministrativeLegalityDimension(str, Enum):
    ACTION_CLASSIFICATION = "action_classification"
    AUTHORITY_BASIS = "authority_basis"
    COMPETENCE = "competence"
    PROCEDURE = "procedure"
    FORM = "form"
    SUBSTANTIVE_LEGALITY = "substantive_legality"
    DISCRETION_AND_PURPOSE = "discretion_and_purpose"
    PROPORTIONALITY = "proportionality"
    LEGITIMATE_EXPECTATION = "legitimate_expectation"


class AdministrativeRemedyIssueType(str, Enum):
    REMEDY_TYPE = "remedy_type"
    STANDING = "standing"
    PRIOR_PROCEEDING = "prior_proceeding"
    FILING_PERIOD = "filing_period"
    REMEDY_INTEREST = "remedy_interest"
    SUSPENSION = "suspension"
    SCOPE_OF_REVIEW = "scope_of_review"


class ConstitutionalReviewDimension(str, Enum):
    REVIEW_ADMISSIBILITY = "review_admissibility"
    PROTECTED_RIGHT = "protected_right"
    INTERFERENCE = "interference"
    LEGAL_RESERVATION = "legal_reservation"
    LEGITIMATE_AIM = "legitimate_aim"
    PROPORTIONALITY = "proportionality"
    EQUALITY = "equality"
    DUE_PROCESS = "due_process"
    JUDGMENT_EFFECT = "judgment_effect"


class _DomainIssueBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    issue_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    label: str = Field(min_length=1, max_length=200)
    proposition: str = Field(min_length=1, max_length=2000)
    status: ElementAssessmentStatus
    normative_source_ids: list[str] = Field(default_factory=list, max_length=32)
    fact_ids: list[str] = Field(default_factory=list, max_length=64)
    evidence_ids: list[str] = Field(default_factory=list, max_length=64)

    @field_validator("normative_source_ids", "fact_ids", "evidence_ids")
    @classmethod
    def require_unique_references(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("issue reference IDs must be unique within each field")
        return value


class CivilProcedureIssue(_DomainIssueBase):
    issue_type: CivilProcedureIssueType


class CriminalSubstantiveIssue(_DomainIssueBase):
    issue_type: CriminalSubstantiveDimension


class CriminalProcedureIssue(_DomainIssueBase):
    issue_type: CriminalProcedureIssueType


class AdministrativeLegalityIssue(_DomainIssueBase):
    track: Literal["legality"] = "legality"
    issue_type: AdministrativeLegalityDimension


class AdministrativeRemedyIssue(_DomainIssueBase):
    track: Literal["remedy"] = "remedy"
    issue_type: AdministrativeRemedyIssueType


AdministrativeIssue = Annotated[
    AdministrativeLegalityIssue | AdministrativeRemedyIssue,
    Field(discriminator="track"),
]


class ConstitutionalReviewIssue(_DomainIssueBase):
    issue_type: ConstitutionalReviewDimension


class _DomainAnalysisBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scope: AnalysisCoverageScope = AnalysisCoverageScope.ISSUE_LIMITED


class CivilSubstantiveAnalysis(_DomainAnalysisBase):
    profile: Literal["civil_substantive"] = "civil_substantive"
    claims: list[CivilClaim] = Field(min_length=1, max_length=32)
    elements: list[CivilElement] = Field(min_length=1, max_length=128)
    burden_of_proof: list[ElementBurdenOfProof] = Field(default_factory=list, max_length=128)
    defenses: list[CivilDefense] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def validate_internal_references(self) -> CivilSubstantiveAnalysis:
        claim_ids = [claim.claim_id for claim in self.claims]
        element_ids = [element.element_id for element in self.elements]
        defense_ids = [defense.defense_id for defense in self.defenses]
        for label, values in (
            ("claim_id", claim_ids),
            ("element_id", element_ids),
            ("defense_id", defense_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"civil substantive {label} values must be unique")

        known_claim_ids = set(claim_ids)
        if any(element.claim_id not in known_claim_ids for element in self.elements):
            raise ValueError("civil substantive element references an unknown claim_id")
        if any(defense.claim_id not in known_claim_ids for defense in self.defenses):
            raise ValueError("civil substantive defense references an unknown claim_id")

        element_id_set = set(element_ids)
        burden_element_ids = [item.element_id for item in self.burden_of_proof]
        if len(burden_element_ids) != len(set(burden_element_ids)):
            raise ValueError("civil substantive permits one burden record per element")
        if any(element_id not in element_id_set for element_id in burden_element_ids):
            raise ValueError("civil substantive burden references an unknown element_id")
        if any(
            not any(element.claim_id == claim_id for element in self.elements)
            for claim_id in known_claim_ids
        ):
            raise ValueError("every civil substantive claim requires at least one element")
        return self


class CivilProcedureAnalysis(_DomainAnalysisBase):
    profile: Literal["civil_procedure"] = "civil_procedure"
    issues: list[CivilProcedureIssue] = Field(min_length=1, max_length=128)


class CriminalSubstantiveAnalysis(_DomainAnalysisBase):
    profile: Literal["criminal_substantive"] = "criminal_substantive"
    issues: list[CriminalSubstantiveIssue] = Field(min_length=1, max_length=128)


class CriminalProcedureAnalysis(_DomainAnalysisBase):
    profile: Literal["criminal_procedure"] = "criminal_procedure"
    issues: list[CriminalProcedureIssue] = Field(min_length=1, max_length=128)


class AdministrativeAnalysis(_DomainAnalysisBase):
    profile: Literal["administrative"] = "administrative"
    issues: list[AdministrativeIssue] = Field(min_length=1, max_length=128)


class ConstitutionalReviewAnalysis(_DomainAnalysisBase):
    profile: Literal["constitutional_review"] = "constitutional_review"
    issues: list[ConstitutionalReviewIssue] = Field(min_length=1, max_length=128)


DomainAnalysis = Annotated[
    CivilSubstantiveAnalysis
    | CivilProcedureAnalysis
    | CriminalSubstantiveAnalysis
    | CriminalProcedureAnalysis
    | AdministrativeAnalysis
    | ConstitutionalReviewAnalysis,
    Field(discriminator="profile"),
]


class LegalAnalysisEnvelope(BaseModel):
    """Untrusted multi-branch proposal containing references, never source bodies."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.legal-analysis/v1"] = "alr-tw.legal-analysis/v1"
    analysis_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    trust_status: Literal["untrusted_client_proposal"] = "untrusted_client_proposal"
    analyses: list[DomainAnalysis] = Field(min_length=1, max_length=6)
    facts: list[FactAssessment] = Field(default_factory=list, max_length=128)
    evidence_assessments: list[EvidenceAssessment] = Field(default_factory=list, max_length=128)
    counter_authority: CounterAuthorityAssessment
    procedural_posture: ProceduralPosture
    limitations: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_internal_references(self) -> LegalAnalysisEnvelope:
        profiles = [analysis.profile for analysis in self.analyses]
        if len(profiles) != len(set(profiles)):
            raise ValueError("legal analysis permits at most one branch per profile")

        issue_ids = [
            issue.issue_id
            for analysis in self.analyses
            if not isinstance(analysis, CivilSubstantiveAnalysis)
            for issue in analysis.issues
        ]
        identifiers = (
            ("issue_id", issue_ids),
            ("fact_id", [fact.fact_id for fact in self.facts]),
            (
                "evidence_id",
                [assessment.evidence_id for assessment in self.evidence_assessments],
            ),
        )
        for label, values in identifiers:
            if len(values) != len(set(values)):
                raise ValueError(f"legal analysis {label} values must be unique")
        return self


class LegalAnalysisDecision(str, Enum):
    VALIDATED = "validated"
    QUALIFIED = "qualified"
    BLOCKED = "blocked"


class LegalAnalysisValidationFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(min_length=1)
    severity: AnalysisValidationSeverity
    path: str = Field(min_length=1)
    message: str = Field(min_length=1)


class LegalAnalysisValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.legal-analysis-validation/v1"] = (
        "alr-tw.legal-analysis-validation/v1"
    )
    analysis_id: str
    profiles: list[LegalAnalysisProfile] = Field(min_length=1, max_length=6)
    decision: LegalAnalysisDecision
    eligible_for_answer_validation: bool
    authorizes_final_answer: Literal[False] = False
    trust_status: Literal["untrusted_client_proposal"] = "untrusted_client_proposal"
    validation_scope: Literal["structural_and_trust_invariants_only"] = (
        "structural_and_trust_invariants_only"
    )
    semantic_entailment_performed: Literal[False] = False
    findings: list[LegalAnalysisValidationFinding] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    qualifications: list[str] = Field(default_factory=list)
    coverage: dict[str, int | str | list[str]] = Field(default_factory=dict)
