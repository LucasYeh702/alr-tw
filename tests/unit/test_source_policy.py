from tw_legal_rag_mcp.verification.source_policy import (
    CitationUse,
    IdentifierResolution,
    SourcePolicyConfig,
    SourceRecord,
    SourceTier,
    classify_citation_use,
    evaluate_citation_use,
    source_policy_config_from_env,
)

IDENTIFIER_OPT_IN = SourcePolicyConfig(identifier_backed_verified_cache=True)


def _identifier_backed_record(
    *,
    legal_material_type: str | None = "judgment",
    identifier_resolution: IdentifierResolution = IdentifierResolution.NOT_ATTEMPTED,
) -> SourceRecord:
    return SourceRecord(
        source_id="cache-jid-1",
        source_tier=SourceTier.VERIFIED_CACHE,
        official_identifier="DEMO,113,測,1,20990101,1",
        official_hash="sha256:raw-jsonl-line",
        verified_at="2026-01-01T00:00:00Z",
        legal_material_type=legal_material_type,
        identifier_resolution=identifier_resolution,
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
    # The strict URL-backed path does not depend on the opt-in capability.
    assert classify_citation_use(source, IDENTIFIER_OPT_IN) == CitationUse.ALLOW_FINAL


def test_verified_cache_missing_hash_is_rejected():
    source = SourceRecord(
        source_id="cache-2",
        source_tier=SourceTier.VERIFIED_CACHE,
        official_url="https://example.test/law/1",
        verified_at="2026-01-01T00:00:00Z",
    )

    decision = evaluate_citation_use(source)
    assert decision.citation_use == CitationUse.REJECT
    assert decision.reason_code == "VERIFIED_CACHE_INCOMPLETE"


def test_identifier_backed_cache_fails_closed_by_default():
    decision = evaluate_citation_use(
        _identifier_backed_record(
            identifier_resolution=IdentifierResolution.HASH_MATCH
        )
    )

    assert decision.citation_use == CitationUse.REJECT
    assert decision.reason_code == "IDENTIFIER_BACKED_DISABLED"


def test_identifier_backed_cache_with_resolver_match_allows_final_when_opted_in():
    decision = evaluate_citation_use(
        _identifier_backed_record(
            identifier_resolution=IdentifierResolution.HASH_MATCH
        ),
        IDENTIFIER_OPT_IN,
    )

    assert decision.citation_use == CitationUse.ALLOW_FINAL


def test_identifier_backed_cache_with_hash_mismatch_is_rejected():
    decision = evaluate_citation_use(
        _identifier_backed_record(
            identifier_resolution=IdentifierResolution.HASH_MISMATCH
        ),
        IDENTIFIER_OPT_IN,
    )

    assert decision.citation_use == CitationUse.REJECT
    assert decision.reason_code == "IDENTIFIER_HASH_MISMATCH"


def test_identifier_backed_cache_without_resolution_is_rejected():
    for resolution in (
        IdentifierResolution.NOT_ATTEMPTED,
        IdentifierResolution.UNRESOLVED,
    ):
        decision = evaluate_citation_use(
            _identifier_backed_record(identifier_resolution=resolution),
            IDENTIFIER_OPT_IN,
        )

        assert decision.citation_use == CitationUse.REJECT
        assert decision.reason_code == "IDENTIFIER_UNRESOLVED"


def test_identifier_backed_cache_is_limited_to_judgment_records():
    for material_type in ("law", "constitutional", None):
        decision = evaluate_citation_use(
            _identifier_backed_record(
                legal_material_type=material_type,
                identifier_resolution=IdentifierResolution.HASH_MATCH,
            ),
            IDENTIFIER_OPT_IN,
        )

        assert decision.citation_use == CitationUse.REJECT
        assert decision.reason_code == "IDENTIFIER_MATERIAL_NOT_ELIGIBLE"


def test_identifier_only_cache_never_final_without_resolver_match():
    """Gate assertion: no configuration path lets a bare identifier reach final.

    A fabricated identifier plus fabricated hash and timestamp must never
    classify as allow_final unless a resolver produced hash_match, regardless
    of opt-in state or material type.
    """
    for config in (SourcePolicyConfig(), IDENTIFIER_OPT_IN):
        for material_type in ("judgment", "law", "constitutional", None):
            for resolution in IdentifierResolution:
                if resolution == IdentifierResolution.HASH_MATCH:
                    continue
                source = _identifier_backed_record(
                    legal_material_type=material_type,
                    identifier_resolution=resolution,
                )

                assert classify_citation_use(source, config) == CitationUse.REJECT


def test_source_policy_config_from_env_defaults_off():
    assert source_policy_config_from_env({}) == SourcePolicyConfig()
    assert source_policy_config_from_env(
        {"ALR_TW_IDENTIFIER_BACKED_VERIFIED_CACHE": "0"}
    ) == SourcePolicyConfig()
    assert source_policy_config_from_env(
        {"ALR_TW_IDENTIFIER_BACKED_VERIFIED_CACHE": "true"}
    ) == SourcePolicyConfig(identifier_backed_verified_cache=True)


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
