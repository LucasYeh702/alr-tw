from __future__ import annotations


def build_demo_appellate_lineage(root_judgment_id: str) -> dict[str, object]:
    first_instance = f"{root_judgment_id}-first-instance"
    appeal = f"{root_judgment_id}-appeal"
    return {
        "root_judgment_id": root_judgment_id,
        "source_tier": "synthetic",
        "not_legal_advice": True,
        "nodes": [
            {"id": first_instance, "level": "first_instance", "source_tier": "synthetic"},
            {"id": appeal, "level": "appeal", "source_tier": "synthetic"},
            {"id": root_judgment_id, "level": "final_demo_node", "source_tier": "synthetic"},
        ],
        "edges": [
            {"from": appeal, "to": first_instance, "relation": "appeal_from"},
            {"from": root_judgment_id, "to": appeal, "relation": "appeal_from"},
        ],
    }
