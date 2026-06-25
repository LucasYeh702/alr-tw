from __future__ import annotations


DEMO_BRIEFS = {
    "lease_deposit": {
        "title": "示範租賃擔保金爭議",
        "summary": "合成示範：先確認契約、收據、返還條件與可查證引用來源。",
        "rule_cards": [
            {
                "card_id": "demo-rule-lease-001",
                "text": "本卡為 synthetic rule card，不代表任何現行法。",
                "source_tier": "synthetic",
            }
        ],
    }
}


def build_demo_issue_brief(issue_id: str) -> dict[str, object]:
    brief = DEMO_BRIEFS.get(
        issue_id,
        {
            "title": "示範一般法律研究問題",
            "summary": "合成示範：此問題尚未建立專門 issue brief。",
            "rule_cards": [],
        },
    )
    return {
        "issue_id": issue_id,
        "source_tier": "synthetic",
        "not_legal_advice": True,
        "citation_policy": "official_or_verified_cache_only",
        **brief,
    }
