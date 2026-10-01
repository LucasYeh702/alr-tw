"""Read-only authoritative-text projection using existing TTL-managed sources."""

from datetime import UTC, datetime
from dataclasses import asdict

from alr_tw.contracts.sources import TrustStatus
from alr_tw.storage.sqlite_store import SqliteStore
from alr_tw.verification.output_privacy import screen_answer_output
from alr_tw.verification.text_projection import locate_quote


def map_source_quote(store: SqliteStore, run_id: str, source_id: str, query: str) -> dict:
    now = datetime.now(UTC)
    run = store.get_run(run_id)
    if run is None or run.expires_at <= now:
        raise ValueError("RESEARCH_RUN_EXPIRED")
    source = next((s for s in store.list_sources(run_id) if s.source_id == source_id), None)
    if (
        source is None
        or source.expires_at <= now
        or source.trust_status != TrustStatus.EVIDENCE_ELIGIBLE
    ):
        raise ValueError("QUOTE_SOURCE_NOT_ELIGIBLE")
    match = locate_quote(source.normalized_text, query)
    if match and not screen_answer_output(match.exact_text).allowed:
        raise ValueError("ANSWER_CONTAINS_SENSITIVE_DATA")
    return {
        "source_id": source_id,
        "source_version_id": source.source_version_id,
        "status": "unique" if match else "unresolved",
        "quote": asdict(match) if match else None,
        "authority_layer": "verified_normalized_text",
        "source_content_hash": source.content_hash,
        "evidence_minting_authorized": False,
        "final_answer_authorized": False,
    }
