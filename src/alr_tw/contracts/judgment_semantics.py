"""Provider-neutral judgment attribution and disposition contracts.

Taiwanese judgments frequently restate an inferior court's reasoning before
rejecting it.  A keyword hit in a ``理由`` paragraph is therefore not enough
to establish the current court's holding.  This module carries the speaker,
stance, and relationship to the disposition as explicit, fail-closed data.

The contracts do not perform legal entailment.  They only validate that a
server-owned parser attached the records to the same run/source/evidence
scope.  Citation and final-answer gates remain responsible for presentation.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"


def _unique(values: Sequence[str], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} values must be unique")


class JudgmentSpeaker(str, Enum):
    """Speaker or source of a proposition in a judgment section."""

    CURRENT_COURT = "current_court"
    LOWER_COURT = "lower_court"
    PARTY = "party"
    QUOTED_AUTHORITY = "quoted_authority"
    SEPARATE_OPINION = "separate_opinion"
    UNKNOWN = "unknown"


class JudgmentStance(str, Enum):
    """How the current section relates to a cited proposition."""

    ADOPTS = "adopts"
    REJECTS = "rejects"
    DISTINGUISHES = "distinguishes"
    DESCRIBES = "describes"
    PROCEDURAL_ONLY = "procedural_only"
    UNKNOWN = "unknown"


class JudgmentDisposition(str, Enum):
    """Bounded disposition categories extracted from the main text."""

    APPEAL_DISMISSED = "appeal_dismissed"
    AFFIRMED = "affirmed"
    VACATED_REMANDED = "vacated_remanded"
    VACATED_REVERSED = "vacated_reversed"
    PARTIALLY_GRANTED = "partially_granted"
    PROCEDURAL_DISMISSAL = "procedural_dismissal"
    GRANTED = "granted"
    UNKNOWN = "unknown"


class DispositionRelation(str, Enum):
    """Relationship between an attributed section and the disposition."""

    SUPPORTS_RESULT = "supports_result"
    REASON_FOR_REMAND = "reason_for_remand"
    BACKGROUND_ONLY = "background_only"
    UNKNOWN = "unknown"


class AttributionConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class JudgmentAttribution(BaseModel):
    """Server-produced attribution for one parsed judgment section."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.judgment-attribution/v1"] = (
        "alr-tw.judgment-attribution/v1"
    )
    section_id: str = Field(pattern=_ID_PATTERN)
    speaker: JudgmentSpeaker
    stance: JudgmentStance
    relation_to_disposition: DispositionRelation
    confidence: AttributionConfidence
    source_ids: list[str] = Field(default_factory=list, max_length=16)
    evidence_ids: list[str] = Field(default_factory=list, max_length=32)
    eligible_for_claim_support: bool = False
    reason_codes: list[str] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def validate_references(self) -> JudgmentAttribution:
        _unique(self.source_ids, "attribution source_ids")
        _unique(self.evidence_ids, "attribution evidence_ids")
        _unique(self.reason_codes, "attribution reason_codes")
        return self


class JudgmentDispositionFinding(BaseModel):
    """One disposition finding, normally linked to a 主文 section."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.judgment-disposition/v1"] = (
        "alr-tw.judgment-disposition/v1"
    )
    finding_id: str = Field(pattern=_ID_PATTERN)
    section_id: str = Field(pattern=_ID_PATTERN)
    disposition: JudgmentDisposition
    confidence: AttributionConfidence
    source_ids: list[str] = Field(default_factory=list, max_length=16)
    evidence_ids: list[str] = Field(default_factory=list, max_length=32)
    reason_codes: list[str] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def validate_references(self) -> JudgmentDispositionFinding:
        _unique(self.source_ids, "disposition source_ids")
        _unique(self.evidence_ids, "disposition evidence_ids")
        _unique(self.reason_codes, "disposition reason_codes")
        return self


class JudgmentSemanticsContract(BaseModel):
    """Server-owned parser output for one judgment source and research run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.judgment-semantics/v1"] = (
        "alr-tw.judgment-semantics/v1"
    )
    run_id: str = Field(pattern=_ID_PATTERN)
    source_id: str = Field(pattern=_ID_PATTERN)
    canonical_jid: str = Field(min_length=1, max_length=300)
    parser_version: str = Field(min_length=1, max_length=100)
    attributions: list[JudgmentAttribution] = Field(max_length=512)
    dispositions: list[JudgmentDispositionFinding] = Field(max_length=32)
    trust_status: Literal["server_owned_judgment_semantics"] = (
        "server_owned_judgment_semantics"
    )
    semantic_entailment_performed: Literal[False] = False
    warnings: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_collection_ids(self) -> JudgmentSemanticsContract:
        section_ids = [item.section_id for item in self.attributions]
        finding_ids = [item.finding_id for item in self.dispositions]
        _unique(section_ids, "judgment attribution section_ids")
        _unique(finding_ids, "judgment disposition finding_ids")
        _unique(self.warnings, "judgment semantics warnings")
        return self


