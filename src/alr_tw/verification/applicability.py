"""Fail-closed verification facade for applicability resolutions.

The resolver and contracts remain provider-neutral.  This module gives MCP
adapters a stable verification import without making callers import the
contract implementation details directly.
"""

from __future__ import annotations

from collections.abc import Sequence

from alr_tw.contracts.applicability import (
    ApplicabilityRequest,
    ApplicabilityResolution,
    ApplicabilitySourceRecord,
    ApplicabilityValidationResult,
    validate_applicability_resolution as _validate_applicability_resolution,
)


def validate_applicability_resolution(
    resolution: ApplicabilityResolution,
    *,
    request: ApplicabilityRequest,
    server_sources: Sequence[ApplicabilitySourceRecord],
    server_source_ids: Sequence[str] | None = None,
) -> ApplicabilityValidationResult:
    """Recompute applicability against an independent server catalog binding."""

    return _validate_applicability_resolution(
        resolution,
        request=request,
        server_sources=server_sources,
        server_source_ids=server_source_ids,
    )


validate_applicability = validate_applicability_resolution


__all__ = ["validate_applicability", "validate_applicability_resolution"]
