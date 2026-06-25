from __future__ import annotations

from .query_normalizer import SYNTHETIC_SYNONYMS


def lookup_synonym(term: str) -> str | None:
    return SYNTHETIC_SYNONYMS.get(term)
