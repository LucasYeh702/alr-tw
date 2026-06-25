from __future__ import annotations

from .tools import (
    exact_constitutional_lookup_tool,
    exact_judgment_lookup_tool,
    exact_law_lookup_tool,
    legal_search,
    validate_citation_tool,
)


TOOLS = {
    "legal_search": legal_search,
    "validate_citation": validate_citation_tool,
    "exact_law_lookup": exact_law_lookup_tool,
    "exact_judgment_lookup": exact_judgment_lookup_tool,
    "exact_constitutional_lookup": exact_constitutional_lookup_tool,
}
