from __future__ import annotations

from alr_tw.harness.orchestrator import run_agentic_demo
from alr_tw.harness.report_builder import build_validation_report

from ..agentic.runner import run_agentic_legal_research
from ..retrieval.exact_lookup import exact_constitutional_lookup, exact_judgment_lookup, exact_law_lookup
from ..retrieval.search_coordinator import demo_search
from alr_tw.verification.claim_support import (
    claim_grounding_policy,
    check_claim_support,
    extract_answer_claims,
)
from ..verification.citation_validator import validate_citation
from ..verification.identifier_resolver import (
    SyntheticIdentifierResolver,
    resolve_identifier_status,
)
from ..verification.source_policy import source_policy_config_from_env


def agentic_legal_research(query: str) -> dict:
    return run_agentic_legal_research(query)


def legal_search(query: str) -> dict:
    return demo_search(query)


def validate_citation_tool(
    citation_id: str,
    source_tier: str,
    official_url: str | None = None,
    official_identifier: str | None = None,
    official_hash: str | None = None,
    verified_at: str | None = None,
    source_label: str | None = None,
    legal_material_type: str | None = None,
) -> dict:
    config = source_policy_config_from_env()
    citation = {
        "citation_id": citation_id,
        "source_id": citation_id,
        "source_tier": source_tier,
        "official_url": official_url,
        "official_identifier": official_identifier,
        "official_hash": official_hash,
        "verified_at": verified_at,
        "source_label": source_label,
        "legal_material_type": legal_material_type,
    }
    # Resolution status is computed server-side by the resolver; callers cannot
    # declare it. The public server only carries the synthetic demo resolver.
    if (
        config.identifier_backed_verified_cache
        and source_tier == "verified_cache"
        and official_identifier
        and not official_url
    ):
        citation["identifier_resolution"] = resolve_identifier_status(
            official_identifier,
            official_hash,
            SyntheticIdentifierResolver(),
        ).value
    return validate_citation(citation, require_final=True, config=config)


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


def extract_answer_claims_tool(answer: str) -> dict:
    claims = extract_answer_claims(answer)
    return {
        "schema_version": "alr-tw.claim_extraction_result/v1",
        "schema": "alr-tw.answer-claim/v1-list",
        "count": len(claims),
        "claims": [claim.model_dump() for claim in claims],
    }


def check_claim_support_tool(
    answer: str,
    claims: list[dict[str, object]],
    segments: list[dict[str, object]],
) -> dict:
    support_items, summary, failure_reasons = check_claim_support(
        answer=answer,
        claims=claims,
        segments=segments,
    )

    return {
        "schema": "alr-tw.claim-support-result/v1",
        "claim_support": [item.model_dump() for item in support_items],
        "summary": summary.model_dump(),
        "failure_reasons": failure_reasons,
    }


def get_claim_grounding_policy_tool() -> dict:
    return claim_grounding_policy()


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
