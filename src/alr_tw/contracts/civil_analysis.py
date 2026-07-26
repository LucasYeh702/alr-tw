"""Public civil-law analysis envelope proposed by an external reasoning client."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$"


class LegalEffectType(str, Enum):
    RIGHT_CONSTITUTING = "right_constituting"
    RIGHT_IMPEDING = "right_impeding"
    RIGHT_EXTINGUISHING = "right_extinguishing"
    DEFENSE = "defense"
    LIABILITY_REDUCTION = "liability_reduction"
    REMEDY_CALCULATION = "remedy_calculation"


class ElementAssessmentStatus(str, Enum):
    MET = "met"
    NOT_MET = "not_met"
    UNCERTAIN = "uncertain"
    NOT_APPLICABLE = "not_applicable"


class FindingState(str, Enum):
    ALLEGED = "alleged"
    ADMITTED = "admitted"
    DISPUTED = "disputed"
    SUPPORTED = "supported"
    PROVEN = "proven"
    CONTRADICTED = "contradicted"
    INADMISSIBLE = "inadmissible"
    EXCLUDED = "excluded"


class BurdenType(str, Enum):
    PLEADING = "pleading"
    PRODUCTION = "production"
    PERSUASION = "persuasion"
    OBJECTIVE_RISK = "objective_risk"


class BurdenBearer(str, Enum):
    CLAIMANT = "claimant"
    DEFENDANT = "defendant"
    THIRD_PARTY = "third_party"
    COURT_EX_OFFICIO = "court_ex_officio"
    DISPUTED = "disputed"
    UNKNOWN = "unknown"


class PresumptionStatus(str, Enum):
    NONE = "none"
    ASSERTED = "asserted"
    APPLICABLE = "applicable"
    REBUTTED = "rebutted"
    UNCERTAIN = "uncertain"


class BurdenShiftStatus(str, Enum):
    NONE = "none"
    SHIFTED = "shifted"
    MAY_SHIFT = "may_shift"
    DISPUTED = "disputed"
    UNKNOWN = "unknown"


class StandardOfProof(str, Enum):
    ORDINARY_CIVIL = "ordinary_civil"
    HEIGHTENED = "heightened"
    REDUCED = "reduced"
    PRIMA_FACIE = "prima_facie"
    STATUTORY_SPECIFIC = "statutory_specific"
    UNKNOWN = "unknown"


class RebuttalStatus(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    NOT_ATTEMPTED = "not_attempted"
    PENDING = "pending"
    REBUTTED = "rebutted"
    NOT_REBUTTED = "not_rebutted"
    UNCERTAIN = "uncertain"


class ProceduralStage(str, Enum):
    PRE_FILING = "pre_filing"
    FIRST_INSTANCE = "first_instance"
    APPEAL = "appeal"
    FINAL = "final"
    ENFORCEMENT = "enforcement"
    RETRIAL = "retrial"
    OTHER = "other"
    UNKNOWN = "unknown"


class CounterAuthorityStatus(str, Enum):
    NOT_SEARCHED = "not_searched"
    FOUND = "found"
    NOT_FOUND_IN_SCOPE = "not_found_in_scope"
    SEARCH_INCOMPLETE = "search_incomplete"
    PROVIDER_ERROR = "provider_error"


class CivilClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    label: str = Field(min_length=1, max_length=200)
    legal_basis_source_ids: list[str] = Field(default_factory=list, max_length=32)
    requested_effects: list[LegalEffectType] = Field(min_length=1, max_length=8)


class CivilElement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    element_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    claim_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    label: str = Field(min_length=1, max_length=200)
    proposition: str = Field(min_length=1, max_length=2000)
    legal_effect: LegalEffectType
    status: ElementAssessmentStatus
    normative_source_ids: list[str] = Field(default_factory=list, max_length=32)
    fact_ids: list[str] = Field(default_factory=list, max_length=64)
    evidence_ids: list[str] = Field(default_factory=list, max_length=64)


class ElementBurdenOfProof(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    element_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    burden_type: BurdenType
    burden_bearer: BurdenBearer
    presumption: PresumptionStatus
    burden_shift: BurdenShiftStatus
    standard_of_proof: StandardOfProof
    rebuttal_status: RebuttalStatus
    normative_source_ids: list[str] = Field(default_factory=list, max_length=32)


class CivilDefense(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    defense_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    claim_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    label: str = Field(min_length=1, max_length=200)
    legal_effect: LegalEffectType
    status: ElementAssessmentStatus
    normative_source_ids: list[str] = Field(default_factory=list, max_length=32)
    fact_ids: list[str] = Field(default_factory=list, max_length=64)
    evidence_ids: list[str] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def validate_defense_effect(self) -> CivilDefense:
        allowed = {
            LegalEffectType.RIGHT_IMPEDING,
            LegalEffectType.RIGHT_EXTINGUISHING,
            LegalEffectType.DEFENSE,
            LegalEffectType.LIABILITY_REDUCTION,
        }
        if self.legal_effect not in allowed:
            raise ValueError("defense must use an impeding, extinguishing, or defensive effect")
        return self


class FactAssessment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    statement: str = Field(min_length=1, max_length=2000)
    status: FindingState
    evidence_ids: list[str] = Field(default_factory=list, max_length=64)


class EvidenceAssessment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    status: FindingState
    supports_fact_ids: list[str] = Field(default_factory=list, max_length=64)


class CounterAuthorityAssessment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: CounterAuthorityStatus
    scope_description: str | None = Field(default=None, max_length=1000)
    source_ids: list[str] = Field(default_factory=list, max_length=64)
    absence_established: Literal[False] = False

    @model_validator(mode="after")
    def validate_counter_authority_scope(self) -> CounterAuthorityAssessment:
        if self.status is CounterAuthorityStatus.FOUND and not self.source_ids:
            raise ValueError("found counter-authority requires at least one source_id")
        if (
            self.status is CounterAuthorityStatus.NOT_FOUND_IN_SCOPE
            and not (self.scope_description or "").strip()
        ):
            raise ValueError("not_found_in_scope requires an explicit bounded scope")
        return self


class ProceduralPosture(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: ProceduralStage
    description: str = Field(min_length=1, max_length=1000)
    source_ids: list[str] = Field(default_factory=list, max_length=32)
    fact_ids: list[str] = Field(default_factory=list, max_length=32)


class CivilLawAnalysis(BaseModel):
    """Untrusted analysis proposal; it contains references, never source bodies."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.civil-law-analysis/v1"] = (
        "alr-tw.civil-law-analysis/v1"
    )
    analysis_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    trust_status: Literal["untrusted_client_proposal"] = "untrusted_client_proposal"
    claims: list[CivilClaim] = Field(min_length=1, max_length=32)
    elements: list[CivilElement] = Field(min_length=1, max_length=128)
    burden_of_proof: list[ElementBurdenOfProof] = Field(default_factory=list, max_length=128)
    defenses: list[CivilDefense] = Field(default_factory=list, max_length=64)
    facts: list[FactAssessment] = Field(default_factory=list, max_length=128)
    evidence_assessments: list[EvidenceAssessment] = Field(default_factory=list, max_length=128)
    counter_authority: CounterAuthorityAssessment
    procedural_posture: ProceduralPosture
    limitations: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_internal_references(self) -> CivilLawAnalysis:
        claim_ids = [claim.claim_id for claim in self.claims]
        element_ids = [element.element_id for element in self.elements]
        defense_ids = [defense.defense_id for defense in self.defenses]
        fact_ids = [fact.fact_id for fact in self.facts]
        evidence_ids = [item.evidence_id for item in self.evidence_assessments]
        for label, values in (
            ("claim_id", claim_ids),
            ("element_id", element_ids),
            ("defense_id", defense_ids),
            ("fact_id", fact_ids),
            ("evidence_id", evidence_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"civil analysis {label} values must be unique")

        known_claim_ids = set(claim_ids)
        if any(element.claim_id not in known_claim_ids for element in self.elements):
            raise ValueError("civil analysis element references an unknown claim_id")
        if any(defense.claim_id not in known_claim_ids for defense in self.defenses):
            raise ValueError("civil analysis defense references an unknown claim_id")

        burden_element_ids = [item.element_id for item in self.burden_of_proof]
        if len(burden_element_ids) != len(set(burden_element_ids)):
            raise ValueError("civil analysis permits at most one burden record per element")
        if any(element_id not in set(element_ids) for element_id in burden_element_ids):
            raise ValueError("civil analysis burden record references an unknown element_id")
        return self


class AnalysisValidationSeverity(str, Enum):
    BLOCKER = "blocker"
    QUALIFICATION = "qualification"
    INFO = "info"


class CivilAnalysisDecision(str, Enum):
    VALIDATED = "validated"
    QUALIFIED = "qualified"
    BLOCKED = "blocked"


class CivilAnalysisValidationFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(min_length=1)
    severity: AnalysisValidationSeverity
    path: str = Field(min_length=1)
    message: str = Field(min_length=1)


class CivilAnalysisValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.civil-analysis-validation/v1"] = (
        "alr-tw.civil-analysis-validation/v1"
    )
    analysis_id: str
    decision: CivilAnalysisDecision
    eligible_for_answer_validation: bool
    authorizes_final_answer: Literal[False] = False
    trust_status: Literal["untrusted_client_proposal"] = "untrusted_client_proposal"
    validation_scope: Literal["structural_and_trust_invariants_only"] = (
        "structural_and_trust_invariants_only"
    )
    semantic_entailment_performed: Literal[False] = False
    findings: list[CivilAnalysisValidationFinding] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    qualifications: list[str] = Field(default_factory=list)
    coverage: dict[str, int] = Field(default_factory=dict)
