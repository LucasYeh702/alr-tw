"""Provider-neutral semantic-verifier plugin contracts.

The core runtime deliberately treats a semantic plugin as an advisory sidecar.
It may compare a server-selected proposition with server-owned references and
report a bounded relation, but it cannot mint evidence, mutate source trust, or
authorize an answer/finalization posture.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .sources import EvidenceSpan, SourceRecord, TrustStatus


_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
_ReferenceId = Annotated[str, Field(pattern=_ID_PATTERN)]


class SemanticVerificationOutcome(str, Enum):
    """Bounded relation reported by a plugin; it is not a legal conclusion."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    UNCERTAIN = "uncertain"
    NOT_EVALUATED = "not_evaluated"


class SemanticVerificationTargetKind(str, Enum):
    """Server-owned proposition kinds that a plugin may inspect."""

    CLAIM = "claim"
    ELEMENT = "element"
    DEFENSE = "defense"
    ISSUE = "issue"
    PROCEDURAL_POSTURE = "procedural_posture"
    JUDGMENT_HOLDING = "judgment_holding"
    JUDGMENT_DISPOSITION = "judgment_disposition"


class SemanticVerifierRunStatus(str, Enum):
    """Execution status before the result crosses the server validation gate."""

    COMPLETED = "completed"
    PARTIAL = "partial"
    NOT_EVALUATED = "not_evaluated"
    FAILED = "failed"


class SemanticVerifierValidationDecision(str, Enum):
    """Structural acceptance of an advisory plugin result."""

    ACCEPTED = "accepted"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class SemanticVerifierTarget(BaseModel):
    """A server-selected proposition reference sent to a plugin.

    The proposition is a bounded task description, not source authority.  A
    plugin must never treat the target itself as evidence.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_id: str = Field(pattern=_ID_PATTERN)
    target_kind: SemanticVerificationTargetKind
    proposition: str = Field(min_length=1, max_length=4000)
    source_ids: list[_ReferenceId] = Field(default_factory=list, max_length=64)
    evidence_ids: list[_ReferenceId] = Field(default_factory=list, max_length=128)

    @field_validator("source_ids", "evidence_ids")
    @classmethod
    def require_unique_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("semantic verifier reference IDs must be unique")
        return value


class SemanticVerifierRequest(BaseModel):
    """Server-owned request envelope passed to an optional plugin."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.semantic-verifier-request/v1"] = (
        "alr-tw.semantic-verifier-request/v1"
    )
    request_id: str = Field(pattern=_ID_PATTERN)
    run_id: str = Field(pattern=_ID_PATTERN)
    targets: list[SemanticVerifierTarget] = Field(min_length=1, max_length=128)
    scope: str = Field(min_length=1, max_length=500)
    trust_status: Literal["server_owned_verifier_request"] = (
        "server_owned_verifier_request"
    )
    semantic_evaluation_requested: Literal[True] = True

    @model_validator(mode="after")
    def validate_targets(self) -> SemanticVerifierRequest:
        target_ids = [item.target_id for item in self.targets]
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("semantic verifier target IDs must be unique")
        return self


