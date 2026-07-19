"""Shared synchronous purge service for CLI and MCP."""

from __future__ import annotations

from alr_tw.contracts.storage import PurgeResult

from .sqlite_store import SqliteStore


class PurgeService:
    def __init__(self, store: SqliteStore):
        self.store = store

    def purge(
        self,
        scope: str,
        *,
        run_id: str | None = None,
        confirmed: bool = False,
    ) -> PurgeResult:
        if not confirmed:
            raise ValueError("PURGE_CONFIRMATION_REQUIRED")
        if scope == "run":
            if not run_id or not run_id.strip():
                raise ValueError("run_id is required for run purge")
            return self.store.purge_run(run_id.strip())
        if scope == "all":
            if run_id is not None:
                raise ValueError("run_id is not allowed for all purge")
            return self.store.purge_all()
        raise ValueError("scope must be run or all")
