from __future__ import annotations


SYNTHETIC_SYNONYMS = {
    "房東": "出租人",
    "押金": "擔保金",
}


def normalize_query(query: str) -> str:
    normalized = query
    for source, target in SYNTHETIC_SYNONYMS.items():
        normalized = normalized.replace(source, target)
    return normalized
