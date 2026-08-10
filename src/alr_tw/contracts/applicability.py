"""Provider-neutral applicability resolution contracts.

The resolver in this module is deliberately structural.  It applies
server-supplied temporal windows and explicit source relationships; it does
not infer a legal relationship from source text and it does not perform
semantic entailment.  A deployment must provide the source records and
relationship metadata from its own authoritative provider.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from enum import Enum
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .legal_context import AuthorityLevel, TemporalApplicabilityStatus
from .sources import MaterialType, TrustStatus


_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$"
_IDENTIFIER_RE = re.compile(_IDENTIFIER_PATTERN)


class ApplicabilityStatus(str, Enum):
    """Deterministic status for a requested normative source set."""

    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"
    INDETERMINATE = "indeterminate"
    CONFLICTING = "conflicting"
    HISTORICAL_VERSION_UNAVAILABLE = "historical_version_unavailable"
    PROVIDER_UNAVAILABLE = "provider_unavailable"


class ApplicabilityResolutionStatus(str, Enum):
    """Trust posture of the server-produced resolution envelope."""

    RESOLVED = "resolved"
    QUALIFIED = "qualified"
    BLOCKED = "blocked"


class ApplicabilityRelationType(str, Enum):
    """Explicit relationships supplied by a server-owned source catalog."""

    SPECIAL_TO_GENERAL = "special_to_general"
    # Aliases make the relation readable to callers using legal-language names.
    SPECIAL_LAW_TO_GENERAL_LAW = "special_to_general"
    SUPERIOR_TO_INFERIOR = "superior_to_inferior"
    TEMPORAL_SUCCESSOR = "temporal_successor"


class ApplicabilitySourceRecord(BaseModel):
    """Server-catalog metadata needed for applicability resolution.

    ``server_owned`` and ``trust_status`` are intentionally explicit.  A
    caller-provided locator or candidate cannot be promoted merely by placing
    its identifier in a request.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.applicability-source/v1"] = (
        "alr-tw.applicability-source/v1"
    )
    source_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    provider_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    material_type: MaterialType = MaterialType.LAW
    authority_level: AuthorityLevel
    title: str | None = Field(default=None, max_length=300)
    scope_key: str | None = Field(default=None, max_length=300)
    effective_from: date | None = None
    effective_until: date | None = None
    repealed_on: date | None = None
    specializes_source_ids: list[str] = Field(default_factory=list, max_length=64)
    superior_source_ids: list[str] = Field(default_factory=list, max_length=64)
    supersedes_source_ids: list[str] = Field(default_factory=list, max_length=64)
    server_owned: bool = False
    # ``EXTERNAL_CANDIDATE`` is the least-trusted available source posture;
    # the source must be explicitly promoted by the server before resolution.
    trust_status: TrustStatus = TrustStatus.EXTERNAL_CANDIDATE

    @property
    def special_to_source_ids(self) -> list[str]:
        """Compatibility spelling for ``specializes_source_ids``."""

        return list(self.specializes_source_ids)

    @property
    def superior_to_source_ids(self) -> list[str]:
        """Compatibility spelling for ``superior_source_ids``."""

        return list(self.superior_source_ids)

    @model_validator(mode="after")
    def validate_source_record(self) -> ApplicabilitySourceRecord:
        relation_groups = (
            self.specializes_source_ids,
            self.superior_source_ids,
            self.supersedes_source_ids,
        )
        for values in relation_groups:
            if len(values) != len(set(values)):
                raise ValueError("applicability relation source IDs must be unique")
            if any(
                not _IDENTIFIER_RE.fullmatch(value) for value in values
            ):
                raise ValueError("applicability relation source IDs are invalid")
        if self.source_id in {
            *self.specializes_source_ids,
            *self.superior_source_ids,
            *self.supersedes_source_ids,
        }:
            raise ValueError("applicability source cannot relate to itself")
        if (
            self.effective_from is not None
            and self.effective_until is not None
            and self.effective_until < self.effective_from
        ):
            raise ValueError("effective_until must not precede effective_from")
        if (
            self.repealed_on is not None
            and self.effective_from is not None
            and self.repealed_on < self.effective_from
        ):
            raise ValueError("repealed_on must not precede effective_from")
        return self


