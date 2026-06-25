from __future__ import annotations

import json

from tw_legal_rag_mcp.knowledge.law_versions import build_demo_law_timeline
from tw_legal_rag_mcp.retrieval.authority_recall import recall_authorities
from tw_legal_rag_mcp.retrieval.exact_lookup import exact_judgment_lookup, exact_law_lookup
from tw_legal_rag_mcp.retrieval.lineage import build_demo_appellate_lineage
from tw_legal_rag_mcp.retrieval.retriever_cache import DemoRetrieverCache
from tw_legal_rag_mcp.retrieval.search_quality import build_baseline, build_snapshot, run_soak_check
from tw_legal_rag_mcp.verification.batch import run_source_verification_batch


def main() -> int:
    records = [
        {"source_id": "official-1", "source_tier": "official"},
        {"source_id": "tlr-1", "source_tier": "external_semantic_recall"},
    ]
    ranked = [
        {"source_id": "demo-law-001", "rank_score": 20, "source_tier": "synthetic"},
        {"source_id": "demo-judgment-001", "rank_score": 12, "source_tier": "synthetic"},
    ]
    cache = DemoRetrieverCache()
    cache.get_or_set("laws", "押金", lambda: [{"source_id": "demo-law-001"}])
    cache.get_or_set("laws", "押金", lambda: [{"source_id": "not-used"}])

    output = {
        "source_verification_batch": run_source_verification_batch(records),
        "authority_recall": recall_authorities(
            [
                {"source_id": "official-1", "source_tier": "official", "issue_tags": ["lease_deposit"]},
                {
                    "source_id": "tlr-1",
                    "source_tier": "external_semantic_recall",
                    "issue_tags": ["lease_deposit"],
                },
            ],
            issue_tags=["lease_deposit"],
        ),
        "search_quality": {
            "baseline": build_baseline("lease_deposit", ranked),
            "snapshot": build_snapshot("lease_deposit", ranked),
            "soak": run_soak_check([build_baseline("lease_deposit", ranked), build_snapshot("lease_deposit", ranked)]),
        },
        "cache": cache.stats(),
        "lineage": build_demo_appellate_lineage("demo-judgment-001"),
        "law_versions": build_demo_law_timeline("demo-law-001"),
        "exact_lookup": {
            "law": exact_law_lookup("示範租賃規則", "第1條"),
            "judgment": exact_judgment_lookup("DEMO,001,民,1,20260101,1"),
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
