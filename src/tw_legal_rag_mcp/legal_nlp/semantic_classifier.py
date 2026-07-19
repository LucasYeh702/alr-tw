from __future__ import annotations

from collections.abc import Mapping


LABEL_RULES = {
    "lease_deposit": ("出租人", "房東", "押金", "擔保金"),
    "tort": ("侵權", "損害賠償", "民法第184條", "民法 第184條"),
    "labor": ("資遣", "工資", "勞基法"),
}


def shadow_annotate(text: str) -> dict[str, object]:
    for label, keywords in LABEL_RULES.items():
        if any(keyword in text for keyword in keywords):
            return {
                "label": label,
                "confidence": 0.82,
                "review_required": True,
                "mode": "shadow",
            }
    return {
        "label": "unknown",
        "confidence": 0.2,
        "review_required": True,
        "mode": "shadow",
    }


def overlay_predictions(
    *, base_result: Mapping[str, object], predictions: list[dict[str, object]]
) -> dict[str, object]:
    result = dict(base_result)
    result["classifier_overlay"] = predictions
    result["final_label_source"] = "human_or_rule_required"
    return result
