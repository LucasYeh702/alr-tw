from __future__ import annotations

from enum import Enum
from typing import Any

from .source_policy import (
    DEFAULT_SOURCE_POLICY_CONFIG,
    CitationUse,
    SourcePolicyConfig,
    SourceRecord,
    coerce_identifier_resolution,
    coerce_source_tier,
    evaluate_citation_use,
)


class CitationStatus(str, Enum):
    EXISTS = "exists"
    NOT_FOUND = "not_found"
    UNVERIFIABLE = "unverifiable"


class CitationSupport(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    NOT_CHECKED = "not_checked"


class CitationEligibility(str, Enum):
    FINAL_ELIGIBLE = "final_eligible"
    CANDIDATE_ONLY = "candidate_only"
    DEMO_ONLY = "demo_only"
    REJECTED = "rejected"
    MISSING = "missing"


def _source_from_mapping(citation: dict[str, Any]) -> SourceRecord:
    return SourceRecord(
        source_id=str(citation.get("source_id") or citation.get("citation_id") or ""),
        source_tier=coerce_source_tier(citation.get("source_tier")),
        official_url=citation.get("official_url"),
        official_identifier=citation.get("official_identifier"),
        official_hash=citation.get("official_hash"),
        verified_at=citation.get("verified_at"),
        source_label=citation.get("source_label"),
        legal_material_type=citation.get("legal_material_type"),
        identifier_resolution=coerce_identifier_resolution(
            citation.get("identifier_resolution")
        ),
    )


def validate_citation(
    citation: dict[str, Any],
    require_final: bool = False,
    config: SourcePolicyConfig = DEFAULT_SOURCE_POLICY_CONFIG,
) -> dict[str, Any]:
    citation_id = str(citation.get("citation_id") or citation.get("source_id") or "")
    source = _source_from_mapping(citation)
    decision = evaluate_citation_use(source, config)
    citation_use = decision.citation_use

    if not citation_id:
        status = CitationStatus.NOT_FOUND
        support = CitationSupport.UNSUPPORTED
        eligibility = CitationEligibility.MISSING
        reason = "citation_id is missing"
        error_code = "CITATION_ID_MISSING"
    elif citation_use == CitationUse.ALLOW_FINAL:
        status = CitationStatus.EXISTS
        support = CitationSupport.NOT_CHECKED
        eligibility = CitationEligibility.FINAL_ELIGIBLE
        reason = "source tier is eligible for final citation"
        error_code = None
    elif citation_use == CitationUse.DEMO_ONLY:
        status = CitationStatus.EXISTS
        support = CitationSupport.NOT_CHECKED
        eligibility = CitationEligibility.DEMO_ONLY
        reason = "synthetic source exists for demo only"
        error_code = "SYNTHETIC_DEMO_ONLY"
    elif citation_use == CitationUse.ALLOW_CANDIDATE_ONLY:
        status = CitationStatus.UNVERIFIABLE if require_final else CitationStatus.EXISTS
        support = CitationSupport.NOT_CHECKED
        eligibility = CitationEligibility.CANDIDATE_ONLY
        reason = "source tier is candidate-only and not allowed as final citation"
        error_code = "CANDIDATE_ONLY_SOURCE" if require_final else None
    else:
        status = CitationStatus.UNVERIFIABLE
        support = CitationSupport.NOT_CHECKED
        eligibility = CitationEligibility.REJECTED
        reason = decision.reason or "source tier is rejected or unknown"
        error_code = decision.reason_code or "SOURCE_REJECTED_OR_UNKNOWN"

    return {
        "citation_id": citation_id,
        "status": status.value,
        "support": support.value,
        "citation_eligibility": eligibility.value,
        "source_tier": source.source_tier.value,
        "citation_use": citation_use.value,
        "official_url": source.official_url,
        "official_identifier": source.official_identifier,
        "identifier_resolution": source.identifier_resolution.value,
        "reason": reason,
        "error_code": error_code,
        "human_review_required": status != CitationStatus.EXISTS or citation_use != CitationUse.ALLOW_FINAL,
    }


def is_final_citation(validation: dict[str, Any]) -> bool:
    return (
        validation.get("status") == CitationStatus.EXISTS.value
        and validation.get("citation_use") == CitationUse.ALLOW_FINAL.value
    )