class ApplicabilityRequest(BaseModel):
    """Untrusted request selecting server-catalog sources for one legal date."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.applicability-request/v1"] = (
        "alr-tw.applicability-request/v1"
    )
    source_ids: list[str] = Field(min_length=1, max_length=128)
    as_of_date: date
    scope_key: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def validate_request(self) -> ApplicabilityRequest:
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("applicability request source IDs must be unique")
        if any(not _IDENTIFIER_RE.fullmatch(value) for value in self.source_ids):
            raise ValueError("applicability request source ID is invalid")
        return self


class ApplicabilityRelationFinding(BaseModel):
    """Auditable relationship applied by the deterministic resolver."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    relation_type: ApplicabilityRelationType
    stronger_source_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    weaker_source_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    active: bool


class ApplicabilityCandidateAssessment(BaseModel):
    """Per-source temporal and structural assessment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    temporal_status: TemporalApplicabilityStatus
    active_at_as_of_date: bool
    reason_codes: list[str] = Field(default_factory=list, max_length=32)


class ApplicabilityResolution(BaseModel):
    """Server-owned applicability decision; never a semantic legal conclusion."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.applicability-resolution/v1"] = (
        "alr-tw.applicability-resolution/v1"
    )
    resolution_status: ApplicabilityResolutionStatus
    status: ApplicabilityStatus
    as_of_date: date
    considered_source_ids: list[str] = Field(default_factory=list, max_length=128)
    selected_source_ids: list[str] = Field(default_factory=list, max_length=128)
    controlling_source_id: str | None = None
    candidate_assessments: list[ApplicabilityCandidateAssessment] = Field(
        default_factory=list, max_length=128
    )
    relation_findings: list[ApplicabilityRelationFinding] = Field(
        default_factory=list, max_length=256
    )
    reason_codes: list[str] = Field(default_factory=list, max_length=64)
    limitations: list[str] = Field(default_factory=list, max_length=64)
    resolution_owner: Literal["server"] = "server"
    server_owned: Literal[True] = True
    semantic_entailment_performed: Literal[False] = False

    @model_validator(mode="after")
    def validate_resolution(self) -> ApplicabilityResolution:
        if len(self.considered_source_ids) != len(set(self.considered_source_ids)):
            raise ValueError("considered source IDs must be unique")
        if len(self.selected_source_ids) != len(set(self.selected_source_ids)):
            raise ValueError("selected source IDs must be unique")
        considered = set(self.considered_source_ids)
        selected = set(self.selected_source_ids)
        if not selected.issubset(considered):
            raise ValueError("selected source IDs must be considered source IDs")
        if self.controlling_source_id is not None and self.controlling_source_id not in selected:
            raise ValueError("controlling source must be selected")
        if self.status is ApplicabilityStatus.APPLICABLE:
            if not self.selected_source_ids or self.controlling_source_id is None:
                raise ValueError("applicable resolution requires one controlling source")
            if self.resolution_status is not ApplicabilityResolutionStatus.RESOLVED:
                raise ValueError("applicable resolution must be resolved")
        if self.status is not ApplicabilityStatus.APPLICABLE and self.selected_source_ids:
            raise ValueError("non-applicable resolution cannot select sources")
        return self


class ApplicabilityValidationDecision(str, Enum):
    ACCEPTED = "accepted"
    QUALIFIED = "qualified"
    BLOCKED = "blocked"


