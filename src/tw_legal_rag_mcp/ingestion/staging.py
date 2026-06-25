from __future__ import annotations


def mark_staging(source_id: str) -> dict[str, str]:
    return {"source_id": source_id, "state": "staging"}
