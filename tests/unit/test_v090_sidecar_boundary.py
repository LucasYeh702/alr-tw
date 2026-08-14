from __future__ import annotations

from typing import Any, cast

from alr_tw.contracts.semantic_verifier import SemanticVerificationTargetKind
from alr_tw.contracts.sidecar import (
    DeployerProviderDeclaration,
    SemanticSidecarRegistration,
    SidecarExecutionMode,
    SidecarValidationDecision,
    validate_deployer_provider_declaration,
    validate_sidecar_registration,
)


def _registration(**updates: Any) -> SemanticSidecarRegistration:
    values: dict[str, Any] = {
        "plugin_id": "semantic-sidecar",
        "plugin_version": "1.0.0",
        "execution_mode": SidecarExecutionMode.SHADOW,
        "target_kinds": [
            SemanticVerificationTargetKind.CLAIM,
            SemanticVerificationTargetKind.JUDGMENT_DISPOSITION,
        ],
    }
    values.update(updates)
    return SemanticSidecarRegistration(**values)


def _declaration(**updates: Any) -> DeployerProviderDeclaration:
    values: dict[str, Any] = {
        "provider_id": "deployer-provider",
        "material_families": ["law", "judgment"],
    }
    values.update(updates)
    return DeployerProviderDeclaration(**values)


def test_shadow_registration_is_accepted_but_not_authoritative() -> None:
    decision = validate_sidecar_registration(_registration())
    assert decision.decision is SidecarValidationDecision.ACCEPTED
    assert decision.authority_owner == "alr-tw.server"
    assert decision.semantic_entailment_performed is False


def test_advisory_registration_is_still_allowed_only_as_sidecar() -> None:
    decision = validate_sidecar_registration(
        _registration(execution_mode=SidecarExecutionMode.ADVISORY)
    )
    assert decision.decision is SidecarValidationDecision.ACCEPTED


def test_sidecar_model_copy_forged_authority_flags_is_blocked() -> None:
    forged = _registration().model_copy(
        update={
            "can_create_evidence": cast(Any, True),
            "can_mutate_source_trust": cast(Any, True),
            "can_authorize_finalization": cast(Any, True),
            "can_emit_presentable_answer": cast(Any, True),
            "bundled_model": cast(Any, True),
            "bundled_corpus": cast(Any, True),
        }
    )
    decision = validate_sidecar_registration(forged)
    assert decision.decision is SidecarValidationDecision.BLOCKED
    assert "SIDECAR_EVIDENCE_CREATION_FORBIDDEN" in decision.reason_codes
    assert "SIDECAR_FINALIZATION_AUTHORIZATION_FORBIDDEN" in decision.reason_codes
    assert "SIDECAR_BUNDLED_CORPUS_FORBIDDEN" in decision.reason_codes


def test_sidecar_registration_requires_server_selected_targets_and_refs() -> None:
    forged = _registration().model_copy(
        update={
            "receives_server_selected_targets_only": cast(Any, False),
            "receives_evidence_refs_only": cast(Any, False),
        }
    )
    decision = validate_sidecar_registration(forged)
    assert decision.decision is SidecarValidationDecision.BLOCKED
    assert "SIDECAR_TARGET_SCOPE_NOT_SERVER_SELECTED" in decision.reason_codes
    assert "SIDECAR_RAW_EVIDENCE_TRANSFER_FORBIDDEN" in decision.reason_codes


def test_malformed_sidecar_payload_is_blocked() -> None:
    decision = validate_sidecar_registration(
        {"plugin_id": "bad plugin", "plugin_version": "1", "target_kinds": []}
    )
    assert decision.decision is SidecarValidationDecision.BLOCKED
    assert "SIDECAR_REGISTRATION_SCHEMA_INVALID" in decision.reason_codes


def test_clean_deployer_declaration_is_accepted_without_data_attestation() -> None:
    decision = validate_deployer_provider_declaration(_declaration())
    assert decision.decision is SidecarValidationDecision.ACCEPTED
    assert decision.data_correctness_attested is False


def test_deployer_declaration_model_copy_forged_bundle_flags_is_blocked() -> None:
    forged = _declaration().model_copy(
        update={
            "bundled_corpus": cast(Any, True),
            "bundled_private_data": cast(Any, True),
            "bundled_credentials": cast(Any, True),
            "bundled_deployment_parameters": cast(Any, True),
        }
    )
    decision = validate_deployer_provider_declaration(forged)
    assert decision.decision is SidecarValidationDecision.BLOCKED
    assert "DEPLOYER_BUNDLED_CORPUS_FORBIDDEN" in decision.reason_codes
    assert "DEPLOYER_CREDENTIALS_FORBIDDEN" in decision.reason_codes


def test_deployer_declaration_requires_server_source_and_snapshot_gates() -> None:
    forged = _declaration().model_copy(
        update={
            "server_owned_source_promotion_required": cast(Any, False),
            "server_owned_snapshot_required": cast(Any, False),
        }
    )
    decision = validate_deployer_provider_declaration(forged)
    assert decision.decision is SidecarValidationDecision.BLOCKED
    assert "DEPLOYER_SOURCE_PROMOTION_SERVER_GATE_REQUIRED" in decision.reason_codes
    assert "DEPLOYER_SNAPSHOT_SERVER_GATE_REQUIRED" in decision.reason_codes


def test_deployer_declaration_rejects_duplicate_or_blank_material_families() -> None:
    duplicate = validate_deployer_provider_declaration(
        {"provider_id": "deployer-provider", "material_families": ["law", "law"]}
    )
    assert duplicate.decision is SidecarValidationDecision.BLOCKED
    blank = validate_deployer_provider_declaration(
        {"provider_id": "deployer-provider", "material_families": [" "]}
    )
    assert blank.decision is SidecarValidationDecision.BLOCKED


def test_deployer_declaration_rejects_private_deployment_marker() -> None:
    decision = validate_deployer_provider_declaration(
        {"provider_id": "deployer-provider", "material_families": ["sqlite:///private"]}
    )
    assert decision.decision is SidecarValidationDecision.BLOCKED