class SemanticVerifierFinding(BaseModel):
    """One advisory plugin relation for one target."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_id: str = Field(pattern=_ID_PATTERN)
    outcome: SemanticVerificationOutcome
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    referenced_source_ids: list[_ReferenceId] = Field(default_factory=list, max_length=64)
    referenced_evidence_ids: list[_ReferenceId] = Field(default_factory=list, max_length=128)
    rationale: str | None = Field(default=None, max_length=2000)

    @field_validator("referenced_source_ids", "referenced_evidence_ids")
    @classmethod
    def require_unique_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("semantic verifier finding reference IDs must be unique")
        return value

    @model_validator(mode="after")
    def require_bounded_confidence(self) -> SemanticVerifierFinding:
        if self.outcome in {
            SemanticVerificationOutcome.SUPPORTS,
            SemanticVerificationOutcome.CONTRADICTS,
        } and self.confidence is None:
            raise ValueError("support/contradict findings require confidence")
        return self


class SemanticVerifierResult(BaseModel):
    """Untrusted output from a semantic plugin.

    The false capability sentinels are checked again by the server validator;
    they are not trusted merely because Pydantic accepted the payload.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.semantic-verifier-result/v1"] = (
        "alr-tw.semantic-verifier-result/v1"
    )
    request_id: str = Field(pattern=_ID_PATTERN)
    run_id: str = Field(pattern=_ID_PATTERN)
    plugin_id: str = Field(pattern=_ID_PATTERN)
    plugin_version: str = Field(pattern=_ID_PATTERN)
    status: SemanticVerifierRunStatus
    findings: list[SemanticVerifierFinding] = Field(default_factory=list, max_length=128)
    reason_codes: list[str] = Field(default_factory=list, max_length=32)
    semantic_evaluation_performed: Literal[True] = True
    legal_entailment_authorized: Literal[False] = False
    evidence_promotion_allowed: Literal[False] = False
    source_trust_mutation_allowed: Literal[False] = False
    finalization_authorized: Literal[False] = False
    final_answer_authorized: Literal[False] = False
    advisory_only: Literal[True] = True

    @field_validator("reason_codes")
    @classmethod
    def require_unique_reason_codes(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("semantic verifier reason codes must be unique")
        return value

    @model_validator(mode="after")
    def require_unique_targets(self) -> SemanticVerifierResult:
        target_ids = [item.target_id for item in self.findings]
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("semantic verifier may return at most one finding per target")
        return self


class SemanticVerifierValidationFinding(BaseModel):
    """Server-generated diagnostic for plugin-result validation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(pattern=_ID_PATTERN)
    path: str = Field(min_length=1, max_length=300)
    message: str = Field(min_length=1, max_length=1000)
    blocker: bool = False


class SemanticVerifierValidationResult(BaseModel):
    """Server-owned, advisory-only acceptance envelope."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.semantic-verifier-validation/v1"] = (
        "alr-tw.semantic-verifier-validation/v1"
    )
    request_id: str
    run_id: str
    plugin_id: str
    decision: SemanticVerifierValidationDecision
    findings: list[SemanticVerifierFinding] = Field(default_factory=list, max_length=128)
    diagnostics: list[SemanticVerifierValidationFinding] = Field(
        default_factory=list, max_length=128
    )
    reason_codes: list[str] = Field(default_factory=list, max_length=32)
    advisory_only: Literal[True] = True
    safe_for_finalization: Literal[False] = False
    authorizes_final_answer: Literal[False] = False
    can_promote_evidence: Literal[False] = False
    can_mutate_source_trust: Literal[False] = False
    semantic_entailment_authorized: Literal[False] = False


@runtime_checkable
class SemanticVerifierPlugin(Protocol):
    """Minimal synchronous plugin port; implementations are deployer-owned."""

    @property
    def plugin_id(self) -> str: ...

    @property
    def plugin_version(self) -> str: ...

    def verify(self, request: SemanticVerifierRequest) -> SemanticVerifierResult: ...


