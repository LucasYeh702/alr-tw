from __future__ import annotations


def build_promotion_manifest(source_id: str, official_hash: str) -> dict[str, str]:
    return {"source_id": source_id, "official_hash": official_hash, "state": "ready_for_review"}
