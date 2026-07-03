from tw_legal_rag_mcp.verification.source_policy import (
    CitationUse,
    SourceRecord,
    SourceTier,
    classify_citation_use,
)


def test_official_source_allows_final_citation():
    source = SourceRecord(source_id="official-1", source_tier=SourceTier.OFFICIAL)

    assert classify_citation_use(source) == CitationUse.ALLOW_FINAL


def test_verified_cache_with_required_metadata_allows_final_citation():
    source = SourceRecord(
        source_id="cache-1",
        source_tier=SourceTier.VERIFIED_CACHE,
        official_url="https://example.test/law/1",
        official_hash="sha256:abc",
        verified_at="2026-01-01T00:00:00Z",
    )

    assert classify_citation_use(source) == CitationUse.ALLOW_FINAL


def test_verified_cache_with_stable_official_identifier_allows_final_citation():
    source = SourceRecord(
        source_id="cache-jid-1",
        source_tier=SourceTier.VERIFIED_CACHE,
        official_identifier="TSTV,113,測,1,20240102,1",
        official_hash="sha256:raw-jsonl-line",
        verified_at="2026-01-01T00:00:00Z",
    )

    assert classify_citation_use(source) == CitationUse.ALLOW_FINAL


def test_verified_cache_missing_hash_is_rejected():
    source = SourceRecord(
        source_id="cache-2",
        source_tier=SourceTier.VERIFIED_CACHE,
        official_url="https://example.test/law/1",
        verified_at="2026-01-01T00:00:00Z",
    )

    assert classify_citation_use(source) == CitationUse.REJECT


def test_candidate_only_and_demo_only_tiers_are_not_final_sources():
    assert (
        classify_citation_use(SourceRecord("hf-1", SourceTier.STAGING))
        == CitationUse.ALLOW_CANDIDATE_ONLY
    )
    assert (
        classify_citation_use(SourceRecord("tlr-1", SourceTier.EXTERNAL_SEMANTIC_RECALL))
        == CitationUse.ALLOW_CANDIDATE_ONLY
    )
    assert classify_citation_use(SourceRecord("demo-1", SourceTier.SYNTHETIC)) == CitationUse.DEMO_ONLY
    assert classify_citation_use(SourceRecord("unknown-1", SourceTier.UNKNOWN)) == CitationUse.REJECT
