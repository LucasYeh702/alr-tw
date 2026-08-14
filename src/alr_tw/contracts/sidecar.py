"""Optional semantic-sidecar and deployer-boundary contracts.

The public package exposes registration and boundary validation only. It does
not bundle a model, corpus, prompt, endpoint, credential, or deployment
configuration. A registered sidecar remains advisory and shadow-first.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .semantic_verifier import SemanticVerificationTargetKind


_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"


class SidecarExecutionMode(str, Enum):
    """Permitted execution posture for an optional semantic sidecar."""

    SHADOW = "shadow"
    ADVISORY = "advisory"


class SidecarValidationDecision(str, Enum):
    ACCEPTED = "accepted"
    BLOCKED = "blocked"


class SemanticSidecarRegistration(BaseModel):
    """Capability declaration for a deployer-supplied semantic sidecar."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.semantic-sidecar-registration/v1"] = (
        "alr-tw.semantic-sidecar-registration/v1"
    )
    plugin_id: str = Field(pattern=_ID_PATTERN)
    plugin_version: str = Field(pattern=_ID_PATTERN)
    execution_mode: SidecarExecutionMode = SidecarExecutionMode.SHADOW
    target_kinds: list[SemanticVerificationTargetKind] = Field(min_length=1, max_length=8)
    receives_server_selected_targets_only: Literal[True] = True
    receives_evidence_refs_only: Literal[True] = True
    can_create_evidence: Literal[False] = False
    can_mutate_source_trust: Literal[False] = False
    can_authorize_finalization: Literal[False] = False
    can_emit_presentable_answer: Literal[False] = False
    bundled_model: Literal[False] = False
    bundled_corpus: Literal[False] = False

    @model_validator(mode="after")
    def validate_registration(self) -> SemanticSidecarRegistration:
        if len(self.target_kinds) != len(set(self.target_kinds)):
            raise ValueError("semantic sidecar target_kinds must be unique")
        return self


class SidecarValidationResult(BaseModel):
    """Server-facing structural decision; not a plugin trust grant."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.semantic-sidecar-validation/v1"] = (
        "alr-tw.semantic-sidecar-validation/v1"
    )
    plugin_id: str
    decision: SidecarValidationDecision
    reason_codes: list[str] = Field(default_factory=list, max_length=32)
    semantic_entailment_performed: Literal[False] = False
    authority_owner: Literal["alr-tw.server"] = "alr-tw.server"


def validate_sidecar_registration(
    registration: SemanticSidecarRegistration | Mapping[str, Any],
) -> SidecarValidationResult:
    """Fail closed if a sidecar attempts to cross the server-owned boundary."""

    try:
        parsed = (
            registration
            if isinstance(registration, SemanticSidecarRegistration)
            else SemanticSidecarRegistration.model_validate(registration)
        )
    except ValidationError as exc:
        return SidecarValidationResult(
            plugin_id="unknown",
            decision=SidecarValidationDecision.BLOCKED,
            reason_codes=["SIDECAR_REGISTRATION_SCHEMA_INVALID", type(exc).__name__],
        )
    reasons: list[str] = []
    if parsed.execution_mode not in {
        SidecarExecutionMode.SHADOW,
        SidecarExecutionMode.ADVISORY,
    }:
        reasons.append("SIDECAR_EXECUTION_MODE_UNSUPPORTED")
    if not parsed.receives_server_selected_targets_only:
        reasons.append("SIDECAR_TARGET_SCOPE_NOT_SERVER_SELECTED")
    if not parsed.receives_evidence_refs_only:
        reasons.append("SIDECAR_RAW_EVIDENCE_TRANSFER_FORBIDDEN")
    if parsed.can_create_evidence:
        reasons.append("SIDECAR_EVIDENCE_CREATION_FORBIDDEN")
    if parsed.can_mutate_source_trust:
        reasons.append("SIDECAR_SOURCE_TRUST_MUTATION_FORBIDDEN")
    if parsed.can_authorize_finalization:
        reasons.append("SIDECAR_FINALIZATION_AUTHORIZATION_FORBIDDEN")
    if parsed.can_emit_presentable_answer:
        reasons.append("SIDECAR_PRESENTABLE_ANSWER_FORBIDDEN")
    if parsed.bundled_model:
        reasons.append("SIDECAR_BUNDLED_MODEL_FORBIDDEN")
    if parsed.bundled_corpus:
        reasons.append("SIDECAR_BUNDLED_CORPUS_FORBIDDEN")
    return SidecarValidationResult(
        plugin_id=parsed.plugin_id,
        decision=(
            SidecarValidationDecision.BLOCKED
            if reasons
            else SidecarValidationDecision.ACCEPTED
        ),
        reason_codes=sorted(set(reasons)),
    )


class DeployerProviderDeclaration(BaseModel):
    """Public declaration for a user-supplied data provider.

    The false flags are boundary assertions about package contents, not proof
    that an external deployment is safe or that its data is legally correct.
    Source promotion and snapshot binding remain server-owned at runtime.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.deployer-provider-declaration/v1"] = (
        "alr-tw.deployer-provider-declaration/v1"
    )
    provider_id: str = Field(pattern=_ID_PATTERN)
    material_families: list[str] = Field(min_length=1, max_length=16)
    ownership: Literal["deployer_supplied"] = "deployer_supplied"
    bundled_corpus: Literal[False] = False
    bundled_private_data: Literal[False] = False
    bundled_credentials: Literal[False] = False
    bundled_deployment_parameters: Literal[False] = False
    server_owned_source_promotion_required: Literal[True] = True
    server_owned_snapshot_required: Literal[True] = True

    @model_validator(mode="after")
    def validate_deployer_boundary(self) -> DeployerProviderDeclaration:
        if len(self.material_families) != len(set(self.material_families)):
            raise ValueError("deployer material_families must be unique")
        if any(not item.strip() for item in self.material_families):
            raise ValueError("deployer material_families must not be blank")
        flattened = " ".join(self.material_families).casefold()
        if any(
            marker in flattened
            for marker in ("/users/", "\\users\\", "sqlite://", "postgres://", "bearer ")
        ):
            raise ValueError("deployer material_families must remain deployment-neutral")
        return self


