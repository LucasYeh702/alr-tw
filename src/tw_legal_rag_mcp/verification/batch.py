from __future__ import annotations

from typing import Any

from .citation_validator import validate_citation
from .source_policy import CitationUse


def run_source_verification_batch(records: list[dict[str, Any]]) -> dict[str, object]:
    deduped: dict[str, dict[str, Any]] = {}
    for record in records:
        source_id = str(record.get("source_id") or record.get("citation_id") or "")
        if source_id and source_id not in deduped:
            deduped[source_id] = record

    validations = [
        validate_citation({"citation_id": source_id, **record}, require_final=True)
        for source_id, record in sorted(deduped.items())
    ]
    final_source_ids = [
        item["citation_id"]
        for item in validations
        if item["citation_use"] == CitationUse.ALLOW_FINAL.value
    ]
    candidate_only_count = sum(
        1 for item in validations if item["citation_use"] == CitationUse.ALLOW_CANDIDATE_ONLY.value
    )

    return {
        "input_count": len(records),
        "deduped_count": len(deduped),
        "allow_final_count": len(final_source_ids),
        "candidate_only_count": candidate_only_count,
        "final_source_ids": final_source_ids,
        "production_data": "not_used",
        "validations": validations,
    }