class ApplicabilityValidationResult(BaseModel):
    """Fail-closed comparison of a proposed resolution with server facts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.applicability-validation/v1"] = (
        "alr-tw.applicability-validation/v1"
    )
    decision: ApplicabilityValidationDecision
    resolution_status: ApplicabilityResolutionStatus
    status: ApplicabilityStatus
    selected_source_ids: list[str] = Field(default_factory=list, max_length=128)
    reason_codes: list[str] = Field(default_factory=list, max_length=64)
    server_owned: Literal[True] = True
    semantic_entailment_performed: Literal[False] = False


def _temporal_assessment(
    source: ApplicabilitySourceRecord,
    as_of_date: date,
) -> ApplicabilityCandidateAssessment:
    if source.effective_from is not None and as_of_date < source.effective_from:
        return ApplicabilityCandidateAssessment(
            source_id=source.source_id,
            temporal_status=TemporalApplicabilityStatus.NOT_YET_EFFECTIVE,
            active_at_as_of_date=False,
            reason_codes=["APPLICABILITY_SOURCE_NOT_YET_EFFECTIVE"],
        )
    if (
        source.effective_until is not None and as_of_date > source.effective_until
    ) or (source.repealed_on is not None and as_of_date >= source.repealed_on):
        return ApplicabilityCandidateAssessment(
            source_id=source.source_id,
            temporal_status=TemporalApplicabilityStatus.EXPIRED_OR_REPEALED,
            active_at_as_of_date=False,
            reason_codes=["APPLICABILITY_SOURCE_EXPIRED_OR_REPEALED"],
        )
    return ApplicabilityCandidateAssessment(
        source_id=source.source_id,
        temporal_status=TemporalApplicabilityStatus.APPLICABLE,
        active_at_as_of_date=True,
        reason_codes=[],
    )


class ApplicabilityResolver:
    """Resolve explicit temporal and hierarchy metadata from server records.

    ``server_source_ids`` is an independent server-owned catalog reference.  It
    is deliberately separate from ``ApplicabilitySourceRecord.server_owned``:
    a caller can construct or mutate a Pydantic record, but cannot make an
    unbound source part of the server catalog merely by setting that flag.
    Deployments should pass the IDs from their run/catalog store, not from the
    request payload.
    """

    def __init__(
        self,
        server_sources: Sequence[ApplicabilitySourceRecord],
        *,
        server_source_ids: Sequence[str] | None = None,
    ):
        records = list(server_sources)
        source_ids = [item.source_id for item in records]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("server applicability source IDs must be unique")
        self._sources = {item.source_id: item for item in records}
        self._server_source_ids = (
            None if server_source_ids is None else tuple(server_source_ids)
        )
        self._binding_error: str | None = None
        if self._server_source_ids is not None:
            if not self._server_source_ids:
                self._binding_error = "APPLICABILITY_SERVER_CATALOG_BINDING_INVALID"
            elif any(not isinstance(source_id, str) for source_id in self._server_source_ids):
                self._binding_error = "APPLICABILITY_SERVER_CATALOG_BINDING_INVALID"
            elif len(self._server_source_ids) != len(set(self._server_source_ids)):
                self._binding_error = "APPLICABILITY_SERVER_CATALOG_BINDING_INVALID"
            elif any(
                not isinstance(source_id, str)
                or not _IDENTIFIER_RE.fullmatch(source_id)
                for source_id in self._server_source_ids
            ):
                self._binding_error = "APPLICABILITY_SERVER_CATALOG_BINDING_INVALID"

    def resolve(self, request: ApplicabilityRequest) -> ApplicabilityResolution:
        requested_ids = list(request.source_ids)
        if self._server_source_ids is None:
            return self._blocked(
                request,
                reason_codes=["APPLICABILITY_SERVER_CATALOG_BINDING_REQUIRED"],
                limitations=["APPLICABILITY_SERVER_CATALOG_BINDING_REQUIRED"],
            )
        if self._binding_error is not None:
            return self._blocked(
                request,
                reason_codes=[self._binding_error],
            )
        bound_ids = set(self._server_source_ids)
        if any(source_id not in bound_ids for source_id in requested_ids):
            return self._blocked(
                request,
                reason_codes=["APPLICABILITY_SOURCE_NOT_SERVER_BOUND"],
                limitations=["APPLICABILITY_SERVER_CATALOG_SCOPE_LIMITED"],
            )
        missing = [source_id for source_id in requested_ids if source_id not in self._sources]
        if missing:
            return self._blocked(
                request,
                reason_codes=["APPLICABILITY_SOURCE_NOT_FOUND"],
                limitations=["APPLICABILITY_SERVER_CATALOG_INCOMPLETE"],
            )
        records = [self._sources[source_id] for source_id in requested_ids]
        if any(not item.server_owned for item in records):
            return self._blocked(
                request,
                reason_codes=["APPLICABILITY_SOURCE_NOT_SERVER_OWNED"],
            )
        if any(
            item.trust_status
            not in {TrustStatus.OFFICIAL_VERIFIED, TrustStatus.EVIDENCE_ELIGIBLE}
            for item in records
        ):
            return self._blocked(
                request,
                reason_codes=["APPLICABILITY_SOURCE_NOT_VERIFIED"],
            )

        assessments = [
            _temporal_assessment(item, request.as_of_date) for item in records
        ]
        if request.scope_key is not None:
            for index, item in enumerate(records):
                if item.scope_key != request.scope_key:
                    assessments[index] = assessments[index].model_copy(
                        update={
                            "temporal_status": TemporalApplicabilityStatus.INDETERMINATE,
                            "active_at_as_of_date": False,
                            "reason_codes": ["APPLICABILITY_SCOPE_MISMATCH"],
                        }
                    )
        active_ids = {
            item.source_id
            for item in assessments
            if item.active_at_as_of_date
        }
        if not active_ids:
            all_future = all(
                item.temporal_status is TemporalApplicabilityStatus.NOT_YET_EFFECTIVE
                for item in assessments
            )
            status = (
                ApplicabilityStatus.HISTORICAL_VERSION_UNAVAILABLE
                if all_future
                else ApplicabilityStatus.NOT_APPLICABLE
            )
            reason = (
                "APPLICABILITY_HISTORICAL_VERSION_UNAVAILABLE"
                if all_future
                else "APPLICABILITY_NO_ACTIVE_SOURCE"
            )
            return self._blocked(
                request,
                status=status,
                assessments=assessments,
                reason_codes=[reason],
            )

        relation_findings, edges, relation_error = self._relations(
            records,
            active_ids=active_ids,
            requested_ids=set(requested_ids),
        )
        if relation_error is not None:
            return self._blocked(
                request,
                assessments=assessments,
                relation_findings=relation_findings,
                reason_codes=[relation_error],
            )
        if self._has_cycle(edges):
            return self._blocked(
                request,
                assessments=assessments,
                relation_findings=relation_findings,
                status=ApplicabilityStatus.CONFLICTING,
                reason_codes=["APPLICABILITY_RELATION_CYCLE"],
            )

        selected = set(active_ids)
        for stronger, weaker in edges:
            if stronger in active_ids and weaker in active_ids:
                selected.discard(weaker)
        if len(selected) != 1:
            status = (
                ApplicabilityStatus.CONFLICTING
                if edges
                else ApplicabilityStatus.INDETERMINATE
            )
            reason = (
                "APPLICABILITY_ACTIVE_SOURCES_CONFLICT"
                if edges
                else "APPLICABILITY_RELATION_UNRESOLVED"
            )
            return self._blocked(
                request,
                assessments=assessments,
                relation_findings=relation_findings,
                status=status,
                reason_codes=[reason],
            )
        controlling = next(iter(selected))
        return ApplicabilityResolution(
            resolution_status=ApplicabilityResolutionStatus.RESOLVED,
            status=ApplicabilityStatus.APPLICABLE,
            as_of_date=request.as_of_date,
            considered_source_ids=requested_ids,
            selected_source_ids=[controlling],
            controlling_source_id=controlling,
            candidate_assessments=assessments,
            relation_findings=relation_findings,
            reason_codes=[],
        )

    def _relations(
        self,
        records: Sequence[ApplicabilitySourceRecord],
        *,
        active_ids: set[str],
        requested_ids: set[str],
    ) -> tuple[list[ApplicabilityRelationFinding], list[tuple[str, str]], str | None]:
        findings: list[ApplicabilityRelationFinding] = []
        edges: list[tuple[str, str]] = []
        relation_specs = (
            (ApplicabilityRelationType.SPECIAL_TO_GENERAL, "specializes_source_ids"),
            (ApplicabilityRelationType.SUPERIOR_TO_INFERIOR, "superior_source_ids"),
            (ApplicabilityRelationType.TEMPORAL_SUCCESSOR, "supersedes_source_ids"),
        )
        for source in records:
            for relation_type, field_name in relation_specs:
                for target_id in getattr(source, field_name):
                    if target_id not in self._sources or target_id not in requested_ids:
                        return (
                            findings,
                            edges,
                            "APPLICABILITY_RELATION_TARGET_NOT_IN_SCOPE",
                        )
                    active = source.source_id in active_ids and target_id in active_ids
                    findings.append(
                        ApplicabilityRelationFinding(
                            relation_type=relation_type,
                            stronger_source_id=source.source_id,
                            weaker_source_id=target_id,
                            active=active,
                        )
                    )
                    if active:
                        edges.append((source.source_id, target_id))
        return findings, edges, None

    @staticmethod
    def _has_cycle(edges: Sequence[tuple[str, str]]) -> bool:
        graph: dict[str, set[str]] = {}
        for source_id, target_id in edges:
            graph.setdefault(source_id, set()).add(target_id)
            graph.setdefault(target_id, set())
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> bool:
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            if any(visit(child) for child in graph[node]):
                return True
            visiting.remove(node)
            visited.add(node)
            return False

        return any(visit(node) for node in graph)

    @staticmethod
    def _blocked(
        request: ApplicabilityRequest,
        *,
        status: ApplicabilityStatus = ApplicabilityStatus.INDETERMINATE,
        assessments: Sequence[ApplicabilityCandidateAssessment] = (),
        relation_findings: Sequence[ApplicabilityRelationFinding] = (),
        reason_codes: Sequence[str],
        limitations: Sequence[str] = (),
    ) -> ApplicabilityResolution:
        return ApplicabilityResolution(
            resolution_status=ApplicabilityResolutionStatus.BLOCKED,
            status=status,
            as_of_date=request.as_of_date,
            considered_source_ids=list(request.source_ids),
            candidate_assessments=list(assessments),
            relation_findings=list(relation_findings),
            reason_codes=list(dict.fromkeys(reason_codes)),
            limitations=list(dict.fromkeys(limitations)),
        )


def validate_applicability_resolution(
    resolution: ApplicabilityResolution,
    *,
    request: ApplicabilityRequest,
    server_sources: Sequence[ApplicabilitySourceRecord],
    server_source_ids: Sequence[str] | None = None,
) -> ApplicabilityValidationResult:
    """Recompute applicability and reject forged caller-owned decisions.

    ``server_source_ids`` must come from an independent server-owned catalog
    reference.  Omitting it intentionally produces a blocked validation result;
    the source records alone are not an authority binding.
    """

    expected = ApplicabilityResolver(
        server_sources,
        server_source_ids=server_source_ids,
    ).resolve(request)
    if resolution.model_dump(mode="json") != expected.model_dump(mode="json"):
        return ApplicabilityValidationResult(
            decision=ApplicabilityValidationDecision.BLOCKED,
            resolution_status=expected.resolution_status,
            status=expected.status,
            selected_source_ids=[],
            reason_codes=["APPLICABILITY_SERVER_RESOLUTION_MISMATCH"],
        )
    if expected.status is ApplicabilityStatus.APPLICABLE:
        decision = (
            ApplicabilityValidationDecision.QUALIFIED
            if expected.limitations
            else ApplicabilityValidationDecision.ACCEPTED
        )
        selected = list(expected.selected_source_ids)
    else:
        decision = ApplicabilityValidationDecision.BLOCKED
        selected = []
    return ApplicabilityValidationResult(
        decision=decision,
        resolution_status=expected.resolution_status,
        status=expected.status,
        selected_source_ids=selected,
        reason_codes=list(expected.reason_codes),
    )


# Concise facade name for MCP/adapters.
validate_applicability = validate_applicability_resolution


__all__ = [
    "ApplicabilityCandidateAssessment",
    "ApplicabilityRelationFinding",
    "ApplicabilityRelationType",
    "ApplicabilityRequest",
    "ApplicabilityResolution",
    "ApplicabilityResolutionStatus",
    "ApplicabilityResolver",
    "ApplicabilitySourceRecord",
    "ApplicabilityStatus",
    "ApplicabilityValidationDecision",
    "ApplicabilityValidationResult",
    "validate_applicability",
    "validate_applicability_resolution",
]
