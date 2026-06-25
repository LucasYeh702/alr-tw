from __future__ import annotations


def route_query(query: str) -> str:
    if any(token in query for token in ("釋字", "憲判")):
        return "constitutional"
    if "法院" in query or "年度" in query:
        return "judgment"
    return "law"