class DeployerBoundaryValidationResult(BaseModel):
    """Boundary validation result; it does not attest to provider data."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.deployer-boundary-validation/v1"] = (
        "alr-tw.deployer-boundary-validation/v1"
    )
    provider_id: str
    decision: SidecarValidationDecision
    reason_codes: list[str] = Field(default_factory=list, max_length=32)
    data_correctness_attested: Literal[False] = False


def validate_deployer_provider_declaration(
    declaration: DeployerProviderDeclaration | Mapping[str, Any],
) -> DeployerBoundaryValidationResult:
    """Reject forged/publicly unsafe declaration flags fail-closed."""

    try:
        parsed = (
            declaration
            if isinstance(declaration, DeployerProviderDeclaration)
            else DeployerProviderDeclaration.model_validate(declaration)
        )
    except ValidationError as exc:
        return DeployerBoundaryValidationResult(
            provider_id="unknown",
            decision=SidecarValidationDecision.BLOCKED,
            reason_codes=["DEPLOYER_BOUNDARY_SCHEMA_INVALID", type(exc).__name__],
        )
    reasons: list[str] = []
    if parsed.ownership != "deployer_supplied":
        reasons.append("DEPLOYER_OWNERSHIP_UNSUPPORTED")
    if parsed.bundled_corpus:
        reasons.append("DEPLOYER_BUNDLED_CORPUS_FORBIDDEN")
    if parsed.bundled_private_data:
        reasons.append("DEPLOYER_PRIVATE_DATA_FORBIDDEN")
    if parsed.bundled_credentials:
        reasons.append("DEPLOYER_CREDENTIALS_FORBIDDEN")
    if parsed.bundled_deployment_parameters:
        reasons.append("DEPLOYER_DEPLOYMENT_PARAMETERS_FORBIDDEN")
    if not parsed.server_owned_source_promotion_required:
        reasons.append("DEPLOYER_SOURCE_PROMOTION_SERVER_GATE_REQUIRED")
    if not parsed.server_owned_snapshot_required:
        reasons.append("DEPLOYER_SNAPSHOT_SERVER_GATE_REQUIRED")
    return DeployerBoundaryValidationResult(
        provider_id=parsed.provider_id,
        decision=(
            SidecarValidationDecision.BLOCKED
            if reasons
            else SidecarValidationDecision.ACCEPTED
        ),
        reason_codes=sorted(set(reasons)),
    )


__all__ = [
    "DeployerBoundaryValidationResult",
    "DeployerProviderDeclaration",
    "SemanticSidecarRegistration",
    "SidecarExecutionMode",
    "SidecarValidationDecision",
    "SidecarValidationResult",
    "validate_deployer_provider_declaration",
    "validate_sidecar_registration",
]
