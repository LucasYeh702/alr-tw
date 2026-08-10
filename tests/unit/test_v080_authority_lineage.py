from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest
from pydantic import ValidationError

from alr_tw.contracts.authority_lineage import (
    AdjudicativeLevel,
    AuthorityAxes,
    AuthorityLineageContract,
    AuthorityLineageEdge,
    AuthorityLineageNode,
    BoundedAuthorityScope,
    BoundedNotFound,
    CourtLevel,
    LineageCoverageStatus,
    LineageRelation,
    NegativeTreatmentRecord,
    NegativeTreatmentStatus,
    ProceduralPostureAssessment,
    SourceRole,
    validate_authority_lineage,
)
from alr_tw.contracts.civil_analysis import ProceduralStage
from alr_tw.contracts.legal_context import (
    AuthorityLevel,
    AuthorityStatus,
    LegalValidityStatus,
    TemporalApplicabilityStatus,
)
from alr_tw.contracts.sources import MaterialType


def _scope() -> BoundedAuthorityScope:
    return BoundedAuthorityScope(
        provider_ids=["synthetic-authority-provider"],
        material_types=[MaterialType.JUDGMENT],
        court_levels=[CourtLevel.HIGH_COURT],
        query_scope="同一爭點的上訴審級與反面處理範圍",
        time_scope="2000-01-01/2026-08-09",
    )


def _axes() -> AuthorityAxes:
    return AuthorityAxes(
        normative_level=AuthorityLevel.JUDGMENT,
        normative_force=AuthorityStatus.PERSUASIVE,
        institutional_level=CourtLevel.HIGH_COURT,
        adjudicative_level=AdjudicativeLevel.APPEAL,
        procedural_stage=ProceduralStage.APPEAL,
        temporal_applicability=TemporalApplicabilityStatus.APPLICABLE,
        legal_validity=LegalValidityStatus.VALID,
    )


def _node(node_id: str, source_id: str, *, role: SourceRole = SourceRole.JUDGMENT_HOLDING) -> AuthorityLineageNode:
    return AuthorityLineageNode(
        node_id=node_id,
        source_id=source_id,
        material_type=MaterialType.JUDGMENT,
        source_role=role,
        authority_axes=_axes(),
        procedural_posture=ProceduralPostureAssessment(
            stage=ProceduralStage.APPEAL,
            description="合成上訴審程序姿態",
            resolved=True,
            source_ids=[source_id],
            evidence_ids=[f"evidence-{node_id}"],
        ),
        evidence_ids=[f"evidence-{node_id}"],
    )


def _contract(*, nodes: list[AuthorityLineageNode] | None = None, edges=None, **kwargs):
    return AuthorityLineageContract(
        run_id="run-authority",
        coverage_status=LineageCoverageStatus.COMPLETE,
        scope=_scope(),
        nodes=nodes or [_node("judgment-a", "source-a")],
        edges=edges or [],
        **kwargs,
    )


def test_complete_server_bound_lineage_is_structural_only() -> None:
    result = validate_authority_lineage(
        _contract(),
        server_run_id="run-authority",
        server_source_ids=["source-a"],
        server_evidence_ids=["evidence-judgment-a"],
    )

    assert result.valid is True
    assert result.structurally_valid is True
    assert result.eligible_for_authority is True
    assert result.safe_for_citation is False
    assert result.semantic_opposition_performed is False
    assert result.global_consensus_claim_allowed is False


def test_foreign_source_or_evidence_reference_fails_closed() -> None:
    contract = _contract(
        nodes=[
            _node("judgment-a", "foreign-source").model_copy(
                update={
                    "evidence_ids": ["foreign-evidence"],
                    "procedural_posture": ProceduralPostureAssessment(
                        stage=ProceduralStage.APPEAL,
                        description="合成上訴審程序姿態",
                        resolved=True,
                        source_ids=["foreign-source"],
                        evidence_ids=["foreign-evidence"],
                    ),
                }
            )
        ],
    )
    result = validate_authority_lineage(
        contract,
        server_run_id="run-authority",
        server_source_ids=["source-a"],
        server_evidence_ids=["evidence-judgment-a"],
    )

    assert result.valid is False
    assert result.structurally_valid is False
    assert "AUTHORITY_LINEAGE_FOREIGN_SOURCE_ID" in result.blockers
    assert "AUTHORITY_LINEAGE_FOREIGN_EVIDENCE_ID" in result.blockers


def test_run_mismatch_and_duplicate_server_refs_are_blockers() -> None:
    result = validate_authority_lineage(
        _contract(),
        server_run_id="different-run",
        server_source_ids=["source-a", "source-a"],
        server_evidence_ids=["evidence-judgment-a"],
    )

    assert result.valid is False
    assert "AUTHORITY_LINEAGE_RUN_MISMATCH" in result.blockers
    assert "SERVER_SOURCE_IDS_DUPLICATE" in result.blockers


def test_unresolved_axis_or_candidate_role_never_becomes_eligible() -> None:
    unresolved = _node("candidate", "source-a", role=SourceRole.CANDIDATE_ONLY)
    unresolved = unresolved.model_copy(
        update={
            "authority_axes": AuthorityAxes(),
            "procedural_posture": ProceduralPostureAssessment(
                stage=ProceduralStage.UNKNOWN,
                description="尚未確認",
                resolved=False,
            ),
        }
    )
    result = validate_authority_lineage(
        _contract(nodes=[unresolved]),
        server_run_id="run-authority",
        server_source_ids=["source-a"],
        server_evidence_ids=["evidence-candidate"],
    )

    assert result.structurally_valid is True
    assert result.valid is False
    assert result.eligible_for_authority is False
    assert any("SOURCE_ROLE_UNRESOLVED" in item for item in result.qualifications)
    assert any("AXES_UNRESOLVED" in item for item in result.qualifications)


