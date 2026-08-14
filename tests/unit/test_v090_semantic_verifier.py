from datetime import UTC, datetime, timedelta
from typing import cast

from alr_tw.contracts.semantic_verifier import (
    SemanticVerificationOutcome,
    SemanticVerificationTargetKind,
    SemanticVerifierRequest,
    SemanticVerifierFinding,
    SemanticVerifierPlugin,
    SemanticVerifierResult,
    SemanticVerifierRunStatus,
    SemanticVerifierTarget,
    execute_semantic_verifier,
    validate_semantic_verifier_result,
)
from alr_tw.contracts.sources import EvidenceSpan, MaterialType, SourceRecord, SourceTier, TrustStatus
from alr_tw.verification.semantic_verifier import validate_server_semantic_verifier


NOW = datetime.now(UTC)


def _source(*, source_id: str = "source-1", expires_at: datetime | None = None) -> SourceRecord:
    text = "合成官方法規內容。"
    digest = EvidenceSpan.hash_text(text)
    return SourceRecord(
        source_id=source_id,
        source_key=f"law:{source_id}",
        source_version_id=f"{source_id}:v1",
        material_type=MaterialType.LAW,
        provider_id="official-law",
        source_tier=SourceTier.OFFICIAL,
        trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
        official_identifier=f"LAW-{source_id}",
        official_url="https://example.test/law",
        citation="合成法規",
        title="合成法規",
        fetched_at=NOW - timedelta(minutes=1),
        verified_at=NOW - timedelta(minutes=1),
        expires_at=expires_at or NOW + timedelta(hours=1),
        content_hash=digest,
        normalized_content_hash=digest,
        normalized_text=text,
    )


def _evidence(*, evidence_id: str = "evidence-1", source_id: str = "source-1") -> EvidenceSpan:
    return EvidenceSpan.from_exact_text(
        evidence_id=evidence_id,
        source_id=source_id,
        section_id="section-1",
        section_type="law_text",
        exact_text="合成官方法規內容。",
        eligible_for_claim_support=True,
    )


def _request() -> SemanticVerifierRequest:
    return SemanticVerifierRequest(
        request_id="semantic-request-1",
        run_id="run-1",
        scope="bounded synthetic semantic check",
        targets=[
            SemanticVerifierTarget(
                target_id="element-1",
                target_kind=SemanticVerificationTargetKind.ELEMENT,
                proposition="被告應負損害賠償責任",
                source_ids=["source-1"],
                evidence_ids=["evidence-1"],
            )
        ],
    )


def _result(*, outcome: SemanticVerificationOutcome = SemanticVerificationOutcome.SUPPORTS) -> SemanticVerifierResult:
    return SemanticVerifierResult(
        request_id="semantic-request-1",
        run_id="run-1",
        plugin_id="plugin-demo",
        plugin_version="1.0.0",
        status=SemanticVerifierRunStatus.COMPLETED,
        findings=[
            SemanticVerifierFinding(
                target_id="element-1",
                outcome=outcome,
                confidence=0.8 if outcome is SemanticVerificationOutcome.SUPPORTS else None,
                referenced_source_ids=["source-1"],
                referenced_evidence_ids=["evidence-1"],
            )
        ],
    )


def test_valid_plugin_result_is_advisory_only() -> None:
    result = validate_semantic_verifier_result(
        _result(),
        request=_request(),
        server_run_id="run-1",
        server_targets=_request().targets,
        server_sources=[_source()],
        server_evidence=[_evidence()],
        expected_plugin_id="plugin-demo",
    )
    assert result.decision.value == "accepted"
    assert result.findings[0].outcome is SemanticVerificationOutcome.SUPPORTS
    assert result.safe_for_finalization is False
    assert result.authorizes_final_answer is False
    assert result.can_promote_evidence is False
    assert result.can_mutate_source_trust is False


