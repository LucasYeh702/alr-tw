from tw_legal_rag_mcp.verification.identifier_resolver import (
    SYNTHETIC_OFFICIAL_RECORDS,
    SyntheticIdentifierResolver,
    compute_content_hash,
    resolve_identifier_citation,
    resolve_identifier_status,
)
from tw_legal_rag_mcp.verification.source_policy import (
    IdentifierResolution,
    SourceRecord,
    SourceTier,
)

DEMO_JID = "DEMO,113,測,1,20990101,1"
DEMO_HASH = compute_content_hash(SYNTHETIC_OFFICIAL_RECORDS[DEMO_JID])


def test_compute_content_hash_is_prefixed_and_deterministic():
    assert DEMO_HASH.startswith("sha256:")
    assert DEMO_HASH == compute_content_hash(SYNTHETIC_OFFICIAL_RECORDS[DEMO_JID])


def test_synthetic_resolver_resolves_demo_identifier_only():
    resolver = SyntheticIdentifierResolver()

    resolved = resolver.resolve(DEMO_JID)
    assert resolved is not None
    assert resolved.identifier == DEMO_JID

    assert resolver.resolve("DEMO,113,測,999,20990101,1") is None


def test_resolve_identifier_status_covers_match_mismatch_and_unresolved():
    resolver = SyntheticIdentifierResolver()

    assert (
        resolve_identifier_status(DEMO_JID, DEMO_HASH, resolver)
        == IdentifierResolution.HASH_MATCH
    )
    assert (
        resolve_identifier_status(DEMO_JID, "sha256:fabricated", resolver)
        == IdentifierResolution.HASH_MISMATCH
    )
    assert (
        resolve_identifier_status("DEMO,113,測,999,20990101,1", DEMO_HASH, resolver)
        == IdentifierResolution.UNRESOLVED
    )


def test_resolve_identifier_citation_updates_verified_cache_records_only():
    resolver = SyntheticIdentifierResolver()
    cache_record = SourceRecord(
        source_id="cache-jid-1",
        source_tier=SourceTier.VERIFIED_CACHE,
        official_identifier=DEMO_JID,
        official_hash=DEMO_HASH,
        verified_at="2026-01-01T00:00:00Z",
        legal_material_type="judgment",
    )

    resolved = resolve_identifier_citation(cache_record, resolver)
    assert resolved.identifier_resolution == IdentifierResolution.HASH_MATCH

    candidate_record = SourceRecord(
        source_id="tlr-1",
        source_tier=SourceTier.EXTERNAL_SEMANTIC_RECALL,
        official_identifier=DEMO_JID,
    )
    assert (
        resolve_identifier_citation(candidate_record, resolver).identifier_resolution
        == IdentifierResolution.NOT_ATTEMPTED
    )
