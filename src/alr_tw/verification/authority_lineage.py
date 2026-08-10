"""Verification facade for provider-neutral authority/lineage records."""

from __future__ import annotations

from collections.abc import Sequence

from alr_tw.contracts.authority_lineage import (
    AuthorityLineageContract,
    AuthorityLineageValidationResult,
    validate_authority_lineage,
)


def validate_server_authority_lineage(
    contract: AuthorityLineageContract,
    *,
    server_run_id: str,
    server_source_ids: Sequence[str],
    server_evidence_ids: Sequence[str],
) -> AuthorityLineageValidationResult:
    """Validate lineage against server-owned refs for one research run."""

    return validate_authority_lineage(
        contract,
        server_run_id=server_run_id,
        server_source_ids=server_source_ids,
        server_evidence_ids=server_evidence_ids,
    )


__all__ = ["validate_server_authority_lineage"]
