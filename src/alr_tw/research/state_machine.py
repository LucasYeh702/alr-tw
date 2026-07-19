"""Allowed server-owned research state transitions."""

from __future__ import annotations

from datetime import datetime

from alr_tw.contracts.research import ResearchRun, ResearchState


class InvalidResearchTransition(ValueError):
    pass


ALLOWED_TRANSITIONS: dict[ResearchState, frozenset[ResearchState]] = {
    ResearchState.CREATED: frozenset({ResearchState.PLANNING, ResearchState.PURGED}),
    ResearchState.PLANNING: frozenset({ResearchState.RESEARCHING, ResearchState.PURGED}),
    ResearchState.RESEARCHING: frozenset(
        {ResearchState.VERIFYING, ResearchState.BLOCKED, ResearchState.PURGED}
    ),
    ResearchState.VERIFYING: frozenset(
        {ResearchState.READY_FOR_DRAFT, ResearchState.BLOCKED, ResearchState.PURGED}
    ),
    ResearchState.READY_FOR_DRAFT: frozenset(
        {ResearchState.VALIDATING, ResearchState.PURGED}
    ),
    ResearchState.VALIDATING: frozenset(
        {
            ResearchState.VALIDATED,
            ResearchState.QUALIFIED,
            ResearchState.BLOCKED,
            ResearchState.PURGED,
        }
    ),
    ResearchState.VALIDATED: frozenset({ResearchState.EXPIRED}),
    ResearchState.QUALIFIED: frozenset({ResearchState.EXPIRED}),
    ResearchState.BLOCKED: frozenset({ResearchState.EXPIRED}),
    ResearchState.PURGED: frozenset(),
    ResearchState.EXPIRED: frozenset(),
}


def transition_run(
    run: ResearchRun,
    target: ResearchState,
    *,
    updated_at: datetime,
) -> ResearchRun:
    if target == run.state:
        return run.model_copy(update={"updated_at": updated_at})
    if target not in ALLOWED_TRANSITIONS[run.state]:
        raise InvalidResearchTransition(f"invalid research transition: {run.state} -> {target}")
    return run.model_copy(update={"state": target, "updated_at": updated_at})
