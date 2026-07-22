from __future__ import annotations

from alr_tw.contracts.providers import CandidateIdentity, ProviderCandidate
from alr_tw.research.judgment_identity import (
    direct_judgment_identity,
    rank_and_dedupe_judgment_identities,
    resolve_judgment_candidate,
)


JID = "DEMO,113,測,42,20990102,1"


def _candidate(
    candidate_id: str,
    provider_id: str,
    *,
    identity: CandidateIdentity | None = None,
    official_identifier: str | None = None,
    official_url: str | None = None,
    rank: int | None = None,
    score: float | None = None,
    title: str | None = None,
    excerpt: str | None = None,
) -> ProviderCandidate:
    return ProviderCandidate(
        candidate_id=candidate_id,
        provider_id=provider_id,
        identity=identity,
        official_identifier=official_identifier,
        official_url=official_url,
        candidate_rank=rank,
        score=score,
        title=title,
        excerpt=excerpt,
    )


def test_resolver_prefers_typed_identity_and_supports_url_fallback() -> None:
    typed = _candidate(
        "typed",
        "tlr_semantic_recall",
        identity=CandidateIdentity(canonical_jid=JID, provider_document_id="opaque"),
    )
    url_only = _candidate(
        "url",
        "tlr_semantic_recall",
        identity=CandidateIdentity(
            provider_document_id="opaque",
            official_url=(
                "https://judgment.judicial.gov.tw/FJUD/data.aspx?ty=JD&"
                "id=DEMO%2C113%2C%E6%B8%AC%2C42%2C20990102%2C1"
            ),
        ),
    )

    typed_result = resolve_judgment_candidate(typed)
    url_result = resolve_judgment_candidate(url_only)

    assert typed_result is not None
    assert typed_result.lookup_identifier == JID
    assert typed_result.resolution_method == "typed_canonical_jid"
    assert url_result is not None
    assert url_result.lookup_identifier == JID
    assert url_result.resolution_method == "typed_official_url"


def test_resolver_supports_formal_citation_and_legacy_doc_id() -> None:
    formal = _candidate(
        "formal",
        "tlr_semantic_recall",
        identity=CandidateIdentity(formal_citation="臺灣臺北地方法院113年度訴字第42號民事判決"),
    )
    legacy = ProviderCandidate(
        candidate_id="legacy",
        provider_id="legacy_provider",
        metadata={"doc_id": JID},
    )

    formal_result = resolve_judgment_candidate(formal)
    legacy_result = resolve_judgment_candidate(legacy)

    assert formal_result is not None
    assert formal_result.lookup_identifier.endswith("民事判決")
    assert formal_result.resolution_method == "formal_citation"
    assert legacy_result is not None
    assert legacy_result.lookup_identifier == JID
    assert legacy_result.resolution_method == "legacy_metadata_doc_id"


def test_rank_and_dedupe_keeps_official_target_and_merges_provenance() -> None:
    tlr = _candidate(
        "tlr-1",
        "tlr_semantic_recall",
        identity=CandidateIdentity(canonical_jid=JID),
        rank=1,
        score=0.99,
    )
    official = _candidate(
        "official-1",
        "official_judicial_yuan_judgments",
        identity=CandidateIdentity(canonical_jid=JID),
        rank=3,
        score=0.2,
    )

    identities = [resolve_judgment_candidate(tlr), resolve_judgment_candidate(official)]
    ranked = rank_and_dedupe_judgment_identities(
        [item for item in identities if item is not None]
    )

    assert len(ranked) == 1
    assert ranked[0].candidate is not None
    assert ranked[0].candidate.provider_id == "official_judicial_yuan_judgments"
    assert ranked[0].merged_candidate_ids == ("official-1", "tlr-1")


def test_direct_jid_dedupe_preserves_matching_candidate_provenance() -> None:
    tlr = _candidate(
        "tlr-1",
        "tlr_semantic_recall",
        identity=CandidateIdentity(canonical_jid=JID),
        rank=1,
    )
    resolved = resolve_judgment_candidate(tlr)
    assert resolved is not None

    ranked = rank_and_dedupe_judgment_identities(
        [direct_judgment_identity(JID), resolved]
    )

    assert len(ranked) == 1
    assert ranked[0].lookup_identifier == JID
    assert ranked[0].candidate is not None
    assert ranked[0].candidate.candidate_id == "tlr-1"
    assert ranked[0].resolution_method == "typed_canonical_jid"
    assert ranked[0].merged_candidate_ids == ("tlr-1",)


def test_query_relevance_demotes_unrelated_criminal_tlr_candidate() -> None:
    criminal_jid = "DEMO,113,刑,7,20990103,1"
    criminal = _candidate(
        "tlr-criminal",
        "tlr_semantic_recall",
        identity=CandidateIdentity(canonical_jid=criminal_jid),
        rank=1,
        score=0.99,
        title="臺灣示範地方法院刑事判決",
        excerpt="被告涉犯詐欺罪，量處有期徒刑。",
    )
    labor = _candidate(
        "tlr-labor",
        "tlr_semantic_recall",
        identity=CandidateIdentity(canonical_jid=JID),
        rank=2,
        score=0.8,
        title="臺灣示範地方法院民事判決",
        excerpt="勞工於試用期間遭雇主終止勞動契約，請求給付資遣費。",
    )
    identities = [resolve_judgment_candidate(criminal), resolve_judgment_candidate(labor)]

    ranked = rank_and_dedupe_judgment_identities(
        [item for item in identities if item is not None],
        query="試用期間解僱是否應支付資遣費",
    )

    assert [item.candidate.candidate_id for item in ranked if item.candidate] == [
        "tlr-labor",
        "tlr-criminal",
    ]