def test_uncertain_and_not_evaluated_are_retained_without_authority() -> None:
    uncertain = _result(outcome=SemanticVerificationOutcome.UNCERTAIN)
    uncertain_result = validate_semantic_verifier_result(
        uncertain,
        request=_request(),
        server_run_id="run-1",
        server_targets=_request().targets,
        server_sources=[_source()],
        server_evidence=[_evidence()],
        expected_plugin_id="plugin-demo",
    )
    assert uncertain_result.decision.value == "accepted"

    not_evaluated = _result(outcome=SemanticVerificationOutcome.NOT_EVALUATED).model_copy(
        update={"status": SemanticVerifierRunStatus.NOT_EVALUATED}
    )
    not_evaluated_result = validate_semantic_verifier_result(
        not_evaluated,
        request=_request(),
        server_run_id="run-1",
        server_targets=_request().targets,
        server_sources=[_source()],
        server_evidence=[_evidence()],
        expected_plugin_id="plugin-demo",
    )
    assert not_evaluated_result.decision.value == "partial"


def test_foreign_target_and_evidence_are_blocked() -> None:
    foreign = _result().model_copy(
        update={
            "findings": [
                SemanticVerifierFinding(
                    target_id="foreign-element",
                    outcome=SemanticVerificationOutcome.SUPPORTS,
                    confidence=0.8,
                    referenced_source_ids=["source-foreign"],
                    referenced_evidence_ids=["evidence-foreign"],
                )
            ]
        }
    )
    result = validate_semantic_verifier_result(
        foreign,
        request=_request(),
        server_run_id="run-1",
        server_targets=_request().targets,
        server_sources=[_source()],
        server_evidence=[_evidence()],
        expected_plugin_id="plugin-demo",
    )
    assert result.decision.value == "blocked"
    assert any(item.code == "SEMANTIC_VERIFIER_TARGET_NOT_SERVER_OWNED" for item in result.diagnostics)


def test_finding_references_must_stay_inside_target_scope() -> None:
    result = validate_semantic_verifier_result(
        _result().model_copy(
            update={
                "findings": [
                    SemanticVerifierFinding(
                        target_id="element-1",
                        outcome=SemanticVerificationOutcome.SUPPORTS,
                        confidence=0.8,
                        referenced_source_ids=["source-2"],
                        referenced_evidence_ids=["evidence-2"],
                    )
                ]
            }
        ),
        request=_request(),
        server_run_id="run-1",
        server_targets=_request().targets,
        server_sources=[_source(), _source(source_id="source-2")],
        server_evidence=[_evidence(), _evidence(evidence_id="evidence-2", source_id="source-2")],
        expected_plugin_id="plugin-demo",
    )
    assert result.decision.value == "blocked"
    assert any(
        item.code == "SEMANTIC_VERIFIER_SOURCE_OUTSIDE_TARGET_SCOPE"
        for item in result.diagnostics
    )
    assert any(
        item.code == "SEMANTIC_VERIFIER_EVIDENCE_OUTSIDE_TARGET_SCOPE"
        for item in result.diagnostics
    )


def test_expired_source_is_not_accepted_as_semantic_support() -> None:
    result = validate_semantic_verifier_result(
        _result(),
        request=_request(),
        server_run_id="run-1",
        server_targets=_request().targets,
        server_sources=[_source(expires_at=NOW - timedelta(seconds=1))],
        server_evidence=[_evidence()],
        expected_plugin_id="plugin-demo",
    )
    assert result.decision.value == "blocked"
    assert any(item.code == "SEMANTIC_VERIFIER_SOURCE_NOT_ELIGIBLE" for item in result.diagnostics)


def test_model_copy_cannot_authorize_finalization_or_evidence() -> None:
    forged = _result().model_copy(
        update={
            "finalization_authorized": True,
            "evidence_promotion_allowed": True,
            "source_trust_mutation_allowed": True,
            "advisory_only": False,
        }
    )
    result = validate_semantic_verifier_result(
        forged,
        request=_request(),
        server_run_id="run-1",
        server_targets=_request().targets,
        server_sources=[_source()],
        server_evidence=[_evidence()],
        expected_plugin_id="plugin-demo",
    )
    assert result.decision.value == "blocked"
    assert any(item.code == "SEMANTIC_VERIFIER_AUTHORITY_SENTINEL_FORGED" for item in result.diagnostics)


