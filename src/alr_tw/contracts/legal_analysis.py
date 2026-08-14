"""Unified legal-analysis envelope proposed by an external reasoning client."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .civil_analysis import (
    AnalysisValidationSeverity,
    BurdenBearer,
    BurdenShiftStatus,
    BurdenType,
    CivilClaim,
    CivilDefense,
    CivilElement,
    CounterAuthorityAssessment,
    ElementAssessmentStatus,
    ElementBurdenOfProof,
    EvidenceAssessment,
    FactAssessment,
    LegalEffectType,
    PresumptionStatus,
    ProceduralPosture,
    RebuttalStatus,
    StandardOfProof,
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


class DomainBurdenOfProof(BaseModel):
    """Issue-level burden record for non-civil-substantive branches."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    issue_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    burden_type: BurdenType
    burden_bearer: BurdenBearer
    presumption: PresumptionStatus
    burden_shift: BurdenShiftStatus
    standard_of_proof: StandardOfProof
    rebuttal_status: RebuttalStatus
    normative_source_ids: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("normative_source_ids")
    @classmethod
    def require_unique_source_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("domain burden source IDs must be unique")
        return value


class DomainDefense(BaseModel):
    """Issue-linked defense/exception proposal for a non-civil branch."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    defense_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    issue_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    label: str = Field(min_length=1, max_length=200)
    legal_effect: LegalEffectType
    status: ElementAssessmentStatus
    normative_source_ids: list[str] = Field(default_factory=list, max_length=32)
    fact_ids: list[str] = Field(default_factory=list, max_length=64)
    evidence_ids: list[str] = Field(default_factory=list, max_length=64)

    @field_validator("normative_source_ids", "fact_ids", "evidence_ids")
    @classmethod
    def require_unique_references(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("domain defense reference IDs must be unique")
        return value

    @model_validator(mode="after")
    def reject_constitutive_effect(self) -> DomainDefense:
        if self.legal_effect is LegalEffectType.RIGHT_CONSTITUTING:
            raise ValueError("a domain defense cannot constitute the claimant right")
        return self


class DomainRefusalConstraint(BaseModel):
    """Client-proposed refusal trigger, retained as an auditable declaration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(pattern=_IDENTIFIER_PATTERN)
    trigger: Literal[
        "missing_normative_source",
        "missing_fact_or_evidence",
        "unresolved_issue",
        "unresolved_burden",
        "unresolved_procedure",
        "incomplete_scope",
    ]
    message: str = Field(min_length=1, max_length=500)


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
    procedural_posture: ProceduralPosture | None = None
    refusal_constraints: list[DomainRefusalConstraint] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_refusal_constraints(self) -> _DomainAnalysisBase:
        codes = [item.code for item in self.refusal_constraints]
        if len(codes) != len(set(codes)):
            raise ValueError("domain refusal constraint codes must be unique")
        return self


class _IssueAnalysisBase(_DomainAnalysisBase):
    """Shared additive domain fields for the five issue-oriented branches."""

    burden_of_proof: list[DomainBurdenOfProof] = Field(default_factory=list, max_length=128)
    defenses: list[DomainDefense] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def validate_domain_references(self) -> _IssueAnalysisBase:
        raw_issues = getattr(self, "issues", [])
        issue_ids = [issue.issue_id for issue in raw_issues]
        if len(issue_ids) != len(set(issue_ids)):
            raise ValueError("domain issue IDs must be unique")
        known_issue_ids = set(issue_ids)
        burden_ids = [item.issue_id for item in self.burden_of_proof]
        if len(burden_ids) != len(set(burden_ids)):
            raise ValueError("domain burden permits one record per issue")
        if any(issue_id not in known_issue_ids for issue_id in burden_ids):
            raise ValueError("domain burden references an unknown issue_id")
        defense_ids = [item.defense_id for item in self.defenses]
        if len(defense_ids) != len(set(defense_ids)):
            raise ValueError("domain defense IDs must be unique")
        if any(item.issue_id not in known_issue_ids for item in self.defenses):
            raise ValueError("domain defense references an unknown issue_id")
        return self


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


class CivilProcedureAnalysis(_IssueAnalysisBase):
    profile: Literal["civil_procedure"] = "civil_procedure"
    issues: list[CivilProcedureIssue] = Field(min_length=1, max_length=128)


class CriminalSubstantiveAnalysis(_IssueAnalysisBase):
    profile: Literal["criminal_substantive"] = "criminal_substantive"
    issues: list[CriminalSubstantiveIssue] = Field(min_length=1, max_length=128)


class CriminalProcedureAnalysis(_IssueAnalysisBase):
    profile: Literal["criminal_procedure"] = "criminal_procedure"
    issues: list[CriminalProcedureIssue] = Field(min_length=1, max_length=128)


class AdministrativeAnalysis(_IssueAnalysisBase):
    profile: Literal["administrative"] = "administrative"
    issues: list[AdministrativeIssue] = Field(min_length=1, max_length=128)


class ConstitutionalReviewAnalysis(_IssueAnalysisBase):
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
        defense_ids = [
            defense.defense_id
            for analysis in self.analyses
            for defense in analysis.defenses
        ]
        identifiers = (
            ("issue_id", issue_ids),
            ("defense_id", defense_ids),
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
