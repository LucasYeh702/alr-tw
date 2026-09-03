"""Build a bounded, server-bound judgment-lineage inspection result."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Sequence

from alr_tw.contracts.authority_lineage import (
    AdjudicativeLevel,
    AuthorityAxes,
    AuthorityLineageContract,
    AuthorityLineageEdge,
    AuthorityLineageNode,
    BoundedAuthorityScope,
    CourtLevel,
    LineageCoverageStatus,
    LineageRelation,
    NegativeTreatmentRecord,
    NegativeTreatmentStatus,
    ProceduralPostureAssessment,
    SourceRole,
)
from alr_tw.contracts.civil_analysis import ProceduralStage
from alr_tw.contracts.judgment_semantics import (
    JudgmentDisposition,
    classify_disposition_text,
)
from alr_tw.contracts.legal_context import AuthorityLevel
from alr_tw.contracts.sources import (
    EvidenceSectionType,
    EvidenceSpan,
    MaterialType,
    SourceRecord,
)
from alr_tw.providers.tlr import TlrCaseHistoryEntry, TlrCaseHistoryRecord
from alr_tw.verification.authority_lineage import validate_server_authority_lineage


_VACATED_DISPOSITIONS = {
    JudgmentDisposition.VACATED_REMANDED.value,
    JudgmentDisposition.VACATED_REVERSED.value,
}
_COURT_VIEW_SECTIONS = {
    EvidenceSectionType.HOLDING,
    EvidenceSectionType.COURT_HOLDING,
    EvidenceSectionType.COURT_REASONING,
}


@dataclass(frozen=True)
class VerifiedLineageSource:
    history: TlrCaseHistoryEntry
    source: SourceRecord
    evidence: tuple[EvidenceSpan, ...]


def disposition_codes(
    source: SourceRecord,
    evidence: Sequence[EvidenceSpan],
) -> list[str]:
    """Return bounded disposition codes from official source metadata/spans."""

    disposition_evidence = [
        item
        for item in evidence
        if item.section_type is EvidenceSectionType.DISPOSITION and item.eligible_for_claim_support
    ]
    if not disposition_evidence:
        return [JudgmentDisposition.UNKNOWN.value]

    values: list[str] = []
    raw_codes = source.metadata.get("disposition_codes")
    if isinstance(raw_codes, list):
        for raw in raw_codes:
            try:
                code = JudgmentDisposition(str(raw)).value
            except ValueError:
                continue
            if code not in values:
                values.append(code)
    for item in disposition_evidence:
        for code in classify_disposition_text(item.exact_text):
            if code.value not in values:
                values.append(code.value)
    if len(values) > 1 and JudgmentDisposition.UNKNOWN.value in values:
        values.remove(JudgmentDisposition.UNKNOWN.value)
    return values or [JudgmentDisposition.UNKNOWN.value]


def evidence_summary(evidence: Sequence[EvidenceSpan]) -> dict[str, list[str]]:
    return {
        "all_evidence_ids": sorted(item.evidence_id for item in evidence),
        "disposition_evidence_ids": sorted(
            item.evidence_id
            for item in evidence
            if item.section_type is EvidenceSectionType.DISPOSITION
            and item.eligible_for_claim_support
        ),
        "court_view_evidence_ids": sorted(
            item.evidence_id
            for item in evidence
            if item.section_type in _COURT_VIEW_SECTIONS and item.eligible_for_claim_support
        ),
    }


def verified_node_payload(
    history: TlrCaseHistoryEntry,
    source: SourceRecord,
    evidence: Sequence[EvidenceSpan],
) -> dict[str, Any]:
    summary = evidence_summary(evidence)
    return {
        "direction": history.direction,
        "provider_history": history.model_dump(mode="json"),
        "official_verification_status": "verified",
        "source_id": source.source_id,
        "official_identifier": source.official_identifier,
        "citation": source.citation,
        "official_url": source.official_url,
        "disposition_codes": disposition_codes(source, evidence),
        **summary,
    }


def build_lineage_contract(
    *,
    run_id: str,
    root_source: SourceRecord,
    root_evidence: Sequence[EvidenceSpan],
    history: TlrCaseHistoryRecord,
    related: Sequence[VerifiedLineageSource],
    max_related_nodes: int,
) -> tuple[AuthorityLineageContract, dict[str, Any]]:
    """Map verified nodes into the existing structural lineage contract."""

    root_node_id = _node_id(root_source.official_identifier or root_source.source_id)
    nodes = [
        _authority_node(
            node_id=root_node_id,
            source=root_source,
            evidence=root_evidence,
            direction="root",
        )
    ]
    edges: list[AuthorityLineageEdge] = []
    related_by_node_id: dict[str, VerifiedLineageSource] = {}
    for item in related:
        identifier = item.source.official_identifier or item.history.provider_document_id
        node_id = _node_id(identifier)
        related_by_node_id[node_id] = item
        nodes.append(
            _authority_node(
                node_id=node_id,
                source=item.source,
                evidence=item.evidence,
                direction=item.history.direction,
            )
        )
        if item.history.direction == "upper":
            from_node_id, to_node_id = node_id, root_node_id
        else:
            from_node_id, to_node_id = root_node_id, node_id
        edges.append(
            AuthorityLineageEdge(
                edge_id=_edge_id(from_node_id, to_node_id),
                from_node_id=from_node_id,
                to_node_id=to_node_id,
                relation=LineageRelation.REVIEW_OF,
                source_ids=sorted({root_source.source_id, item.source.source_id}),
            )
        )

    negative_treatments: list[NegativeTreatmentRecord] = []
    confirmed_reversing_nodes: list[str] = []
    for node_id, item in related_by_node_id.items():
        if item.history.direction != "upper" or not item.history.vacated_marker:
            continue
        codes = set(disposition_codes(item.source, item.evidence))
        has_disposition_evidence = any(
            evidence.section_type is EvidenceSectionType.DISPOSITION
            and evidence.eligible_for_claim_support
            for evidence in item.evidence
        )
        if not has_disposition_evidence or not codes.intersection(_VACATED_DISPOSITIONS):
            continue
        confirmed_reversing_nodes.append(node_id)
    if confirmed_reversing_nodes:
        treating_sources = [
            related_by_node_id[node_id].source for node_id in confirmed_reversing_nodes
        ]
        treating_evidence = [
            evidence
            for node_id in confirmed_reversing_nodes
            for evidence in related_by_node_id[node_id].evidence
            if evidence.section_type is EvidenceSectionType.DISPOSITION
            and evidence.eligible_for_claim_support
        ]
        negative_treatments.append(
            NegativeTreatmentRecord(
                target_node_id=root_node_id,
                status=NegativeTreatmentStatus.REVERSED,
                treating_node_ids=confirmed_reversing_nodes,
                source_ids=sorted(source.source_id for source in treating_sources),
                evidence_ids=sorted(item.evidence_id for item in treating_evidence),
                reason_codes=[
                    "TLR_UPPER_VACATED_MARKER",
                    "OFFICIAL_UPPER_DISPOSITION_CONFIRMED",
                ],
            )
        )

    provider_ids = sorted(
        {
            "tlr_semantic_recall",
            root_source.provider_id,
            *(item.source.provider_id for item in related),
        }
    )
    limitations = [
        "TLR_CASE_HISTORY_DATABASE_RECORDED_ONLY",
        "NO_UPPER_HISTORY_DOES_NOT_ESTABLISH_FINALITY",
        "TLR_CASE_HISTORY_RELATION_GRANULARITY_BOUNDED",
        "SEMANTIC_OPINION_COMPARISON_NOT_PERFORMED",
    ]
    if not history.history_present:
        limitations.append("TLR_CASE_HISTORY_FIELD_MISSING")
    contract = AuthorityLineageContract(
        run_id=run_id,
        coverage_status=LineageCoverageStatus.PARTIAL,
        scope=BoundedAuthorityScope(
            provider_ids=provider_ids,
            material_types=[MaterialType.JUDGMENT],
            query_scope=(
                "TLR database-recorded upper/lower instances for one server-owned "
                f"judgment; at most {max_related_nodes} related nodes officially verified"
            ),
            max_results=max_related_nodes + 1,
        ),
        nodes=nodes,
        edges=edges,
        negative_treatments=negative_treatments,
        limitations=limitations,
    )
    validation = validate_server_authority_lineage(
        contract,
        server_run_id=run_id,
        server_source_ids=[root_source.source_id, *(item.source.source_id for item in related)],
        server_evidence_ids=[
            *(item.evidence_id for item in root_evidence),
            *(evidence.evidence_id for item in related for evidence in item.evidence),
        ],
    )
    return contract, validation.model_dump(mode="json")


def _authority_node(
    *,
    node_id: str,
    source: SourceRecord,
    evidence: Sequence[EvidenceSpan],
    direction: str,
) -> AuthorityLineageNode:
    court_level = _court_level(source.citation)
    is_upper = direction == "upper"
    stage = ProceduralStage.APPEAL if is_upper else ProceduralStage.UNKNOWN
    adjudicative_level = AdjudicativeLevel.APPEAL if is_upper else AdjudicativeLevel.UNKNOWN
    has_court_view = any(
        item.section_type in {*_COURT_VIEW_SECTIONS, EvidenceSectionType.DISPOSITION}
        and item.eligible_for_claim_support
        for item in evidence
    )
    return AuthorityLineageNode(
        node_id=node_id,
        source_id=source.source_id,
        material_type=MaterialType.JUDGMENT,
        source_role=(
            SourceRole.JUDGMENT_HOLDING if has_court_view else SourceRole.JUDGMENT_PROCEDURE
        ),
        authority_axes=AuthorityAxes(
            normative_level=AuthorityLevel.JUDGMENT,
            institutional_level=court_level,
            adjudicative_level=adjudicative_level,
            procedural_stage=stage,
            rationale_codes=[
                "SERVER_OWNED_OFFICIAL_JUDGMENT",
                f"TLR_HISTORY_DIRECTION_{direction.upper()}",
            ],
        ),
        procedural_posture=ProceduralPostureAssessment(
            stage=stage,
            description=(
                "TLR reports this decision as an upper instance of the root judgment."
                if is_upper
                else "The exact procedural stage is not resolved from TLR history metadata alone."
            ),
            resolved=is_upper,
            source_ids=[source.source_id] if is_upper else [],
        ),
        evidence_ids=sorted(item.evidence_id for item in evidence),
        label=source.citation,
    )


def _court_level(citation: str) -> CourtLevel:
    compact = citation.replace(" ", "").replace("臺", "台")
    if "憲法法庭" in compact:
        return CourtLevel.CONSTITUTIONAL_COURT
    if "最高行政法院" in compact:
        return CourtLevel.ADMINISTRATIVE_SUPREME_COURT
    if "高等行政法院" in compact:
        return CourtLevel.ADMINISTRATIVE_HIGH_COURT
    if "最高法院" in compact:
        return CourtLevel.SUPREME_COURT
    if "高等法院" in compact or "智慧財產及商業法院" in compact:
        return CourtLevel.HIGH_COURT
    if "地方法院" in compact:
        return CourtLevel.DISTRICT_COURT
    return CourtLevel.UNKNOWN


def _node_id(identifier: str) -> str:
    return f"lineage_node_{hashlib.sha256(identifier.encode('utf-8')).hexdigest()[:20]}"


def _edge_id(from_node_id: str, to_node_id: str) -> str:
    value = f"{from_node_id}\x00{to_node_id}"
    return f"lineage_edge_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:20]}"


__all__ = [
    "VerifiedLineageSource",
    "build_lineage_contract",
    "disposition_codes",
    "evidence_summary",
    "verified_node_payload",
]
