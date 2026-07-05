from tw_legal_rag_mcp.knowledge.law_versions import build_demo_law_timeline
from tw_legal_rag_mcp.retrieval.authority_recall import recall_authorities
from tw_legal_rag_mcp.retrieval.exact_lookup import exact_constitutional_lookup, exact_judgment_lookup, exact_law_lookup
from tw_legal_rag_mcp.retrieval.lineage import build_demo_appellate_lineage
from tw_legal_rag_mcp.retrieval.retriever_cache import DemoRetrieverCache
from tw_legal_rag_mcp.retrieval.search_quality import build_baseline, build_snapshot, run_soak_check
from tw_legal_rag_mcp.verification.batch import run_source_verification_batch


def test_source_verification_batch_deduplicates_and_keeps_candidate_only_sources_non_final():
    records = [
        {"source_id": "official-1", "source_tier": "official"},
        {"source_id": "official-1", "source_tier": "official"},
        {"source_id": "tlr-1", "source_tier": "external_semantic_recall"},
        {
            "source_id": "cache-1",
            "source_tier": "verified_cache",
            "official_url": "https://example.test/law/1",
            "official_hash": "sha256:abc",
            "verified_at": "2026-01-01T00:00:00Z",
        },
    ]

    result = run_source_verification_batch(records)

    assert result["input_count"] == 4
    assert result["deduped_count"] == 3
    assert result["allow_final_count"] == 2
    assert result["candidate_only_count"] == 1
    assert result["final_source_ids"] == ["cache-1", "official-1"]


def test_authority_recall_prioritizes_official_and_verified_sources():
    candidates = [
        {"source_id": "tlr-1", "source_tier": "external_semantic_recall", "issue_tags": ["lease_deposit"]},
        {"source_id": "official-1", "source_tier": "official", "issue_tags": ["lease_deposit"]},
        {
            "source_id": "cache-1",
            "source_tier": "verified_cache",
            "issue_tags": ["lease_deposit"],
            "official_url": "https://example.test/law/1",
            "official_hash": "sha256:abc",
            "verified_at": "2026-01-01T00:00:00Z",
        },
    ]

    recalled = recall_authorities(candidates, issue_tags=["lease_deposit"], limit=2)

    assert [item["source_id"] for item in recalled] == ["official-1", "cache-1"]
    assert all(item["citation_use"] == "allow_final" for item in recalled)


def test_search_baseline_snapshot_and_soak_are_synthetic_and_stable():
    results = [
        {"source_id": "demo-law-001", "rank_score": 20, "source_tier": "synthetic"},
        {"source_id": "demo-judgment-001", "rank_score": 12, "source_tier": "synthetic"},
    ]

    baseline = build_baseline("lease_deposit", results)
    snapshot = build_snapshot("lease_deposit", results)
    soak = run_soak_check([baseline, snapshot])

    assert baseline["baseline_id"] == "lease_deposit"
    assert snapshot["top_source_ids"] == ["demo-law-001", "demo-judgment-001"]
    assert soak["status"] == "stable"
    assert soak["production_data"] == "not_used"


def test_demo_retriever_cache_reuses_by_query_and_corpus_without_persisting_data():
    cache = DemoRetrieverCache()

    first = cache.get_or_set("laws", "押金", lambda: [{"source_id": "demo-law-001"}])
    second = cache.get_or_set("laws", "押金", lambda: [{"source_id": "should-not-run"}])

    assert first == [{"source_id": "demo-law-001"}]
    assert second == first
    assert cache.stats() == {"entries": 1, "hits": 1, "misses": 1, "persistent": False}


def test_appellate_lineage_graph_uses_synthetic_nodes_only():
    graph = build_demo_appellate_lineage("demo-judgment-001")

    assert graph["root_judgment_id"] == "demo-judgment-001"
    assert graph["source_tier"] == "synthetic"
    assert graph["edges"][0]["relation"] == "appeal_from"
    assert graph["not_legal_advice"] is True


def test_law_version_timeline_marks_versions_as_synthetic_not_current_law():
    timeline = build_demo_law_timeline("demo-law-001")

    assert timeline["law_id"] == "demo-law-001"
    assert timeline["versions"][0]["source_tier"] == "synthetic"
    assert timeline["versions"][0]["is_current_law"] is False
    assert timeline["not_legal_advice"] is True
    assert "does not represent actual legislative amendments" in timeline["disclaimer"]


def test_exact_lookup_tools_return_demo_only_citations():
    law = exact_law_lookup("示範租賃規則", "第1條")
    judgment = exact_judgment_lookup("DEMO,113,測,1,20990101,1")
    constitutional = exact_constitutional_lookup("demo-constitutional-001")

    assert law["citation_use"] == "demo_only"
    assert judgment["source_tier"] == "synthetic"
    assert constitutional["status"] == "exists"
