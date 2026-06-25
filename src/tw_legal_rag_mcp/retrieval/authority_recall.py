from __future__ import annotations

from typing import Any

from .authority_ranker import authority_score
from ..verification.source_policy import SourceRecord, classify_citation_use, coerce_source_tier


def recall_authorities(
    candidates: list[dict[str, Any]],
    *,
    issue_tags: list[str],
    limit: int = 5,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        source_tier = coerce_source_tier(candidate.get("source_tier"))
        citation_use = classify_citation_use(
            SourceRecord(
                source_id=str(candidate.get("source_id", "")),
                source_tier=source_tier,
                official_url=candidate.get("official_url"),
                official_hash=candidate.get("official_hash"),
                verified_at=candidate.get("verified_at"),
            )
        )
        if citation_use.value != "allow_final":
            continue
        candidate_tags = set(candidate.get("issue_tags", []))
        score = authority_score(source_tier.value) + 20 * len(candidate_tags.intersection(issue_tags))
        ranked.append({**candidate, "citation_use": citation_use.value, "authority_recall_score": score})

    return sorted(
        ranked,
        key=lambda item: (-int(item["authority_recall_score"]), str(item.get("source_id", ""))),
    )[:limit]
