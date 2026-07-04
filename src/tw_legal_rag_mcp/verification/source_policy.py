from __future__ import annotations

import os
from collections.abc import Mapping
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


class IdentifierResolution(str, Enum):
    """Outcome of resolving an official identifier against a local original record.

    Only a verifier that has resolved the identifier to a locally downloaded
    official record and recomputed its content hash may set HASH_MATCH. A bare
    identifier string supplied by a caller is never sufficient on its own.
    """

    NOT_ATTEMPTED = "not_attempted"
    HASH_MATCH = "hash_match"
    HASH_MISMATCH = "hash_mismatch"
    UNRESOLVED = "unresolved"


# Identifier-backed verified cache is limited to judgment-type records:
# Judicial Yuan judgments are keyed by stable JIDs while per-record URLs are
# not durable. Laws and constitutional materials keep the strict URL rule.
IDENTIFIER_ELIGIBLE_MATERIAL_TYPES = frozenset({"judgment"})

IDENTIFIER_BACKED_VERIFIED_CACHE_ENV = "ALR_TW_IDENTIFIER_BACKED_VERIFIED_CACHE"
_ENV_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True)
class SourcePolicyConfig:
    """Deployment-level source policy capabilities. All relaxations default OFF."""

    identifier_backed_verified_cache: bool = False


DEFAULT_SOURCE_POLICY_CONFIG = SourcePolicyConfig()


def source_policy_config_from_env(environ: Mapping[str, str] | None = None) -> SourcePolicyConfig:
    env = os.environ if environ is None else environ
    raw = env.get(IDENTIFIER_BACKED_VERIFIED_CACHE_ENV, "").strip().lower()
    return SourcePolicyConfig(identifier_backed_verified_cache=raw in _ENV_TRUE_VALUES)


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    source_tier: SourceTier
    official_url: str | None = None
    official_identifier: str | None = None
    official_hash: str | None = None
    verified_at: str | None = None
    source_label: str | None = None
    legal_material_type: str | None = None
    identifier_resolution: IdentifierResolution = IdentifierResolution.NOT_ATTEMPTED


@dataclass(frozen=True)
class SourcePolicyDecision:
    citation_use: CitationUse
    reason_code: str | None = None
    reason: str = ""


def coerce_source_tier(value: str | SourceTier | None) -> SourceTier:
    if isinstance(value, SourceTier):
        return value
    if value is None:
        return SourceTier.UNKNOWN
    try:
        return SourceTier(value)
    except ValueError:
        return SourceTier.UNKNOWN


def coerce_identifier_resolution(
    value: str | IdentifierResolution | None,
) -> IdentifierResolution:
    if isinstance(value, IdentifierResolution):
        return value
    if value is None:
        return IdentifierResolution.NOT_ATTEMPTED
    try:
        return IdentifierResolution(value)
    except ValueError:
        return IdentifierResolution.NOT_ATTEMPTED


def _evaluate_verified_cache(
    source: SourceRecord, config: SourcePolicyConfig
) -> SourcePolicyDecision:
    if not (source.official_hash and source.verified_at):
        return SourcePolicyDecision(
            CitationUse.REJECT,
            "VERIFIED_CACHE_INCOMPLETE",
            "verified cache is missing official hash or verification time",
        )
    if source.official_url:
        return SourcePolicyDecision(
            CitationUse.ALLOW_FINAL,
            None,
            "verified cache has official URL, hash, and verification time",
        )
    if not source.official_identifier:
        return SourcePolicyDecision(
            CitationUse.REJECT,
            "VERIFIED_CACHE_INCOMPLETE",
            "verified cache is missing an official URL",
        )
    if not config.identifier_backed_verified_cache:
        return SourcePolicyDecision(
            CitationUse.REJECT,
            "IDENTIFIER_BACKED_DISABLED",
            "identifier-backed verified cache is an opt-in capability and is disabled",
        )
    if source.legal_material_type not in IDENTIFIER_ELIGIBLE_MATERIAL_TYPES:
        return SourcePolicyDecision(
            CitationUse.REJECT,
            "IDENTIFIER_MATERIAL_NOT_ELIGIBLE",
            "identifier-backed verified cache is limited to judgment records",
        )
    resolution = source.identifier_resolution
    if resolution == IdentifierResolution.HASH_MATCH:
        return SourcePolicyDecision(
            CitationUse.ALLOW_FINAL,
            None,
            "official identifier resolved to a local original record with matching hash",
        )
    if resolution == IdentifierResolution.HASH_MISMATCH:
        return SourcePolicyDecision(
            CitationUse.REJECT,
            "IDENTIFIER_HASH_MISMATCH",
            "recomputed content hash of the resolved original record does not match",
        )
    return SourcePolicyDecision(
        CitationUse.REJECT,
        "IDENTIFIER_UNRESOLVED",
        "official identifier was not resolved against a local original record",
    )


def evaluate_citation_use(
    source: SourceRecord,
    config: SourcePolicyConfig = DEFAULT_SOURCE_POLICY_CONFIG,
) -> SourcePolicyDecision:
    if source.source_tier == SourceTier.OFFICIAL:
        return SourcePolicyDecision(
            CitationUse.ALLOW_FINAL, None, "official source tier"
        )
    if source.source_tier == SourceTier.VERIFIED_CACHE:
        return _evaluate_verified_cache(source, config)
    if source.source_tier in {SourceTier.STAGING, SourceTier.EXTERNAL_SEMANTIC_RECALL}:
        return SourcePolicyDecision(
            CitationUse.ALLOW_CANDIDATE_ONLY,
            None,
            "candidate-only source tier",
        )
    if source.source_tier == SourceTier.SYNTHETIC:
        return SourcePolicyDecision(CitationUse.DEMO_ONLY, None, "synthetic demo fixture")
    return SourcePolicyDecision(
        CitationUse.REJECT, "SOURCE_REJECTED_OR_UNKNOWN", "unknown source tier"
    )


def classify_citation_use(
    source: SourceRecord,
    config: SourcePolicyConfig = DEFAULT_SOURCE_POLICY_CONFIG,
) -> CitationUse:
    return evaluate_citation_use(source, config).citation_use
