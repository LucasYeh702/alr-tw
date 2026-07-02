from tw_legal_rag_mcp.knowledge.layer import build_demo_issue_brief
from tw_legal_rag_mcp.legal_nlp.query_understanding import understand_query
from tw_legal_rag_mcp.legal_nlp.semantic_classifier import (
    overlay_predictions,
    shadow_annotate,
)
from tw_legal_rag_mcp.retrieval.coverage import CoverageState, build_stateful_coverage_report
from tw_legal_rag_mcp.retrieval.judgment_ranking import evaluate_ranking, rank_judgment_candidates
from tw_legal_rag_mcp.verification.trust_gates import evaluate_trust_gate


def test_stateful_coverage_keeps_reason_and_non_boolean_state():
    report = build_stateful_coverage_report(
        laws=(CoverageState.PRESENT, "synthetic law fixture matched", 2),
        judgments=(CoverageState.LOW_CONFIDENCE, "demo judgment lacks final citation", 1),
        constitutional=(CoverageState.NOT_CHECKED, "not needed for this query", 0),
    )

    assert report["has_laws"]["state"] == "present"
    assert report["has_laws"]["reason"] == "synthetic law fixture matched"
    assert report["has_laws"]["evidence_count"] == 2
    assert all(not isinstance(item["state"], bool) for item in report.values())


def test_query_understanding_masks_private_text_and_extracts_legal_signals():
    synthetic_id = "A" + "123456789"
    result = understand_query(f"王小明 {synthetic_id} 想問房東不退押金，類似民法第184條嗎？")

    assert result["masked_query"] != result["raw_query"]
    assert synthetic_id not in result["masked_query"]
    assert result["normalized_query"].startswith("王小明 [TW_ID] 想問出租人不退擔保金")
    assert result["intent"] == "civil_law"
    assert result["citations"][0]["normalized"] == "民法 第184條"
    assert "lease_deposit" in result["issue_tags"]


def test_classifier_shadow_and_overlay_keep_human_review_boundary():
    prediction = shadow_annotate("出租人不退擔保金")

    assert prediction["label"] == "lease_deposit"
    assert prediction["review_required"] is True

    overlay = overlay_predictions(
        base_result={"issue_tags": ["lease_deposit"]},
        predictions=[prediction],
    )
    assert overlay["classifier_overlay"][0]["label"] == "lease_deposit"
    assert overlay["final_label_source"] == "human_or_rule_required"


def test_demo_issue_brief_is_synthetic_and_not_legal_advice():
    brief = build_demo_issue_brief("lease_deposit")

    assert brief["issue_id"] == "lease_deposit"
    assert brief["source_tier"] == "synthetic"
    assert brief["not_legal_advice"] is True
    assert brief["citation_policy"] == "official_or_verified_cache_only"


def test_judgment_ranking_prefers_exact_issue_and_verified_sources():
    candidates = [
        {
            "source_id": "demo-judgment-low",
            "source_tier": "synthetic",
            "issue_tags": ["consumer"],
            "text": "示範文字",
        },
        {
            "source_id": "demo-judgment-strong",
            "source_tier": "official",
            "issue_tags": ["lease_deposit"],
            "text": "出租人 擔保金 返還",
        },
    ]

    ranked = rank_judgment_candidates("出租人不退擔保金", candidates, issue_tags=["lease_deposit"])

    assert ranked[0]["source_id"] == "demo-judgment-strong"
    assert ranked[0]["rank_score"] > ranked[1]["rank_score"]
    metric = evaluate_ranking(
        ranked,
        relevant_source_ids={"demo-judgment-strong"},
        note="synthetic demo metric",
    )
    assert metric["mrr"] == 1.0
    assert metric["note"] == "synthetic demo metric"


def test_trust_gate_blocks_candidate_only_final_answer_but_allows_official():
    blocked = evaluate_trust_gate(
        answer="候選結果",
        citations=[{"citation_id": "tlr-1", "source_id": "tlr-1", "source_tier": "external_semantic_recall"}],
        coverage={"has_laws": "present", "has_judgments": "low_confidence"},
    )
    assert blocked["safe_to_present"] is False
    assert "NO_FINAL_CITATION" in blocked["failure_reasons"]

    allowed = evaluate_trust_gate(
        answer="官方來源支持的結果",
        citations=[{"citation_id": "official-1", "source_id": "official-1", "source_tier": "official"}],
        coverage={"has_laws": "present", "has_judgments": "not_checked"},
    )
    assert allowed["safe_to_present"] is True
