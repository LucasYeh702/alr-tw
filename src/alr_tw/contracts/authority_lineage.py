"""Provider-neutral authority and judgment-lineage contracts.

This module describes *what a provider resolved*, not whether a proposition is
legally correct.  In particular, the contract can carry court level, source
role, procedural posture, appeal lineage, and a provider's negative-treatment
label without implementing an opposition classifier or a consensus detector.

The models are deliberately reference-only.  A caller cannot turn an
``official``-looking identifier into authority: :func:`validate_authority_lineage`
must bind every reference to the server-owned source/evidence set for the same
research run.  The result never authorizes citation or final-answer
presentation; existing citation and finalization gates remain the only such
interfaces.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .civil_analysis import ProceduralStage
from .legal_context import (
    AuthorityLevel,
    AuthorityStatus,
    LegalValidityStatus,
    TemporalApplicabilityStatus,
)
from .sources import MaterialType


_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"


def _unique(values: Sequence[str], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} values must be unique")


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


class AuthorityAxis(str, Enum):
    """Independent dimensions used by an authority assessment."""

    NORMATIVE_LEVEL = "normative_level"
    NORMATIVE_FORCE = "normative_force"
    INSTITUTIONAL_LEVEL = "institutional_level"
    ADJUDICATIVE_LEVEL = "adjudicative_level"
    PROCEDURAL_POSTURE = "procedural_posture"
    TEMPORAL_APPLICABILITY = "temporal_applicability"
    LEGAL_VALIDITY = "legal_validity"
    SOURCE_ROLE = "source_role"


class CourtLevel(str, Enum):
    """Provider-neutral court/institution level, not a ranking score."""

    CONSTITUTIONAL_COURT = "constitutional_court"
    SUPREME_COURT = "supreme_court"
    HIGH_COURT = "high_court"
    DISTRICT_COURT = "district_court"
    ADMINISTRATIVE_SUPREME_COURT = "administrative_supreme_court"
    ADMINISTRATIVE_HIGH_COURT = "administrative_high_court"
    ADMINISTRATIVE_DISTRICT_COURT = "administrative_district_court"
    OTHER = "other"
    UNKNOWN = "unknown"


class AdjudicativeLevel(str, Enum):
    """Stage of a decision in an appeal/review chain."""

    FIRST_INSTANCE = "first_instance"
    APPEAL = "appeal"
    FINAL = "final"
    REMAND = "remand"
    RETRIAL = "retrial"
    ENFORCEMENT = "enforcement"
    CONSTITUTIONAL_REVIEW = "constitutional_review"
    OTHER = "other"
    UNKNOWN = "unknown"


class SourceRole(str, Enum):
    """Role a source or section plays in a legal research record."""

    NORMATIVE_TEXT = "normative_text"
    JUDGMENT_HOLDING = "judgment_holding"
    JUDGMENT_REASONING = "judgment_reasoning"
    JUDGMENT_PROCEDURE = "judgment_procedure"
    FACTUAL_RECORD = "factual_record"
    PARTY_ARGUMENT = "party_argument"
    CONCURRING_OPINION = "concurring_opinion"
    DISSENTING_OPINION = "dissenting_opinion"
    COMMENTARY = "commentary"
    CANDIDATE_ONLY = "candidate_only"
    UNKNOWN = "unknown"


class LineageRelation(str, Enum):
    """Directed relationship between two decision nodes.

    ``from_node_id`` is the later or derived decision and ``to_node_id`` is
    the decision it reviews, replaces, or descends from.  No relation implies
    that the later decision is legally correct.
    """

    APPEAL_FROM = "appeal_from"
    REVIEW_OF = "review_of"
    REMANDED_FROM = "remanded_from"
    RETRIAL_OF = "retrial_of"
    ENFORCEMENT_OF = "enforcement_of"
    PROCEDURAL_SUCCESSOR_OF = "procedural_successor_of"
    SEPARATE_OPINION_OF = "separate_opinion_of"
    CONSOLIDATED_WITH = "consolidated_with"


class LineageCoverageStatus(str, Enum):
    """Coverage state for a bounded lineage lookup."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    NOT_CHECKED = "not_checked"
    NOT_FOUND_IN_SCOPE = "not_found_in_scope"
    PROVIDER_ERROR = "provider_error"


