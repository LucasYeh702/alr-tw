from __future__ import annotations

from enum import Enum
from typing import Any

from .source_policy import (
    CitationUse,
    SourceRecord,
    classify_citation_use,
    coerce_source_tier,
)


class CitationStatus(str, Enum):
    EXISTS = "exists"
    NOT_FOUND = "not_found"
    UNVERIFIABLE = "unverifiable"


class CitationSupport(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    NOT_CHECKED = "not_checked"


def _source_from_mapping(citation: dict[str, Any]) -> SourceRecord:
    return SourceRecord(
        source_id=str(citation.get("source_id") or citation.get("citation_id") or ""),
        source_tier=coerce_source_tier(citation.get("source_tier")),
        official_url=citation.get("official_url"),
        official_hash=citation.get("official_hash"),
        verified_at=citation.get("verified_at"),
        source_label=citation.get("source_label"),
    )


def validate_citation(citation: dict[str, Any], require_final: bool = False) -> dict[str, Any]:
    citation_id = str(citation.get("citation_id") or citation.get("source_id") or "")
    source = _source_from_mapping(citation)
    citation_use = classify_citation_use(source)

    if not citation_id:
        status = CitationStatus.NOT_FOUND
        support = CitationSupport.UNSUPPORTED
        reason = "citation_id is missing"
    elif citation_use == CitationUse.ALLOW_FINAL:
        status = CitationStatus.EXISTS
        support = CitationSupport.SUPPORTED
        reason = "citation is allowed as a final source"
    elif citation_use == CitationUse.DEMO_ONLY:
        status = CitationStatus.EXISTS
        support = CitationSupport.NOT_CHECKED
        reason = "synthetic source exists for demo only"
    elif citation_use == CitationUse.ALLOW_CANDIDATE_ONLY:
        status = CitationStatus.UNVERIFIABLE if require_final else CitationStatus.EXISTS
        support = CitationSupport.UNSUPPORTED if require_final else CitationSupport.NOT_CHECKED
        reason = "source tier is candidate-only and not allowed as final citation"
    else:
        status = CitationStatus.UNVERIFIABLE
        support = CitationSupport.UNSUPPORTED
        reason = "source tier is rejected or unknown"

    return {
        "citation_id": citation_id,
        "status": status.value,
        "support": support.value,
        "source_tier": source.source_tier.value,
        "citation_use": citation_use.value,
        "official_url": source.official_url,
        "reason": reason,
    }


def is_final_citation(validation: dict[str, Any]) -> bool:
    return (
        validation.get("status") == CitationStatus.EXISTS.value
        and validation.get("citation_use") == CitationUse.ALLOW_FINAL.value
    )
