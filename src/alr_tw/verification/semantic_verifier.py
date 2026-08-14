"""Fail-closed facade for optional semantic-verifier sidecars."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from alr_tw.contracts.semantic_verifier import (
    SemanticVerifierPlugin,
    SemanticVerifierRequest,
    SemanticVerifierTarget,
    SemanticVerifierValidationResult,
    execute_semantic_verifier,
    validate_semantic_verifier_result,
)
from alr_tw.contracts.sources import EvidenceSpan, SourceRecord


def validate_server_semantic_verifier(
    result: object,
    *,
    request: SemanticVerifierRequest,
    server_run_id: str,
    server_targets: Mapping[str, SemanticVerifierTarget] | Sequence[SemanticVerifierTarget],
    server_sources: Sequence[SourceRecord],
    server_evidence: Sequence[EvidenceSpan],
    expected_plugin_id: str | None = None,
    expected_plugin_version: str | None = None,
) -> SemanticVerifierValidationResult:
    """Validate a plugin result against independent server-owned references."""

    from alr_tw.contracts.semantic_verifier import SemanticVerifierResult

    try:
        parsed = (
            result
            if isinstance(result, SemanticVerifierResult)
            else SemanticVerifierResult.model_validate(result)
        )
    except Exception as exc:
        from alr_tw.contracts.semantic_verifier import (
            SemanticVerifierValidationDecision,
            SemanticVerifierValidationFinding,
        )

        return SemanticVerifierValidationResult(
            request_id=request.request_id,
            run_id=server_run_id,
            plugin_id=expected_plugin_id or "unknown",
            decision=SemanticVerifierValidationDecision.BLOCKED,
            diagnostics=[
                SemanticVerifierValidationFinding(
                    code="SEMANTIC_VERIFIER_RESULT_INVALID",
                    path="result",
                    message=f"Plugin result failed schema validation: {type(exc).__name__}",
                    blocker=True,
                )
            ],
        )
    return validate_semantic_verifier_result(
        parsed,
        request=request,
        server_run_id=server_run_id,
        server_targets=server_targets,
        server_sources=server_sources,
        server_evidence=server_evidence,
        expected_plugin_id=expected_plugin_id,
        expected_plugin_version=expected_plugin_version,
    )


def run_server_semantic_verifier(
    plugin: SemanticVerifierPlugin,
    request: SemanticVerifierRequest,
    *,
    server_run_id: str,
    server_targets: Mapping[str, SemanticVerifierTarget] | Sequence[SemanticVerifierTarget],
    server_sources: Sequence[SourceRecord],
    server_evidence: Sequence[EvidenceSpan],
) -> SemanticVerifierValidationResult:
    """Execute and validate a plugin without granting it runtime authority."""

    return execute_semantic_verifier(
        plugin,
        request,
        server_run_id=server_run_id,
        server_targets=server_targets,
        server_sources=server_sources,
        server_evidence=server_evidence,
    )


__all__ = ["run_server_semantic_verifier", "validate_server_semantic_verifier"]