class NegativeTreatmentStatus(str, Enum):
    """Provider-reported treatment state.

    The labels are transported only.  ALR-TW does not infer the label, use it
    as a semantic opposition decision, or derive a consensus conclusion.
    """

    NOT_CHECKED = "not_checked"
    NOT_FOUND_IN_SCOPE = "not_found_in_scope"
    FOUND_UNCLASSIFIED = "found_unclassified"
    CRITICIZED = "criticized"
    DISTINGUISHED = "distinguished"
    NOT_FOLLOWED = "not_followed"
    OVERRULED = "overruled"
    REVERSED = "reversed"
    PROVIDER_ERROR = "provider_error"


class AuthorityAxes(BaseModel):
    """Explicit authority axes; unknown is a value, not an assertion."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.authority-axes/v1"] = "alr-tw.authority-axes/v1"
    normative_level: AuthorityLevel = AuthorityLevel.OTHER
    normative_force: AuthorityStatus = AuthorityStatus.UNKNOWN
    institutional_level: CourtLevel = CourtLevel.UNKNOWN
    adjudicative_level: AdjudicativeLevel = AdjudicativeLevel.UNKNOWN
    procedural_stage: ProceduralStage = ProceduralStage.UNKNOWN
    temporal_applicability: TemporalApplicabilityStatus = (
        TemporalApplicabilityStatus.INDETERMINATE
    )
    legal_validity: LegalValidityStatus = LegalValidityStatus.UNKNOWN
    rationale_codes: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_rationale_codes(self) -> AuthorityAxes:
        _unique(self.rationale_codes, "rationale_codes")
        return self

    @property
    def authority_status(self) -> AuthorityStatus:
        """Compatibility alias for the existing legal-context vocabulary."""

        return self.normative_force

    @property
    def unresolved_axes(self) -> tuple[AuthorityAxis, ...]:
        unresolved: list[AuthorityAxis] = []
        if self.normative_force is AuthorityStatus.UNKNOWN:
            unresolved.append(AuthorityAxis.NORMATIVE_FORCE)
        if self.institutional_level is CourtLevel.UNKNOWN:
            unresolved.append(AuthorityAxis.INSTITUTIONAL_LEVEL)
        if self.adjudicative_level is AdjudicativeLevel.UNKNOWN:
            unresolved.append(AuthorityAxis.ADJUDICATIVE_LEVEL)
        if self.procedural_stage is ProceduralStage.UNKNOWN:
            unresolved.append(AuthorityAxis.PROCEDURAL_POSTURE)
        if self.temporal_applicability in {
            TemporalApplicabilityStatus.INDETERMINATE,
            TemporalApplicabilityStatus.HISTORICAL_VERSION_UNAVAILABLE,
        }:
            unresolved.append(AuthorityAxis.TEMPORAL_APPLICABILITY)
        if self.legal_validity is LegalValidityStatus.UNKNOWN:
            unresolved.append(AuthorityAxis.LEGAL_VALIDITY)
        return tuple(unresolved)


class ProceduralPostureAssessment(BaseModel):
    """Server/provider assessment of a decision's procedural posture."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.procedural-posture/v1"] = (
        "alr-tw.procedural-posture/v1"
    )
    stage: ProceduralStage = ProceduralStage.UNKNOWN
    description: str = Field(min_length=1, max_length=1000)
    resolved: bool = False
    source_ids: list[str] = Field(default_factory=list, max_length=32)
    evidence_ids: list[str] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def validate_posture(self) -> ProceduralPostureAssessment:
        _unique(self.source_ids, "procedural posture source_ids")
        _unique(self.evidence_ids, "procedural posture evidence_ids")
        if self.resolved and self.stage is ProceduralStage.UNKNOWN:
            raise ValueError("resolved procedural posture cannot use unknown stage")
        return self


