from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SourceTier(str, Enum):
    OFFICIAL = "official"
    VERIFIED_CACHE = "verified_cache"
    STAGING = "staging"
    EXTERNAL_SEMANTIC_RECALL = "external_semantic_recall"
    SYNTHETIC = "synthetic"
    UNKNOWN = "unknown"


class CitationUse(str, Enum):
    ALLOW_FINAL = "allow_final"
    ALLOW_CANDIDATE_ONLY = "allow_candidate_only"
    DEMO_ONLY = "demo_only"
    REJECT = "reject"


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    source_tier: SourceTier
    official_url: str | None = None
    official_hash: str | None = None
    verified_at: str | None = None
    source_label: str | None = None


def coerce_source_tier(value: str | SourceTier | None) -> SourceTier:
    if isinstance(value, SourceTier):
        return value
    if value is None:
        return SourceTier.UNKNOWN
    try:
        return SourceTier(value)
    except ValueError:
        return SourceTier.UNKNOWN


def classify_citation_use(source: SourceRecord) -> CitationUse:
    if source.source_tier == SourceTier.OFFICIAL:
        return CitationUse.ALLOW_FINAL
    if source.source_tier == SourceTier.VERIFIED_CACHE:
        if source.official_url and source.official_hash and source.verified_at:
            return CitationUse.ALLOW_FINAL
        return CitationUse.REJECT
    if source.source_tier in {SourceTier.STAGING, SourceTier.EXTERNAL_SEMANTIC_RECALL}:
        return CitationUse.ALLOW_CANDIDATE_ONLY
    if source.source_tier == SourceTier.SYNTHETIC:
        return CitationUse.DEMO_ONLY
    return CitationUse.REJECT