def validate_semantic_verifier_result(
    result: SemanticVerifierResult,
    *,
    request: SemanticVerifierRequest,
    server_run_id: str,
    server_targets: Mapping[str, SemanticVerifierTarget] | Sequence[SemanticVerifierTarget],
    server_sources: Sequence[SourceRecord],
    server_evidence: Sequence[EvidenceSpan],
    expected_plugin_id: str | None = None,
    expected_plugin_version: str | None = None,
) -> SemanticVerifierValidationResult:
    """Validate a plugin response against independent server-owned bindings.

    ``supports`` and ``contradicts`` are retained only as advisory findings.
    They never enter source promotion, claim-support, or finalization paths.
    """

    diagnostics: list[SemanticVerifierValidationFinding] = []

    def add(code: str, path: str, message: str, *, blocker: bool = True) -> None:
        diagnostics.append(
            SemanticVerifierValidationFinding(
                code=code,
                path=path,
                message=message,
                blocker=blocker,
            )
        )

    if request.trust_status != "server_owned_verifier_request":
        add(
            "SEMANTIC_VERIFIER_REQUEST_NOT_SERVER_OWNED",
            "request.trust_status",
            "Verifier requests must be issued by the server-owned research run.",
        )
    if request.run_id != server_run_id or result.run_id != server_run_id:
        add(
            "SEMANTIC_VERIFIER_RUN_NOT_SERVER_BOUND",
            "run_id",
            "Plugin request/result run_id does not match the server-owned run.",
        )
    if result.request_id != request.request_id:
        add(
            "SEMANTIC_VERIFIER_REQUEST_ID_MISMATCH",
            "request_id",
            "Plugin result does not belong to the submitted verifier request.",
        )
    if expected_plugin_id is not None and result.plugin_id != expected_plugin_id:
        add(
            "SEMANTIC_VERIFIER_PLUGIN_ID_MISMATCH",
            "plugin_id",
            "Plugin result identity does not match the registered adapter.",
        )
    if expected_plugin_version is not None and result.plugin_version != expected_plugin_version:
        add(
            "SEMANTIC_VERIFIER_PLUGIN_VERSION_MISMATCH",
            "plugin_version",
            "Plugin result version does not match the registered adapter.",
        )
    if result.semantic_evaluation_performed is not True:
        add(
            "SEMANTIC_VERIFIER_EVALUATION_SENTINEL_INVALID",
            "semantic_evaluation_performed",
            "The plugin evaluation sentinel is invalid.",
        )
    for field_name in (
        "legal_entailment_authorized",
        "evidence_promotion_allowed",
        "source_trust_mutation_allowed",
        "finalization_authorized",
        "final_answer_authorized",
        "advisory_only",
    ):
        expected = field_name == "advisory_only"
        if getattr(result, field_name) is not expected:
            add(
                "SEMANTIC_VERIFIER_AUTHORITY_SENTINEL_FORGED",
                field_name,
                "A plugin cannot authorize evidence, trust, finalization, or answers.",
            )

    target_map: dict[str, SemanticVerifierTarget] = {}
    raw_server_targets = (
        list(server_targets.values()) if isinstance(server_targets, Mapping) else list(server_targets)
    )
    for index, raw_target in enumerate(raw_server_targets):
        try:
            parsed_target = (
                raw_target
                if isinstance(raw_target, SemanticVerifierTarget)
                else SemanticVerifierTarget.model_validate(raw_target)
            )
        except Exception as exc:
            add(
                "SEMANTIC_VERIFIER_SERVER_TARGET_INVALID",
                f"server_targets[{index}]",
                f"Server target failed schema validation: {type(exc).__name__}",
            )
            continue
        target_map[parsed_target.target_id] = parsed_target
    request_targets: list[SemanticVerifierTarget] = []
    for index, raw_target in enumerate(request.targets):
        try:
            parsed_target = (
                raw_target
                if isinstance(raw_target, SemanticVerifierTarget)
                else SemanticVerifierTarget.model_validate(raw_target)
            )
        except Exception as exc:
            add(
                "SEMANTIC_VERIFIER_REQUEST_TARGET_INVALID",
                f"request.targets[{index}]",
                f"Request target failed schema validation: {type(exc).__name__}",
            )
            continue
        request_targets.append(parsed_target)
    request_target_ids = {item.target_id for item in request_targets}
    unknown_request_targets = request_target_ids - set(target_map)
    if unknown_request_targets:
        add(
            "SEMANTIC_VERIFIER_REQUEST_TARGET_NOT_SERVER_OWNED",
            "request.targets",
            "The request contains target IDs outside the server-owned target set.",
        )

    sources = {item.source_id: item for item in server_sources}
    evidence = {item.evidence_id: item for item in server_evidence}
    # Freshness is intentionally evaluated against current wall-clock time;
    # the host can pin a stricter run clock by removing expired records before
    # invoking this facade.
    now = datetime.now(UTC)
    accepted_findings: list[SemanticVerifierFinding] = []
    seen_target_ids: set[str] = set()
    raw_findings = result.findings if isinstance(result.findings, (list, tuple)) else []
    if not isinstance(result.findings, (list, tuple)):
        add(
            "SEMANTIC_VERIFIER_FINDINGS_INVALID",
            "findings",
            "Plugin findings must be a bounded sequence.",
        )
    for index, raw_finding in enumerate(raw_findings):
        path = f"findings[{index}]"
        try:
            finding = (
                raw_finding
                if isinstance(raw_finding, SemanticVerifierFinding)
                else SemanticVerifierFinding.model_validate(raw_finding)
            )
        except Exception as exc:
            add(
                "SEMANTIC_VERIFIER_FINDING_INVALID",
                path,
                f"Plugin finding failed schema validation: {type(exc).__name__}",
            )
            continue
        if finding.target_id in seen_target_ids:
            add(
                "SEMANTIC_VERIFIER_TARGET_DUPLICATED",
                f"{path}.target_id",
                "A plugin may return at most one finding for each target.",
            )
            continue
        seen_target_ids.add(finding.target_id)
        bound_target = target_map.get(finding.target_id)
        if finding.target_id not in request_target_ids or bound_target is None:
            add(
                "SEMANTIC_VERIFIER_TARGET_NOT_SERVER_OWNED",
                f"{path}.target_id",
                "Finding target is not bound to a server-owned verifier target.",
            )
            continue
        target_source_ids = set(bound_target.source_ids)
        target_evidence_ids = set(bound_target.evidence_ids)
        out_of_scope_source_ids = set(finding.referenced_source_ids) - target_source_ids
        out_of_scope_evidence_ids = set(finding.referenced_evidence_ids) - target_evidence_ids
        if out_of_scope_source_ids:
            add(
                "SEMANTIC_VERIFIER_SOURCE_OUTSIDE_TARGET_SCOPE",
                f"{path}.referenced_source_ids",
                "Finding source references must be declared by the target scope.",
            )
        if out_of_scope_evidence_ids:
            add(
                "SEMANTIC_VERIFIER_EVIDENCE_OUTSIDE_TARGET_SCOPE",
                f"{path}.referenced_evidence_ids",
                "Finding evidence references must be declared by the target scope.",
            )
        if finding.outcome in {
            SemanticVerificationOutcome.SUPPORTS,
            SemanticVerificationOutcome.CONTRADICTS,
        } and not (
            finding.referenced_source_ids or finding.referenced_evidence_ids
        ):
            add(
                "SEMANTIC_VERIFIER_SUPPORT_REFERENCE_REQUIRED",
                path,
                "A supports/contradicts finding requires a server reference.",
            )
            continue
        invalid = bool(out_of_scope_source_ids or out_of_scope_evidence_ids)
        for source_id in finding.referenced_source_ids:
            source = sources.get(source_id)
            if source is None:
                add(
                    "SEMANTIC_VERIFIER_SOURCE_NOT_SERVER_OWNED",
                    f"{path}.referenced_source_ids",
                    f"Unknown server source reference: {source_id}",
                )
                invalid = True
                continue
            if (
                source.expires_at.tzinfo is None
                or source.expires_at.utcoffset() is None
                or source.expires_at <= now
                or source.trust_status is not TrustStatus.EVIDENCE_ELIGIBLE
            ):
                add(
                    "SEMANTIC_VERIFIER_SOURCE_NOT_ELIGIBLE",
                    f"{path}.referenced_source_ids",
                    f"Source is stale or not evidence eligible: {source_id}",
                )
                invalid = True
        for evidence_id in finding.referenced_evidence_ids:
            span = evidence.get(evidence_id)
            if span is None:
                add(
                    "SEMANTIC_VERIFIER_EVIDENCE_NOT_SERVER_OWNED",
                    f"{path}.referenced_evidence_ids",
                    f"Unknown server evidence reference: {evidence_id}",
                )
                invalid = True
                continue
            source = sources.get(span.source_id)
            if (
                source is None
                or source.expires_at.tzinfo is None
                or source.expires_at.utcoffset() is None
                or source.expires_at <= now
                or source.trust_status is not TrustStatus.EVIDENCE_ELIGIBLE
                or not span.eligible_for_claim_support
            ):
                add(
                    "SEMANTIC_VERIFIER_EVIDENCE_NOT_ELIGIBLE",
                    f"{path}.referenced_evidence_ids",
                    f"Evidence is stale, foreign, or not eligible: {evidence_id}",
                )
                invalid = True
        if not invalid:
            accepted_findings.append(finding)

    if result.status is SemanticVerifierRunStatus.FAILED:
        add(
            "SEMANTIC_VERIFIER_RUN_FAILED",
            "status",
            "The plugin reported failure; the result cannot be treated as advisory success.",
        )
    blockers = any(item.blocker for item in diagnostics)
    if blockers:
        decision = SemanticVerifierValidationDecision.BLOCKED
    elif result.status in {
        SemanticVerifierRunStatus.PARTIAL,
        SemanticVerifierRunStatus.NOT_EVALUATED,
    }:
        decision = SemanticVerifierValidationDecision.PARTIAL
    else:
        if len(accepted_findings) < len(request_target_ids):
            diagnostics.append(
                SemanticVerifierValidationFinding(
                    code="SEMANTIC_VERIFIER_TARGET_COVERAGE_PARTIAL",
                    path="findings",
                    message="Completed plugin output did not evaluate every requested target.",
                    blocker=False,
                )
            )
            decision = SemanticVerifierValidationDecision.PARTIAL
        else:
            decision = SemanticVerifierValidationDecision.ACCEPTED
    final_findings = [] if decision is SemanticVerifierValidationDecision.BLOCKED else accepted_findings
    return SemanticVerifierValidationResult(
        request_id=request.request_id,
        run_id=server_run_id,
        plugin_id=result.plugin_id,
        decision=decision,
        findings=final_findings,
        diagnostics=diagnostics,
        reason_codes=list(dict.fromkeys(result.reason_codes)),
    )


