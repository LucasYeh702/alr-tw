from __future__ import annotations

from typing import TypedDict

from .citation_parser import (
    CONSTITUTIONAL_RE,
    INTERPRETATION_RE,
    JUDGMENT_RE,
    LAW_ARTICLE_RE,
    parse_citation,
)
from .privacy import mask_sensitive_text
from .query_normalizer import normalize_query


ISSUE_KEYWORDS = {
    "lease_deposit": ("押金", "擔保金", "房東", "出租人"),
    "tort": ("侵權", "損害賠償", "184"),
    "labor": ("資遣", "勞基法", "工資"),
}


class QueryUnderstanding(TypedDict):
    raw_query: str
    masked_query: str
    normalized_query: str
    citations: list[dict[str, str]]
    issue_tags: list[str]
    intent: str


def _find_citations(text: str) -> list[dict[str, str]]:
    citations: list[dict[str, str]] = []
    compact = text.replace(" ", "")
    for pattern in (LAW_ARTICLE_RE, INTERPRETATION_RE, CONSTITUTIONAL_RE, JUDGMENT_RE):
        for match in pattern.finditer(compact):
            parsed = parse_citation(match.group(0))
            if parsed:
                citations.append(parsed)
    if citations:
        return citations
    for token in text.replace("，", " ").replace("？", " ").replace("?", " ").split():
        parsed = parse_citation(token)
        if parsed:
            citations.append(parsed)
    return citations


def _issue_tags(text: str) -> list[str]:
    tags: list[str] = []
    for tag, keywords in ISSUE_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            tags.append(tag)
    return tags


def _intent(text: str, citations: list[dict[str, str]], tags: list[str]) -> str:
    if any(item["type"].startswith("constitutional") for item in citations):
        return "constitutional"
    if "labor" in tags:
        return "labor_law"
    if any(item.get("law_name") in {"民法", "刑法"} for item in citations) or "lease_deposit" in tags:
        return "civil_law"
    return "general_legal_research"


def understand_query(query: str) -> QueryUnderstanding:
    # Names are retained in this synthetic demo because legal issue extraction may need party roles.
    # Production external-recall calls should choose a stricter masking profile.
    masked = mask_sensitive_text(query, mask_names=False)
    normalized = normalize_query(masked)
    citations = _find_citations(normalized)
    tags = _issue_tags(normalized)
    return {
        "raw_query": query,
        "masked_query": masked,
        "normalized_query": normalized,
        "citations": citations,
        "issue_tags": tags,
        "intent": _intent(normalized, citations, tags),
    }
