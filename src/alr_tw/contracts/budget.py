"""Persisted, server-owned limits for research advancement."""
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class ResearchBudget(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_seconds: float = Field(default=120, gt=0, le=3600, allow_inf_nan=False)
    max_http_requests: int = Field(default=50, ge=1, le=1000, strict=True)
    deadline_at: AwareDatetime | None = None
    used_http_requests: int = Field(default=0, ge=0, strict=True)
    exhausted_reason: str | None = None
    # Drafting/model calls belong to the external client; unknown is not zero.
    used_total_tokens: int | None = None

    def remaining(self, now: datetime) -> float:
        return self.max_seconds if self.deadline_at is None else max(
            0.0, min(self.max_seconds, (self.deadline_at - now).total_seconds())
        )