def execute_semantic_verifier(
    plugin: SemanticVerifierPlugin,
    request: SemanticVerifierRequest,
    *,
    server_run_id: str,
    server_targets: Mapping[str, SemanticVerifierTarget] | Sequence[SemanticVerifierTarget],
    server_sources: Sequence[SourceRecord],
    server_evidence: Sequence[EvidenceSpan],
) -> SemanticVerifierValidationResult:
    """Run one plugin through a fail-closed boundary.

    Plugin exceptions and malformed payloads become blocked diagnostics; they
    are never interpreted as ``uncertain`` or a clean negative result.
    """

    from pydantic import ValidationError

    plugin_id = getattr(plugin, "plugin_id", None)
    plugin_version = getattr(plugin, "plugin_version", None)
    if not isinstance(plugin_id, str) or not plugin_id:
        return SemanticVerifierValidationResult(
            request_id=request.request_id,
            run_id=server_run_id,
            plugin_id="unknown",
            decision=SemanticVerifierValidationDecision.BLOCKED,
            diagnostics=[
                SemanticVerifierValidationFinding(
                    code="SEMANTIC_VERIFIER_PLUGIN_ID_MISSING",
                    path="plugin.plugin_id",
                    message="A registered semantic plugin must expose a stable plugin_id.",
                    blocker=True,
                )
            ],
        )
    if not isinstance(plugin_version, str) or not plugin_version:
        return SemanticVerifierValidationResult(
            request_id=request.request_id,
            run_id=server_run_id,
            plugin_id=plugin_id,
            decision=SemanticVerifierValidationDecision.BLOCKED,
            diagnostics=[
                SemanticVerifierValidationFinding(
                    code="SEMANTIC_VERIFIER_PLUGIN_VERSION_MISSING",
                    path="plugin.plugin_version",
                    message="A registered semantic plugin must expose a stable plugin_version.",
                    blocker=True,
                )
            ],
        )
    try:
        raw = plugin.verify(request)
        result = (
            raw
            if isinstance(raw, SemanticVerifierResult)
            else SemanticVerifierResult.model_validate(raw)
        )
    except (Exception, ValidationError) as exc:
        return SemanticVerifierValidationResult(
            request_id=request.request_id,
            run_id=server_run_id,
            plugin_id=plugin_id,
            decision=SemanticVerifierValidationDecision.BLOCKED,
            diagnostics=[
                SemanticVerifierValidationFinding(
                    code="SEMANTIC_VERIFIER_PLUGIN_EXECUTION_FAILED",
                    path="plugin.verify",
                    message=f"Plugin execution failed: {type(exc).__name__}",
                    blocker=True,
                )
            ],
        )
    return validate_semantic_verifier_result(
        result,
        request=request,
        server_run_id=server_run_id,
        server_targets=server_targets,
        server_sources=server_sources,
        server_evidence=server_evidence,
        expected_plugin_id=plugin_id,
        expected_plugin_version=plugin_version,
    )


__all__ = [
    "SemanticVerificationOutcome",
    "SemanticVerificationTargetKind",
    "SemanticVerifierFinding",
    "SemanticVerifierPlugin",
    "SemanticVerifierRequest",
    "SemanticVerifierResult",
    "SemanticVerifierRunStatus",
    "SemanticVerifierTarget",
    "SemanticVerifierValidationDecision",
    "SemanticVerifierValidationFinding",
    "SemanticVerifierValidationResult",
    "execute_semantic_verifier",
    "validate_semantic_verifier_result",
]
