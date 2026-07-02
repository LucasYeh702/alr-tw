from __future__ import annotations

from alr_tw.harness.orchestrator import run_agentic_demo
from alr_tw.harness.report_builder import build_validation_report

from ..agentic.runner import run_agentic_legal_research
from ..retrieval.exact_lookup import exact_constitutional_lookup, exact_judgment_lookup, exact_law_lookup
from ..retrieval.search_coordinator import demo_search
from ..verification.citation_validator import validate_citation


def agentic_legal_research(query: str) -> dict:
    return run_agentic_legal_research(query)


def legal_search(query: str) -> dict:
    return demo_search(query)


def validate_citation_tool(
    citation_id: str,
    source_tier: str,
    official_url: str | None = None,
    official_hash: str | None = None,
    verified_at: str | None = None,
    source_label: str | None = None,
) -> dict:
    return validate_citation(
        {
            "citation_id": citation_id,
            "source_id": citation_id,
            "source_tier": source_tier,
            "official_url": official_url,
            "official_hash": official_hash,
            "verified_at": verified_at,
            "source_label": source_label,
        },
        require_final=True,
    )


def exact_law_lookup_tool(title: str, article_no: str) -> dict:
    return exact_law_lookup(title, article_no)


def exact_judgment_lookup_tool(jid: str) -> dict:
    return exact_judgment_lookup(jid)


def exact_constitutional_lookup_tool(source_id: str) -> dict:
    return exact_constitutional_lookup(source_id)


def run_agentic_demo_tool(query: str, scenario: str = "auto") -> dict:
    return run_agentic_demo(query, scenario=scenario).model_dump()


def build_validation_report_tool(query: str, scenario: str = "auto") -> dict:
    trace = run_agentic_demo(query, scenario=scenario)
    return {
        "schema_version": "alr-tw.validation_report/v1",
        "trace": trace.model_dump(),
        "report": build_validation_report(trace),
    }


def get_trust_model_tool() -> dict:
    return {
        "schema_version": "alr-tw.trust_model/v1",
        "source_tiers": [
            "official",
            "verified_cache",
            "staging",
            "external_semantic_recall",
            "synthetic",
            "unknown",
        ],
        "final_citation_tiers": ["official", "verified_cache"],
        "candidate_only_tiers": ["staging", "external_semantic_recall"],
        "demo_only_tiers": ["synthetic"],
        "fail_closed_reasons": [
            "NO_FINAL_CITATION",
            "REJECTED_CITATION",
            "UNVERIFIABLE_CITATION",
            "LAWS_COVERAGE_LOW",
            "JUDGMENTS_COVERAGE_LOW",
            "CLAIM_SUPPORT_NOT_CHECKED",
            "HUMAN_REVIEW_REQUIRED",
        ],
    }