def test_lineage_edges_require_known_nodes_and_are_acyclic() -> None:
    with pytest.raises(ValidationError, match="unknown node"):
        _contract(
            edges=[
                AuthorityLineageEdge(
                    edge_id="edge-a",
                    from_node_id="judgment-a",
                    to_node_id="missing",
                    relation=LineageRelation.APPEAL_FROM,
                    source_ids=["source-a"],
                    evidence_ids=["evidence-judgment-a"],
                )
            ]
        )

    first = _node("first", "source-first")
    second = _node("second", "source-second")
    with pytest.raises(ValidationError, match="acyclic"):
        _contract(
            nodes=[first, second],
            edges=[
                AuthorityLineageEdge(
                    edge_id="edge-forward",
                    from_node_id="first",
                    to_node_id="second",
                    relation=LineageRelation.APPEAL_FROM,
                ),
                AuthorityLineageEdge(
                    edge_id="edge-backward",
                    from_node_id="second",
                    to_node_id="first",
                    relation=LineageRelation.REVIEW_OF,
                ),
            ],
        )


def test_resolved_procedural_posture_must_bind_its_source() -> None:
    node = _node("judgment-a", "source-a").model_copy(
        update={
            "procedural_posture": ProceduralPostureAssessment(
                stage=ProceduralStage.APPEAL,
                description="來源未綁定",
                resolved=True,
                source_ids=["different-source"],
            )
        }
    )
    result = validate_authority_lineage(
        _contract(nodes=[node]),
        server_run_id="run-authority",
        server_source_ids=["source-a", "different-source"],
        server_evidence_ids=["evidence-judgment-a"],
    )
    assert result.valid is False
    assert "AUTHORITY_LINEAGE_POSTURE_SOURCE_UNBOUND" in result.blockers


def test_negative_treatment_is_transport_only_and_never_consensus() -> None:
    treatment = NegativeTreatmentRecord(
        target_node_id="judgment-a",
        status=NegativeTreatmentStatus.FOUND_UNCLASSIFIED,
        treating_node_ids=["treating-node"],
        source_ids=["source-treatment"],
        evidence_ids=["evidence-treatment"],
    )
    treating = _node("treating-node", "source-treatment")
    contract = _contract(nodes=[_node("judgment-a", "source-a"), treating], negative_treatments=[treatment])
    result = validate_authority_lineage(
        contract,
        server_run_id="run-authority",
        server_source_ids=["source-a", "source-treatment"],
        server_evidence_ids=[
            "evidence-judgment-a",
            "evidence-treatment",
            "evidence-treating-node",
        ],
    )

    assert result.structurally_valid is True
    assert result.valid is False
    assert result.semantic_opposition_performed is False
    assert result.global_consensus_claim_allowed is False
    assert "NEGATIVE_TREATMENT_SEMANTIC_CLASSIFICATION_NOT_PERFORMED" in result.qualifications


def test_not_found_in_scope_requires_explicit_bounded_scope_and_cannot_claim_absence() -> None:
    bounded = BoundedNotFound(
        scope=_scope(),
        checked_at=datetime.now(UTC),
        reason_codes=["PROVIDER_EMPTY_RESULT"],
    )
    contract = AuthorityLineageContract(
        run_id="run-authority",
        coverage_status=LineageCoverageStatus.NOT_FOUND_IN_SCOPE,
        scope=_scope(),
        not_found=bounded,
    )
    result = validate_authority_lineage(
        contract,
        server_run_id="run-authority",
        server_source_ids=[],
        server_evidence_ids=[],
    )

    assert result.valid is False
    assert result.structurally_valid is True
    assert result.global_consensus_claim_allowed is False
    assert "AUTHORITY_LINEAGE_NOT_FOUND_IS_BOUNDED_ONLY" in result.qualifications

    with pytest.raises(ValidationError, match="bounded scope"):
        NegativeTreatmentRecord(
            target_node_id="judgment-a",
            status=NegativeTreatmentStatus.NOT_FOUND_IN_SCOPE,
        )


def test_contract_rejects_caller_consensus_flags() -> None:
    with pytest.raises(ValidationError):
        BoundedAuthorityScope(
            provider_ids=["provider"],
            material_types=[MaterialType.JUDGMENT],
            query_scope="bounded",
            consensus_claim_allowed=cast(Any, True),
        )

    with pytest.raises(ValidationError):
        AuthorityLineageContract(
            run_id="run-authority",
            global_consensus_claim_allowed=cast(Any, True),
        )


def test_model_copy_cannot_forge_server_or_semantic_trust_sentinels() -> None:
    forged = _contract().model_copy(
        update={
            "trust_status": "client_attested",
            "semantic_opposition_classified": True,
            "global_consensus_claim_allowed": True,
        }
    )
    result = validate_authority_lineage(
        forged,
        server_run_id="run-authority",
        server_source_ids=["source-a"],
        server_evidence_ids=["evidence-judgment-a"],
    )

    assert result.valid is False
    assert "AUTHORITY_LINEAGE_TRUST_STATUS_INVALID" in result.blockers
    assert "AUTHORITY_LINEAGE_SEMANTIC_CLASSIFIER_FORGED" in result.blockers
    assert "AUTHORITY_LINEAGE_CONSENSUS_GATE_FORGED" in result.blockers