class BoundedAuthorityScope(BaseModel):
    """Explicit provider/query scope for lineage or treatment lookups."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.authority-scope/v1"] = "alr-tw.authority-scope/v1"
    provider_ids: list[str] = Field(min_length=1, max_length=32)
    material_types: list[MaterialType] = Field(min_length=1, max_length=8)
    court_levels: list[CourtLevel] = Field(default_factory=list, max_length=8)
    query_scope: str = Field(min_length=1, max_length=1000)
    time_scope: str | None = Field(default=None, max_length=200)
    max_results: int = Field(default=64, ge=1, le=512)
    global_absence_claim_allowed: Literal[False] = False
    consensus_claim_allowed: Literal[False] = False

    @model_validator(mode="after")
    def validate_scope(self) -> BoundedAuthorityScope:
        _unique(self.provider_ids, "provider_ids")
        _unique([item.value for item in self.material_types], "material_types")
        _unique([item.value for item in self.court_levels], "court_levels")
        if any(not item.strip() for item in self.provider_ids):
            raise ValueError("provider_ids must not contain blank values")
        return self


class BoundedNotFound(BaseModel):
    """A scoped miss that can never establish global absence or consensus."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.bounded-not-found/v1"] = (
        "alr-tw.bounded-not-found/v1"
    )
    status: Literal["not_found_in_scope"] = "not_found_in_scope"
    scope: BoundedAuthorityScope
    checked_at: datetime
    reason_codes: list[str] = Field(default_factory=list, max_length=32)
    global_absence_claim_allowed: Literal[False] = False
    consensus_claim_allowed: Literal[False] = False

    @model_validator(mode="after")
    def validate_checked_at(self) -> BoundedNotFound:
        if not _aware(self.checked_at):
            raise ValueError("bounded not-found checked_at must be timezone-aware")
        _unique(self.reason_codes, "reason_codes")
        return self


class AuthorityLineageNode(BaseModel):
    """One server-resolved source in an appeal/decision lineage graph."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.authority-lineage-node/v1"] = (
        "alr-tw.authority-lineage-node/v1"
    )
    node_id: str = Field(pattern=_ID_PATTERN)
    source_id: str = Field(pattern=_ID_PATTERN)
    material_type: MaterialType
    source_role: SourceRole
    authority_axes: AuthorityAxes
    procedural_posture: ProceduralPostureAssessment
    evidence_ids: list[str] = Field(default_factory=list, max_length=128)
    label: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_references(self) -> AuthorityLineageNode:
        _unique(self.evidence_ids, "lineage node evidence_ids")
        if self.source_id in self.evidence_ids:
            raise ValueError("source_id cannot also be an evidence_id")
        return self


class AuthorityLineageEdge(BaseModel):
    """A provider-reported, directed relation between two lineage nodes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.authority-lineage-edge/v1"] = (
        "alr-tw.authority-lineage-edge/v1"
    )
    edge_id: str = Field(pattern=_ID_PATTERN)
    from_node_id: str = Field(pattern=_ID_PATTERN)
    to_node_id: str = Field(pattern=_ID_PATTERN)
    relation: LineageRelation
    source_ids: list[str] = Field(default_factory=list, max_length=32)
    evidence_ids: list[str] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def validate_edge(self) -> AuthorityLineageEdge:
        if self.from_node_id == self.to_node_id:
            raise ValueError("lineage edge cannot point to itself")
        _unique(self.source_ids, "lineage edge source_ids")
        _unique(self.evidence_ids, "lineage edge evidence_ids")
        return self


