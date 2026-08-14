"""Fail-closed verification facade for historical-law resolutions."""

from __future__ import annotations

from collections.abc import Collection
from datetime import datetime

from alr_tw.contracts.historical_law import (
    HistoricalLawResolution,
    HistoricalLawValidationResult,
    validate_historical_law_resolution,
)
from alr_tw.contracts.public_law import PublicLawServerMetadata


def validate_server_historical_law(
    resolution: HistoricalLawResolution,
    *,
    server_metadata: PublicLawServerMetadata | None,
    server_source_ids: Collection[str] | None,
    now: datetime | None = None,
) -> HistoricalLawValidationResult:
    """Validate a provider response against server-owned snapshot/source refs."""

    return validate_historical_law_resolution(
        resolution,
        server_metadata=server_metadata,
        server_source_ids=server_source_ids,
        now=now,
    )


__all__ = ["validate_server_historical_law"]
