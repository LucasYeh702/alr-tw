from __future__ import annotations

from typing import Iterable

from .authority_ranker import authority_score


def rank_judgment_candidates(
    query: str,
    candidates: list[dict[str, object]],
    *,
    issue_tags: list[str] | None = None,
) -> list[dict[str, object]]:
    issue_tags = issue_tags or []
    query_terms = {term for term in query.replace("？", "").replace("?", "").split() if term}
    ranked: list[dict[str, object]] = []

    for candidate in candidates:
        candidate_tags = set(candidate.get("issue_tags", []))
        text = str(candidate.get("text", ""))
        source_tier = str(candidate.get("source_tier", "unknown"))
        issue_score = 25 * len(candidate_tags.intersection(issue_tags))
        lexical_score = sum(5 for term in query_terms if term and term in text)
        score = authority_score(source_tier) + issue_score + lexical_score
        ranked.append({**candidate, "rank_score": score})

    return sorted(ranked, key=lambda item: (-int(item["rank_score"]), str(item.get("source_id", ""))))


def evaluate_ranking(
    ranked: list[dict[str, object]],
    *,
    relevant_source_ids: Iterable[str],
    note: str | None = None,
) -> dict[str, float | int]:
    relevant = set(relevant_source_ids)
    reciprocal_rank = 0.0
    for index, candidate in enumerate(ranked, start=1):
        if candidate.get("source_id") in relevant:
            reciprocal_rank = 1.0 / index
            break
    result: dict[str, float | int | str] = {"mrr": reciprocal_rank, "ranked_count": len(ranked)}
    if note:
        result["note"] = note
    return result
