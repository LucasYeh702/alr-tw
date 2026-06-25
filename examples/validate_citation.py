from __future__ import annotations

import json

from tw_legal_rag_mcp.verification.citation_validator import validate_citation


def main() -> int:
    samples = [
        {"citation_id": "official-1", "source_id": "official-1", "source_tier": "official"},
        {"citation_id": "tlr-1", "source_id": "tlr-1", "source_tier": "external_semantic_recall"},
        {"citation_id": "hf-1", "source_id": "hf-1", "source_tier": "staging"},
        {"citation_id": "demo-1", "source_id": "demo-1", "source_tier": "synthetic"},
    ]
    print(json.dumps([validate_citation(item, require_final=True) for item in samples], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
