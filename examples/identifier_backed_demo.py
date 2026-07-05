from __future__ import annotations

from tw_legal_rag_mcp.verification.citation_validator import validate_citation
from tw_legal_rag_mcp.verification.identifier_resolver import (
    SYNTHETIC_OFFICIAL_RECORDS,
    SyntheticIdentifierResolver,
    compute_content_hash,
    resolve_identifier_status,
)
from tw_legal_rag_mcp.verification.source_policy import SourcePolicyConfig


def _verified_cache_citation(
    *,
    identifier: str,
    official_hash: str,
    resolver: SyntheticIdentifierResolver,
) -> dict[str, str]:
    return {
        "citation_id": "verified-cache-demo",
        "source_id": "verified-cache-demo",
        "source_tier": "verified_cache",
        "official_identifier": identifier,
        "official_hash": official_hash,
        "verified_at": "2099-01-01T00:00:00Z",
        "source_label": "synthetic-official-cache",
        "legal_material_type": "judgment",
        "identifier_resolution": resolve_identifier_status(
            identifier,
            official_hash,
            resolver,
        ).value,
    }


def _candidate_citation(identifier: str) -> dict[str, str]:
    return {
        "citation_id": "tlr-candidate-demo",
        "source_id": "tlr-candidate-demo",
        "source_tier": "external_semantic_recall",
        "official_identifier": identifier,
        "source_label": "synthetic-tlr-candidate",
        "legal_material_type": "judgment",
    }


def main() -> int:
    resolver = SyntheticIdentifierResolver()
    identifier, canonical_text = next(iter(SYNTHETIC_OFFICIAL_RECORDS.items()))
    resolver_hash = compute_content_hash(canonical_text)
    fabricated_hash = compute_content_hash("synthetic mismatched canonical content")
    opt_in = SourcePolicyConfig(identifier_backed_verified_cache=True)
    default_config = SourcePolicyConfig()

    candidate = validate_citation(_candidate_citation(identifier), require_final=True)
    print(f"TLR candidate -> {candidate['citation_use']}")

    match = validate_citation(
        _verified_cache_citation(
            identifier=identifier,
            official_hash=resolver_hash,
            resolver=resolver,
        ),
        require_final=True,
        config=opt_in,
    )
    print(f"opt-in + resolver hash match -> {match['citation_use']}")

    mismatch = validate_citation(
        _verified_cache_citation(
            identifier=identifier,
            official_hash=fabricated_hash,
            resolver=resolver,
        ),
        require_final=True,
        config=opt_in,
    )
    print(f"opt-in + fabricated hash -> rejected with {mismatch['error_code']}")

    disabled = validate_citation(
        _verified_cache_citation(
            identifier=identifier,
            official_hash=resolver_hash,
            resolver=resolver,
        ),
        require_final=True,
        config=default_config,
    )
    print(f"default config (no opt-in) -> rejected with {disabled['error_code']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