class NegativeTreatmentRecord(BaseModel):
    """Provider-reported treatment of one decision by another decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.negative-treatment/v1"] = (
        "alr-tw.negative-treatment/v1"
    )
    target_node_id: str = Field(pattern=_ID_PATTERN)
    status: NegativeTreatmentStatus
    treating_node_ids: list[str] = Field(default_factory=list, max_length=64)
    scope: BoundedAuthorityScope | None = None
    source_ids: list[str] = Field(default_factory=list, max_length=64)
    evidence_ids: list[str] = Field(default_factory=list, max_length=128)
    reason_codes: list[str] = Field(default_factory=list, max_length=32)
    semantic_opposition_classified: Literal[False] = False
    consensus_claim_allowed: Literal[False] = False

    @model_validator(mode="after")
    def validate_treatment_shape(self) -> NegativeTreatmentRecord:
        _unique(self.treating_node_ids, "treating_node_ids")
        _unique(self.source_ids, "negative-treatment source_ids")
        _unique(self.evidence_ids, "negative-treatment evidence_ids")
        _unique(self.reason_codes, "reason_codes")
        if self.status is NegativeTreatmentStatus.NOT_FOUND_IN_SCOPE:
            if self.scope is None:
                raise ValueError("not_found_in_scope treatment requires a bounded scope")
            if self.treating_node_ids or self.source_ids or self.evidence_ids:
                raise ValueError("not_found_in_scope treatment cannot contain treating refs")
        elif self.status is NegativeTreatmentStatus.NOT_CHECKED:
            if self.treating_node_ids:
                raise ValueError("not_checked treatment cannot contain treating refs")
        elif self.status in {
            NegativeTreatmentStatus.FOUND_UNCLASSIFIED,
            NegativeTreatmentStatus.CRITICIZED,
            NegativeTreatmentStatus.DISTINGUISHED,
            NegativeTreatmentStatus.NOT_FOLLOWED,
            NegativeTreatmentStatus.OVERRULED,
            NegativeTreatmentStatus.REVERSED,
        } and not self.treating_node_ids:
            raise ValueError("found treatment requires a treating node reference")
        return self


class AuthorityLineageContract(BaseModel):
    """Server-owned, provider-neutral authority/lineage envelope."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.authority-lineage/v1"] = (
        "alr-tw.authority-lineage/v1"
    )
    run_id: str = Field(pattern=_ID_PATTERN)
    trust_status: Literal["server_owned_authority_lineage"] = (
        "server_owned_authority_lineage"
    )
    coverage_status: LineageCoverageStatus = LineageCoverageStatus.NOT_CHECKED
    scope: BoundedAuthorityScope | None = None
    nodes: list[AuthorityLineageNode] = Field(default_factory=list, max_length=512)
    edges: list[AuthorityLineageEdge] = Field(default_factory=list, max_length=1024)
    negative_treatments: list[NegativeTreatmentRecord] = Field(
        default_factory=list,
        max_length=256,
    )
    not_found: BoundedNotFound | None = None
    limitations: list[str] = Field(default_factory=list, max_length=64)
    semantic_opposition_classified: Literal[False] = False
    global_consensus_claim_allowed: Literal[False] = False

    @model_validator(mode="after")
    def validate_graph(self) -> AuthorityLineageContract:
        node_ids = [item.node_id for item in self.nodes]
        edge_ids = [item.edge_id for item in self.edges]
        _unique(node_ids, "lineage node_id")
        _unique(edge_ids, "lineage edge_id")
        node_set = set(node_ids)
        for edge in self.edges:
            if edge.from_node_id not in node_set or edge.to_node_id not in node_set:
                raise ValueError("lineage edge references an unknown node")
        for treatment in self.negative_treatments:
            if treatment.target_node_id not in node_set:
                raise ValueError("negative treatment references an unknown target node")
            if any(node_id not in node_set for node_id in treatment.treating_node_ids):
                raise ValueError("negative treatment references an unknown treating node")
        if self.coverage_status is LineageCoverageStatus.NOT_FOUND_IN_SCOPE:
            if self.not_found is None or self.scope is None:
                raise ValueError("not_found_in_scope lineage requires a bounded scope and result")
        elif self.not_found is not None:
            raise ValueError("not_found result requires not_found_in_scope coverage")
        if self.not_found is not None and self.scope != self.not_found.scope:
            raise ValueError("lineage scope must match bounded not-found scope")
        _unique(self.limitations, "limitations")
        self._validate_acyclic(node_set)
        return self

    def _validate_acyclic(self, node_ids: set[str]) -> None:
        adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
        for edge in self.edges:
            adjacency[edge.from_node_id].append(edge.to_node_id)
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError("authority lineage graph must be acyclic")
            if node_id in visited:
                return
            visiting.add(node_id)
            for child in adjacency[node_id]:
                visit(child)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in node_ids:
            visit(node_id)


