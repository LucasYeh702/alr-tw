"""Context-local request accounting and cancellable provider time limits."""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass
from time import monotonic
from typing import Any, Callable, Coroutine, TypeVar

from alr_tw.contracts.budget import ResearchBudget

_T = TypeVar('_T')


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class BudgetScope:
    budget: ResearchBudget
    deadline: float
    persist: Callable[[ResearchBudget], None]

    def check(self) -> float:
        if self.budget.exhausted_reason:
            raise BudgetExceeded(self.budget.exhausted_reason)
        remaining = self.deadline - monotonic()
        if remaining <= 0:
            self.exhaust('TIMEOUT_BUDGET_EXHAUSTED')
        return remaining

    def exhaust(self, reason: str) -> None:
        self.budget = self.budget.model_copy(update={'exhausted_reason': reason})
        self.persist(self.budget)
        raise BudgetExceeded(reason)

    def request(self) -> None:
        self.check()
        if self.budget.used_http_requests >= self.budget.max_http_requests:
            self.exhaust('HTTP_BUDGET_EXHAUSTED')
        self.budget = self.budget.model_copy(update={
            'used_http_requests': self.budget.used_http_requests + 1,
        })
        # Charge before I/O, including failed attempts and redirects.
        self.persist(self.budget)


ACTIVE_BUDGET: ContextVar[BudgetScope | None] = ContextVar('research_budget', default=None)


def charge_http_request() -> None:
    scope = ACTIVE_BUDGET.get()
    if scope is not None:
        scope.request()


async def bounded_provider(coroutine: Coroutine[Any, Any, _T]) -> _T:
    scope = ACTIVE_BUDGET.get()
    if scope is None:
        return await coroutine
    try:
        remaining = scope.check()
    except BudgetExceeded:
        coroutine.close()
        raise
    timer = asyncio.timeout(remaining)
    try:
        async with timer:
            result = await coroutine
        scope.check()
        return result
    except TimeoutError:
        if timer.expired():
            scope.exhaust('TIMEOUT_BUDGET_EXHAUSTED')
        raise