def test_plugin_reported_failure_is_blocked() -> None:
    result = validate_semantic_verifier_result(
        _result().model_copy(update={"status": SemanticVerifierRunStatus.FAILED}),
        request=_request(),
        server_run_id="run-1",
        server_targets=_request().targets,
        server_sources=[_source()],
        server_evidence=[_evidence()],
        expected_plugin_id="plugin-demo",
    )
    assert result.decision.value == "blocked"
    assert any(item.code == "SEMANTIC_VERIFIER_RUN_FAILED" for item in result.diagnostics)


def test_blocked_result_discards_all_advisory_findings() -> None:
    result = validate_semantic_verifier_result(
        _result().model_copy(update={"run_id": "forged-run"}),
        request=_request(),
        server_run_id="run-1",
        server_targets=_request().targets,
        server_sources=[_source()],
        server_evidence=[_evidence()],
        expected_plugin_id="plugin-demo",
    )
    assert result.decision.value == "blocked"
    assert result.findings == []


def test_completed_result_with_missing_targets_is_partial() -> None:
    request = _request().model_copy(
        update={
            "targets": [
                _request().targets[0],
                SemanticVerifierTarget(
                    target_id="element-2",
                    target_kind=SemanticVerificationTargetKind.ELEMENT,
                    proposition="第二項構成要件",
                    source_ids=["source-1"],
                    evidence_ids=["evidence-1"],
                ),
            ]
        }
    )
    result = validate_semantic_verifier_result(
        _result(),
        request=request,
        server_run_id="run-1",
        server_targets=request.targets,
        server_sources=[_source()],
        server_evidence=[_evidence()],
        expected_plugin_id="plugin-demo",
    )
    assert result.decision.value == "partial"
    assert any(
        item.code == "SEMANTIC_VERIFIER_TARGET_COVERAGE_PARTIAL"
        for item in result.diagnostics
    )


def test_facade_enforces_plugin_version_binding() -> None:
    result = validate_server_semantic_verifier(
        _result(),
        request=_request(),
        server_run_id="run-1",
        server_targets=_request().targets,
        server_sources=[_source()],
        server_evidence=[_evidence()],
        expected_plugin_id="plugin-demo",
        expected_plugin_version="2.0.0",
    )
    assert result.decision.value == "blocked"
    assert any(
        item.code == "SEMANTIC_VERIFIER_PLUGIN_VERSION_MISMATCH"
        for item in result.diagnostics
    )


def test_supporting_finding_requires_a_server_reference() -> None:
    result = validate_semantic_verifier_result(
        SemanticVerifierResult(
            request_id="semantic-request-1",
            run_id="run-1",
            plugin_id="plugin-demo",
            plugin_version="1.0.0",
            status=SemanticVerifierRunStatus.COMPLETED,
            findings=[
                SemanticVerifierFinding(
                    target_id="element-1",
                    outcome=SemanticVerificationOutcome.SUPPORTS,
                    confidence=0.8,
                )
            ],
        ),
        request=_request(),
        server_run_id="run-1",
        server_targets=_request().targets,
        server_sources=[_source()],
        server_evidence=[_evidence()],
        expected_plugin_id="plugin-demo",
    )
    assert result.decision.value == "blocked"
    assert any(
        item.code == "SEMANTIC_VERIFIER_SUPPORT_REFERENCE_REQUIRED"
        for item in result.diagnostics
    )