class AuthorityLineageValidationResult(BaseModel):
    """Fail-closed result for server reference and structural validation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.authority-lineage-validation/v1"] = (
        "alr-tw.authority-lineage-validation/v1"
    )
    run_id: str
    valid: bool
    structurally_valid: bool
    eligible_for_authority: bool = False
    safe_for_citation: Literal[False] = False
    semantic_opposition_performed: Literal[False] = False
    global_consensus_claim_allowed: Literal[False] = False
    coverage_status: LineageCoverageStatus
    checked_source_ids: list[str] = Field(default_factory=list)
    checked_evidence_ids: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list, max_length=64)
    qualifications: list[str] = Field(default_factory=list, max_length=64)


def _contract_refs(contract: AuthorityLineageContract) -> tuple[set[str], set[str]]:
    source_ids: set[str] = set()
    evidence_ids: set[str] = set()
    for node in contract.nodes:
        source_ids.add(node.source_id)
        source_ids.update(node.procedural_posture.source_ids)
        evidence_ids.update(node.evidence_ids)
        evidence_ids.update(node.procedural_posture.evidence_ids)
    for edge in contract.edges:
        source_ids.update(edge.source_ids)
        evidence_ids.update(edge.evidence_ids)
    for treatment in contract.negative_treatments:
        source_ids.update(treatment.source_ids)
        evidence_ids.update(treatment.evidence_ids)
    return source_ids, evidence_ids


def validate_authority_lineage(
    contract: AuthorityLineageContract,
    *,
    server_run_id: str,
    server_source_ids: Sequence[str],
    server_evidence_ids: Sequence[str],
) -> AuthorityLineageValidationResult:
    """Validate lineage references against one server-owned research run.

    ``valid`` means the envelope is structurally complete enough for the
    provider-neutral authority contract.  It never means that the provider's
    negative-treatment label is semantically correct and never enables final
    citation.  Foreign IDs, run mismatches, unresolved axes, incomplete
    coverage, and bounded misses therefore fail closed via ``valid=False`` or
    an explicit qualification.
    """

    blockers: list[str] = []
    qualifications: list[str] = []

    # Pydantic's ``model_copy(update=...)`` intentionally skips validation.
    # Re-check the trust and anti-claim sentinels here so a caller cannot forge
    # a server-owned or semantic decision after constructing the model.
    if contract.trust_status != "server_owned_authority_lineage":
        blockers.append("AUTHORITY_LINEAGE_TRUST_STATUS_INVALID")
    if contract.semantic_opposition_classified is not False:
        blockers.append("AUTHORITY_LINEAGE_SEMANTIC_CLASSIFIER_FORGED")
    if contract.global_consensus_claim_allowed is not False:
        blockers.append("AUTHORITY_LINEAGE_CONSENSUS_GATE_FORGED")
    if contract.scope is not None and (
        contract.scope.global_absence_claim_allowed is not False
        or contract.scope.consensus_claim_allowed is not False
    ):
        blockers.append("AUTHORITY_LINEAGE_SCOPE_GATE_FORGED")
    if contract.not_found is not None and (
        contract.not_found.global_absence_claim_allowed is not False
        or contract.not_found.consensus_claim_allowed is not False
    ):
        blockers.append("AUTHORITY_LINEAGE_NOT_FOUND_GATE_FORGED")
    for treatment in contract.negative_treatments:
        if (
            treatment.semantic_opposition_classified is not False
            or treatment.consensus_claim_allowed is not False
        ):
            blockers.append("NEGATIVE_TREATMENT_GATE_FORGED")

    server_sources = list(server_source_ids)
    server_evidence = list(server_evidence_ids)
    if len(server_sources) != len(set(server_sources)):
        blockers.append("SERVER_SOURCE_IDS_DUPLICATE")
    if len(server_evidence) != len(set(server_evidence)):
        blockers.append("SERVER_EVIDENCE_IDS_DUPLICATE")

    source_refs, evidence_refs = _contract_refs(contract)
    foreign_sources = sorted(source_refs.difference(server_sources))
    foreign_evidence = sorted(evidence_refs.difference(server_evidence))
    if contract.run_id != server_run_id:
        blockers.append("AUTHORITY_LINEAGE_RUN_MISMATCH")
    if foreign_sources:
        blockers.append("AUTHORITY_LINEAGE_FOREIGN_SOURCE_ID")
    if foreign_evidence:
        blockers.append("AUTHORITY_LINEAGE_FOREIGN_EVIDENCE_ID")

    if contract.coverage_status is LineageCoverageStatus.NOT_FOUND_IN_SCOPE:
        qualifications.append("AUTHORITY_LINEAGE_NOT_FOUND_IN_SCOPE")
    if contract.coverage_status is not LineageCoverageStatus.COMPLETE:
        qualifications.append("AUTHORITY_LINEAGE_COVERAGE_INCOMPLETE")
    if not contract.nodes and contract.coverage_status is not LineageCoverageStatus.NOT_FOUND_IN_SCOPE:
        blockers.append("AUTHORITY_LINEAGE_NODES_MISSING")

    eligible = not blockers and contract.coverage_status is LineageCoverageStatus.COMPLETE
    for node in contract.nodes:
        if node.source_id not in server_sources:
            blockers.append("AUTHORITY_LINEAGE_SOURCE_NOT_SERVER_OWNED")
        if node.source_role in {SourceRole.CANDIDATE_ONLY, SourceRole.UNKNOWN}:
            eligible = False
            qualifications.append(f"AUTHORITY_LINEAGE_SOURCE_ROLE_UNRESOLVED:{node.node_id}")
        if node.authority_axes.unresolved_axes:
            eligible = False
            qualifications.append(f"AUTHORITY_LINEAGE_AXES_UNRESOLVED:{node.node_id}")
        if not node.procedural_posture.resolved:
            eligible = False
            qualifications.append(f"AUTHORITY_LINEAGE_PROCEDURAL_POSTURE_UNRESOLVED:{node.node_id}")
        if node.procedural_posture.resolved and node.source_id not in node.procedural_posture.source_ids:
            blockers.append("AUTHORITY_LINEAGE_POSTURE_SOURCE_UNBOUND")

    if contract.negative_treatments:
        # Labels are provider output only; no ALR semantic classifier is run.
        eligible = False
        qualifications.append("NEGATIVE_TREATMENT_SEMANTIC_CLASSIFICATION_NOT_PERFORMED")
    if contract.not_found is not None:
        eligible = False
        qualifications.append("AUTHORITY_LINEAGE_NOT_FOUND_IS_BOUNDED_ONLY")

    blockers = list(dict.fromkeys(blockers))
    qualifications = list(dict.fromkeys(qualifications))
    structurally_valid = not blockers
    valid = structurally_valid and eligible
    return AuthorityLineageValidationResult(
        run_id=contract.run_id,
        valid=valid,
        structurally_valid=structurally_valid,
        eligible_for_authority=eligible,
        coverage_status=contract.coverage_status,
        checked_source_ids=sorted(source_refs.intersection(server_sources)),
        checked_evidence_ids=sorted(evidence_refs.intersection(server_evidence)),
        blockers=blockers,
        qualifications=qualifications,
    )


# Short aliases make the provider-neutral vocabulary discoverable without
# creating a second schema or changing finalization/citation contracts.
AuthorityLineage = AuthorityLineageContract
NegativeTreatment = NegativeTreatmentRecord


__all__ = [
    "AdjudicativeLevel",
    "AuthorityAxis",
    "AuthorityAxes",
    "AuthorityLineage",
    "AuthorityLineageContract",
    "AuthorityLineageEdge",
    "AuthorityLineageNode",
    "AuthorityLineageValidationResult",
    "BoundedAuthorityScope",
    "BoundedNotFound",
    "CourtLevel",
    "LineageCoverageStatus",
    "LineageRelation",
    "NegativeTreatment",
    "NegativeTreatmentRecord",
    "NegativeTreatmentStatus",
    "ProceduralPostureAssessment",
    "SourceRole",
    "validate_authority_lineage",
]
