from __future__ import annotations

from typing import Any


def _top_source_ids(results: list[dict[str, Any]]) -> list[str]:
    ranked = sorted(results, key=lambda item: (-int(item.get("rank_score", 0)), str(item.get("source_id", ""))))
    return [str(item["source_id"]) for item in ranked]


def build_baseline(baseline_id: str, results: list[dict[str, Any]]) -> dict[str, object]:
    return {
        "baseline_id": baseline_id,
        "top_source_ids": _top_source_ids(results),
        "production_data": "not_used",
    }


def build_snapshot(snapshot_id: str, results: list[dict[str, Any]]) -> dict[str, object]:
    return {
        "snapshot_id": snapshot_id,
        "top_source_ids": _top_source_ids(results),
        "result_count": len(results),
        "production_data": "not_used",
    }


def run_soak_check(samples: list[dict[str, object]]) -> dict[str, object]:
    top_lists = [sample.get("top_source_ids", []) for sample in samples]
    stable = bool(top_lists) and all(top_list == top_lists[0] for top_list in top_lists)
    return {
        "status": "stable" if stable else "changed",
        "sample_count": len(samples),
        "production_data": "not_used",
    }
