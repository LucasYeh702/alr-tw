"""Fail-closed verification facade for parsed judgment semantics."""

from __future__ import annotations

from collections.abc import Sequence

from alr_tw.contracts.judgment_semantics import (
    JudgmentSemanticsContract,
    JudgmentSemanticsValidationResult,
    validate_judgment_semantics,
)


def validate_server_judgment_semantics(
    contract: JudgmentSemanticsContract,
    *,
    server_run_id: str,
    server_source_ids: Sequence[str],
    server_evidence_ids: Sequence[str],
) -> JudgmentSemanticsValidationResult:
    """Validate parser output against server-owned refs for one run."""

    return validate_judgment_semantics(
        contract,
        server_run_id=server_run_id,
        server_source_ids=server_source_ids,
        server_evidence_ids=server_evidence_ids,
    )


__all__ = ["validate_server_judgment_semantics"]
