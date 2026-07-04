"""Resolver extension point for identifier-backed verified cache citations.

An official identifier (for example a judgment JID) may substitute for an
official URL only after a resolver maps it to a locally downloaded official
original record and the record's recomputed content hash matches the declared
``official_hash``. A deployer provides a real resolver over their own lawfully
downloaded official archive; this module ships only a synthetic in-memory
resolver so the match and mismatch paths can be demonstrated and tested
without production data.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import Protocol

from .source_policy import IdentifierResolution, SourceRecord, SourceTier

HASH_ALGORITHM = "sha256"


@dataclass(frozen=True)
class ResolvedOfficialRecord:
    """A locally stored official original record located by identifier."""

    identifier: str
    canonical_text: str
    source_label: str | None = None


class IdentifierResolver(Protocol):
    def resolve(self, identifier: str) -> ResolvedOfficialRecord | None: ...


def compute_content_hash(canonical_text: str) -> str:
    digest = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()
    return f"{HASH_ALGORITHM}:{digest}"


# Synthetic fixtures only: DEMO court code, 測 case type, future dates.
SYNTHETIC_OFFICIAL_RECORDS: dict[str, str] = {
    "DEMO,113,測,1,20990101,1": (
        '{"jid": "DEMO,113,測,1,20990101,1", '
        '"body": "本裁判為合成示範資料，僅供 harness 測試使用。"}'
    ),
}


class SyntheticIdentifierResolver:
    """Demo resolver backed by in-memory synthetic records."""

    def __init__(self, records: dict[str, str] | None = None) -> None:
        self._records = dict(SYNTHETIC_OFFICIAL_RECORDS if records is None else records)

    def resolve(self, identifier: str) -> ResolvedOfficialRecord | None:
        canonical_text = self._records.get(identifier)
        if canonical_text is None:
            return None
        return ResolvedOfficialRecord(
            identifier=identifier,
            canonical_text=canonical_text,
            source_label="synthetic-official-archive",
        )


def resolve_identifier_status(
    identifier: str,
    declared_hash: str | None,
    resolver: IdentifierResolver,
) -> IdentifierResolution:
    resolved = resolver.resolve(identifier)
    if resolved is None:
        return IdentifierResolution.UNRESOLVED
    if declared_hash == compute_content_hash(resolved.canonical_text):
        return IdentifierResolution.HASH_MATCH
    return IdentifierResolution.HASH_MISMATCH


def resolve_identifier_citation(
    source: SourceRecord, resolver: IdentifierResolver
) -> SourceRecord:
    if source.source_tier != SourceTier.VERIFIED_CACHE or not source.official_identifier:
        return source
    status = resolve_identifier_status(
        source.official_identifier, source.official_hash, resolver
    )
    return replace(source, identifier_resolution=status)
