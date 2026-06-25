from __future__ import annotations

import json

from tw_legal_rag_mcp.retrieval.search_coordinator import demo_search


def main() -> int:
    synthetic_id = "A" + "123456789"
    result = demo_search(f"{synthetic_id} 想問房東不退押金，類似民法第184條嗎？")
    print(
        json.dumps(
            {
                "query_understanding": result["query_understanding"],
                "stateful_coverage": result["stateful_coverage"],
                "knowledge_brief": result["knowledge_brief"],
                "ranking_eval": result["ranking_eval"],
                "trust_gate": result["trust_gate"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
