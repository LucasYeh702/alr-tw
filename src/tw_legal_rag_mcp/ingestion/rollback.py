from __future__ import annotations


def rollback_plan(manifest_id: str) -> dict[str, str]:
    return {"manifest_id": manifest_id, "action": "manual_review_required"}
