"""Unified research storage policy contracts."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StorageMode(str, Enum):
    EPHEMERAL = "ephemeral"
    TIMED = "timed"


class StoragePolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: StorageMode = StorageMode.TIMED
    retention_seconds: int = Field(default=86400, gt=0, le=7 * 24 * 60 * 60)
    purge_on_request: bool = True
    cleanup_on_expiry: bool = True


class OperationRecordResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    created: bool
    result: dict[str, Any]


class CleanupResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    expired_runs: int = 0
    deleted_sources: int = 0


class PurgeResult(BaseModel):
    """Ephemeral purge response; callers must not persist it in the managed store."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    success: bool
    scope: str
    already_absent: bool = False
    deleted_runs: int = 0
    deleted_sources: int = 0
    failures: list[str] = Field(default_factory=list)
    error_code: str | None = None
