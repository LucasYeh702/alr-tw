from __future__ import annotations


def requires_official_verification(source_tier: str) -> bool:
    return source_tier in {"staging", "verified_cache"}
