from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .coverage import CoverageState, build_coverage_report, build_stateful_coverage_report
from .judgment_ranking import evaluate_ranking, rank_judgment_candidates
from ..knowledge.layer import build_demo_issue_brief
from ..legal_nlp.query_normalizer import normalize_query
from ..legal_nlp.query_understanding import understand_query
from ..legal_nlp.semantic_classifier import overlay_predictions, shadow_annotate
from ..verification.trust_gates import evaluate_trust_gate


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_synthetic_documents(root: Path | None = None) -> list[dict[str, Any]]:
    base = root or _repo_root()
    docs: list[dict[str, Any]] = []
    for filename in (
        "synthetic_laws.jsonl",
        "synthetic_judgments.jsonl",
        "synthetic_constitutional.jsonl",
    ):
        path = base / "demo_data" / filename
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    docs.append(json.loads(line))
    return docs


def demo_search(query: str) -> dict[str, Any]:
    understanding = understand_query(query)
    normalized_query = normalize_query(query)
    documents = load_synthetic_documents()
    terms = {term for term in normalized_query.replace("？", "").replace("?", "").split() if term}

    results = []
    for doc in documents:
        haystack = f"{doc.get('title', '')} {doc.get('text', '')}"
        if any(term in haystack for term in terms) or "押金" in haystack:
            results.append(
                {
                    "citation_id": doc["source_id"],
                    "source_id": doc["source_id"],
                    "source_tier": doc["source_tier"],
                    "title": doc.get("title"),
                    "issue_tags": ["lease_deposit"] if "押金" in doc.get("text", "") else [],
                    "snippet": doc.get("text", "")[:80],
                    "text": doc.get("text", ""),
                }
            )

    ranked_results = rank_judgment_candidates(
        str(understanding["normalized_query"]),
        results,
        issue_tags=list(understanding["issue_tags"]),
    )
    classifier_prediction = shadow_annotate(str(understanding["normalized_query"]))
    overlay = overlay_predictions(base_result=understanding, predictions=[classifier_prediction])
    coverage = build_coverage_report(
        laws=CoverageState.PRESENT,
        judgments=CoverageState.PRESENT,
        constitutional=CoverageState.NOT_CHECKED,
        administrative=CoverageState.LOW_CONFIDENCE,
        opposing_view=CoverageState.ABSENT,
    )
    stateful_coverage = build_stateful_coverage_report(
        laws=(CoverageState.PRESENT, "synthetic law fixture loaded", 1),
        judgments=(CoverageState.PRESENT, "synthetic judgment fixture loaded", 1),
        constitutional=(CoverageState.NOT_CHECKED, "not needed for demo query", 0),
        administrative=(CoverageState.LOW_CONFIDENCE, "not included in synthetic demo index", 0),
        opposing_view=(CoverageState.ABSENT, "no synthetic opposing view fixture", 0),
    )
    issue_id = list(understanding["issue_tags"])[0] if understanding["issue_tags"] else "general"
    trust_gate = evaluate_trust_gate(
        answer="synthetic demo answer",
        citations=ranked_results,
        coverage=coverage,
    )

    return {
        "query": query,
        "normalized_query": normalized_query,
        "query_understanding": overlay,
        "coverage": coverage,
        "stateful_coverage": stateful_coverage,
        "knowledge_brief": build_demo_issue_brief(str(issue_id)),
        "ranking_eval": evaluate_ranking(
            ranked_results,
            relevant_source_ids={ranked_results[0]["source_id"]} if ranked_results else set(),
            note="synthetic demo metric: top-ranked fixture is treated as relevant",
        ),
        "trust_gate": trust_gate,
        "results": ranked_results,
    }
