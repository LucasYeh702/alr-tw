from __future__ import annotations


def build_demo_law_timeline(law_id: str) -> dict[str, object]:
    return {
        "law_id": law_id,
        "source_tier": "synthetic",
        "not_legal_advice": True,
        "disclaimer": (
            "This timeline is for architecture demonstration only and does not "
            "represent actual legislative amendments or current law."
        ),
        "versions": [
            {
                "version_id": f"{law_id}-v1",
                "effective_from": "2026-01-01",
                "source_tier": "synthetic",
                "is_current_law": False,
                "note": "Synthetic historical version for demo only.",
            },
            {
                "version_id": f"{law_id}-v2",
                "effective_from": "2026-06-01",
                "source_tier": "synthetic",
                "is_current_law": False,
                "note": "Synthetic timeline does not represent current law.",
            },
        ],
    }