class JudgmentSemanticsValidationResult(BaseModel):
    """Fail-closed validation result; never a citation authorization."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.judgment-semantics-validation/v1"] = (
        "alr-tw.judgment-semantics-validation/v1"
    )
    run_id: str = Field(pattern=_ID_PATTERN)
    source_id: str = Field(pattern=_ID_PATTERN)
    valid: bool
    structurally_valid: bool
    eligible_for_current_court_claim: bool
    eligible_for_disposition_claim: bool = False
    safe_for_citation: Literal[False] = False
    semantic_entailment_performed: Literal[False] = False
    eligible_attribution_ids: list[str] = Field(default_factory=list, max_length=512)
    eligible_disposition_ids: list[str] = Field(default_factory=list, max_length=32)
    blockers: list[str] = Field(default_factory=list, max_length=64)
    qualifications: list[str] = Field(default_factory=list, max_length=64)


def classify_disposition_text(text: str) -> tuple[JudgmentDisposition, ...]:
    """Classify explicit 主文 phrases without inferring a legal holding."""

    normalized = "".join(text.split())
    results: list[JudgmentDisposition] = []

    def add(value: JudgmentDisposition) -> None:
        if value not in results:
            results.append(value)

    if any(token in normalized for token in ("廢棄", "撤銷")) and any(
        token in normalized for token in ("發回", "更審")
    ):
        add(JudgmentDisposition.VACATED_REMANDED)
    if any(token in normalized for token in ("廢棄", "撤銷")) and any(
        token in normalized for token in ("改判", "自為判決")
    ):
        add(JudgmentDisposition.VACATED_REVERSED)
    if any(token in normalized for token in ("部分有理由", "一部有理由", "部分准許", "一部准許")):
        add(JudgmentDisposition.PARTIALLY_GRANTED)
    if any(
        token in normalized
        for token in ("上訴不合法", "抗告不合法", "程序不合法", "程序不備")
    ):
        add(JudgmentDisposition.PROCEDURAL_DISMISSAL)
    if any(token in normalized for token in ("上訴駁回", "駁回上訴", "抗告駁回", "駁回抗告")):
        add(JudgmentDisposition.APPEAL_DISMISSED)
    if any(token in normalized for token in ("維持原判決", "原判決維持", "維持原裁定", "原裁定維持")):
        add(JudgmentDisposition.AFFIRMED)
    if any(token in normalized for token in ("准許", "應予准許")):
        add(JudgmentDisposition.GRANTED)
    return tuple(results) or (JudgmentDisposition.UNKNOWN,)


def validate_judgment_semantics(
    contract: JudgmentSemanticsContract,
    *,
    server_run_id: str,
    server_source_ids: Sequence[str],
    server_evidence_ids: Sequence[str],
) -> JudgmentSemanticsValidationResult:
    """Validate parser output against server-owned run/source/evidence refs."""

    blockers: list[str] = []
    qualifications: list[str] = []
    source_scope = set(server_source_ids)
    evidence_scope = set(server_evidence_ids)
    if contract.run_id != server_run_id:
        blockers.append("JUDGMENT_SEMANTICS_RUN_MISMATCH")
    if contract.source_id not in source_scope:
        blockers.append("JUDGMENT_SEMANTICS_SOURCE_NOT_SERVER_BOUND")
    if contract.trust_status != "server_owned_judgment_semantics":
        blockers.append("JUDGMENT_SEMANTICS_TRUST_STATUS_FORGED")
    if len(source_scope) != len(server_source_ids) or len(evidence_scope) != len(
        server_evidence_ids
    ):
        blockers.append("JUDGMENT_SEMANTICS_SERVER_SCOPE_DUPLICATE")
    if contract.semantic_entailment_performed is not False:
        blockers.append("JUDGMENT_SEMANTICS_SEMANTIC_FLAG_FORGED")

    eligible_attribution_ids: list[str] = []
    for attribution in contract.attributions:
        if not set(attribution.source_ids).issubset(source_scope):
            blockers.append(f"JUDGMENT_ATTRIBUTION_SOURCE_NOT_BOUND:{attribution.section_id}")
        if not set(attribution.evidence_ids).issubset(evidence_scope):
            blockers.append(f"JUDGMENT_ATTRIBUTION_EVIDENCE_NOT_BOUND:{attribution.section_id}")
        structurally_eligible = (
            attribution.speaker is JudgmentSpeaker.CURRENT_COURT
            and attribution.stance
            in {
                JudgmentStance.ADOPTS,
                JudgmentStance.REJECTS,
                JudgmentStance.DISTINGUISHES,
                JudgmentStance.DESCRIBES,
            }
            and attribution.relation_to_disposition
            in {
                DispositionRelation.SUPPORTS_RESULT,
                DispositionRelation.REASON_FOR_REMAND,
            }
            and bool(attribution.source_ids)
            and bool(attribution.evidence_ids)
        )
        if attribution.eligible_for_claim_support and not structurally_eligible:
            blockers.append(f"JUDGMENT_ATTRIBUTION_ELIGIBILITY_FORGED:{attribution.section_id}")
        if structurally_eligible and attribution.eligible_for_claim_support:
            eligible_attribution_ids.append(attribution.section_id)
        elif attribution.speaker is not JudgmentSpeaker.CURRENT_COURT:
            qualifications.append(f"JUDGMENT_NON_CURRENT_SPEAKER:{attribution.section_id}")

    eligible_disposition_ids: list[str] = []
    for finding in contract.dispositions:
        if not set(finding.source_ids).issubset(source_scope):
            blockers.append(f"JUDGMENT_DISPOSITION_SOURCE_NOT_BOUND:{finding.finding_id}")
        if not set(finding.evidence_ids).issubset(evidence_scope):
            blockers.append(f"JUDGMENT_DISPOSITION_EVIDENCE_NOT_BOUND:{finding.finding_id}")
        if finding.disposition is JudgmentDisposition.UNKNOWN:
            qualifications.append(f"JUDGMENT_DISPOSITION_UNKNOWN:{finding.finding_id}")
        elif finding.source_ids and finding.evidence_ids:
            eligible_disposition_ids.append(finding.finding_id)

    if not eligible_disposition_ids:
        blockers.append("JUDGMENT_DISPOSITION_UNRESOLVED")
    if not eligible_attribution_ids:
        qualifications.append("JUDGMENT_CURRENT_COURT_ATTRIBUTION_UNRESOLVED")

    blockers = list(dict.fromkeys(blockers))
    qualifications = list(dict.fromkeys(qualifications))
    structurally_valid = not blockers
    eligible_for_claim = bool(eligible_attribution_ids) and structurally_valid
    eligible_for_disposition = bool(eligible_disposition_ids) and structurally_valid
    return JudgmentSemanticsValidationResult(
        run_id=contract.run_id,
        source_id=contract.source_id,
        valid=structurally_valid and bool(eligible_disposition_ids),
        structurally_valid=structurally_valid,
        eligible_for_current_court_claim=eligible_for_claim,
        eligible_for_disposition_claim=eligible_for_disposition,
        eligible_attribution_ids=eligible_attribution_ids,
        eligible_disposition_ids=eligible_disposition_ids,
        blockers=blockers,
        qualifications=qualifications,
    )


__all__ = [
    "AttributionConfidence",
    "DispositionRelation",
    "JudgmentAttribution",
    "JudgmentDisposition",
    "JudgmentDispositionFinding",
    "JudgmentSemanticsContract",
    "JudgmentSemanticsValidationResult",
    "JudgmentSpeaker",
    "JudgmentStance",
    "classify_disposition_text",
    "validate_judgment_semantics",
]
