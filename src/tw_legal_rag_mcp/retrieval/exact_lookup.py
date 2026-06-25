from __future__ import annotations

from typing import Any

from ..verification.citation_validator import validate_citation


SYNTHETIC_LAWS = {
    ("示範租賃規則", "第1條"): {
        "citation_id": "demo-law-001",
        "source_id": "demo-law-001",
        "source_tier": "synthetic",
        "title": "示範租賃規則",
        "article_no": "第1條",
    }
}

SYNTHETIC_JUDGMENTS = {
    "DEMO,001,民,1,20260101,1": {
        "citation_id": "demo-judgment-001",
        "source_id": "demo-judgment-001",
        "source_tier": "synthetic",
        "jid": "DEMO,001,民,1,20260101,1",
    }
}

SYNTHETIC_CONSTITUTIONAL = {
    "demo-constitutional-001": {
        "citation_id": "demo-constitutional-001",
        "source_id": "demo-constitutional-001",
        "source_tier": "synthetic",
    }
}


def _with_validation(record: dict[str, Any] | None) -> dict[str, Any]:
    if record is None:
        return {"status": "not_found", "citation_use": "reject", "source_tier": "unknown"}
    validation = validate_citation(record)
    return {**record, **validation}


def exact_law_lookup(title: str, article_no: str) -> dict[str, Any]:
    return _with_validation(SYNTHETIC_LAWS.get((title, article_no)))


def exact_judgment_lookup(jid: str) -> dict[str, Any]:
    return _with_validation(SYNTHETIC_JUDGMENTS.get(jid))


def exact_constitutional_lookup(source_id: str) -> dict[str, Any]:
    return _with_validation(SYNTHETIC_CONSTITUTIONAL.get(source_id))
