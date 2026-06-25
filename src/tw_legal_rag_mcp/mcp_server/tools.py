from __future__ import annotations

from ..retrieval.exact_lookup import exact_constitutional_lookup, exact_judgment_lookup, exact_law_lookup
from ..retrieval.search_coordinator import demo_search
from ..verification.citation_validator import validate_citation


def legal_search(query: str) -> dict:
    return demo_search(query)


def validate_citation_tool(citation_id: str, source_tier: str) -> dict:
    return validate_citation(
        {"citation_id": citation_id, "source_id": citation_id, "source_tier": source_tier},
        require_final=True,
    )


def exact_law_lookup_tool(title: str, article_no: str) -> dict:
    return exact_law_lookup(title, article_no)


def exact_judgment_lookup_tool(jid: str) -> dict:
    return exact_judgment_lookup(jid)


def exact_constitutional_lookup_tool(source_id: str) -> dict:
    return exact_constitutional_lookup(source_id)