def test_contradicting_finding_has_the_same_reference_gate() -> None:
    result = validate_semantic_verifier_result(
        SemanticVerifierResult(
            request_id="semantic-request-1",
            run_id="run-1",
            plugin_id="plugin-demo",
            plugin_version="1.0.0",
            status=SemanticVerifierRunStatus.COMPLETED,
            findings=[
                SemanticVerifierFinding(
                    target_id="element-1",
                    outcome=SemanticVerificationOutcome.CONTRADICTS,
                    confidence=0.8,
                )
            ],
        ),
        request=_request(),
        server_run_id="run-1",
        server_targets=_request().targets,
        server_sources=[_source()],
        server_evidence=[_evidence()],
        expected_plugin_id="plugin-demo",
    )
    assert result.decision.value == "blocked"
    assert any(
        item.code == "SEMANTIC_VERIFIER_SUPPORT_REFERENCE_REQUIRED"
        for item in result.diagnostics
    )


class _Plugin:
    plugin_id = "plugin-demo"
    plugin_version = "1.0.0"

    def verify(self, request: SemanticVerifierRequest) -> SemanticVerifierResult:
        assert request.run_id == "run-1"
        return _result()


class _FailingPlugin(_Plugin):
    def verify(self, request: SemanticVerifierRequest) -> SemanticVerifierResult:
        raise RuntimeError("provider unavailable")


class _PluginWithoutIdentity:
    def verify(self, request: SemanticVerifierRequest) -> SemanticVerifierResult:
        return _result()


class _PluginWithoutVersion:
    plugin_id = "plugin-demo"

    def verify(self, request: SemanticVerifierRequest) -> SemanticVerifierResult:
        return _result()


def test_execution_boundary_blocks_plugin_exception() -> None:
    result = execute_semantic_verifier(
        _FailingPlugin(),
        _request(),
        server_run_id="run-1",
        server_targets=_request().targets,
        server_sources=[_source()],
        server_evidence=[_evidence()],
    )
    assert result.decision.value == "blocked"
    assert result.diagnostics[0].code == "SEMANTIC_VERIFIER_PLUGIN_EXECUTION_FAILED"


def test_execution_boundary_requires_registered_plugin_identity() -> None:
    result = execute_semantic_verifier(
        cast(SemanticVerifierPlugin, _PluginWithoutIdentity()),
        _request(),
        server_run_id="run-1",
        server_targets=_request().targets,
        server_sources=[_source()],
        server_evidence=[_evidence()],
    )
    assert result.decision.value == "blocked"
    assert result.diagnostics[0].code == "SEMANTIC_VERIFIER_PLUGIN_ID_MISSING"


def test_execution_boundary_requires_registered_plugin_version() -> None:
    result = execute_semantic_verifier(
        cast(SemanticVerifierPlugin, _PluginWithoutVersion()),
        _request(),
        server_run_id="run-1",
        server_targets=_request().targets,
        server_sources=[_source()],
        server_evidence=[_evidence()],
    )
    assert result.decision.value == "blocked"
    assert result.diagnostics[0].code == "SEMANTIC_VERIFIER_PLUGIN_VERSION_MISSING"


def test_facade_invalid_payload_is_blocked() -> None:
    result = validate_server_semantic_verifier(
        None,
        request=_request(),
        server_run_id="run-1",
        server_targets=_request().targets,
        server_sources=[_source()],
        server_evidence=[_evidence()],
        expected_plugin_id="plugin-demo",
    )
    assert result.decision.value == "blocked"
    assert result.diagnostics[0].code == "SEMANTIC_VERIFIER_RESULT_INVALID"


def test_forged_request_trust_status_is_not_server_owned() -> None:
    request = _request().model_copy(update={"trust_status": "untrusted_client_proposal"})
    result = validate_semantic_verifier_result(
        _result(),
        request=request,
        server_run_id="run-1",
        server_targets=_request().targets,
        server_sources=[_source()],
        server_evidence=[_evidence()],
        expected_plugin_id="plugin-demo",
    )
    assert result.decision.value == "blocked"
    assert any(item.code == "SEMANTIC_VERIFIER_REQUEST_NOT_SERVER_OWNED" for item in result.diagnostics)
