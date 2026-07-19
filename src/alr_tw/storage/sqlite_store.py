"""Transactional SQLite store for short-lived research state and evidence."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import sqlite3
from threading import RLock
from typing import Any

from alr_tw.contracts.providers import ProviderCandidate
from alr_tw.contracts.research import ResearchRun
from alr_tw.contracts.sources import EvidenceSpan, SourceRecord
from alr_tw.contracts.storage import CleanupResult, OperationRecordResult, PurgeResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS research_runs (
    run_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS research_obligations (
    run_id TEXT NOT NULL REFERENCES research_runs(run_id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (run_id, kind)
);

CREATE TABLE IF NOT EXISTS operations (
    run_id TEXT NOT NULL REFERENCES research_runs(run_id) ON DELETE CASCADE,
    operation_id TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (run_id, operation_id)
);

CREATE TABLE IF NOT EXISTS source_records (
    source_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_sources (
    run_id TEXT NOT NULL REFERENCES research_runs(run_id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES source_records(source_id) ON DELETE CASCADE,
    PRIMARY KEY (run_id, source_id)
);

CREATE TABLE IF NOT EXISTS evidence_spans (
    evidence_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES research_runs(run_id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES source_records(source_id) ON DELETE CASCADE,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (run_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS retrieval_candidates (
    run_id TEXT NOT NULL REFERENCES research_runs(run_id) ON DELETE CASCADE,
    candidate_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY (run_id, candidate_id)
);

CREATE TABLE IF NOT EXISTS cache_entries (
    cache_key TEXT PRIMARY KEY,
    source_id TEXT REFERENCES source_records(source_id) ON DELETE CASCADE,
    payload_json TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_research_runs_expires ON research_runs(expires_at);
CREATE INDEX IF NOT EXISTS idx_source_records_expires ON source_records(expires_at);
CREATE INDEX IF NOT EXISTS idx_evidence_run ON evidence_spans(run_id);
"""


def _json_dump(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class SqliteStore:
    """Single-user managed store with transaction-scoped connections."""

    def __init__(self, root_path: Path | str):
        self.root_path = Path(root_path)
        self.database_path = self.root_path / "alr_tw_storage.sqlite3"
        self.temp_path = self.root_path / "tmp"
        self._lock = RLock()
        with self._connection():
            pass

    def _prepare_paths(self) -> None:
        self.root_path.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root_path, 0o700)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._prepare_paths()
            connection = sqlite3.connect(self.database_path, timeout=10.0)
            try:
                os.chmod(self.database_path, 0o600)
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute("PRAGMA secure_delete = ON")
                connection.execute("PRAGMA journal_mode = WAL")
                connection.executescript(_SCHEMA)
                connection.commit()
                yield connection
            finally:
                connection.close()

    def save_run(self, run: ResearchRun) -> None:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO research_runs(run_id, payload_json, created_at, updated_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at,
                    expires_at = excluded.expires_at
                """,
                (
                    run.run_id,
                    run.model_dump_json(),
                    run.created_at.isoformat(),
                    run.updated_at.isoformat(),
                    run.expires_at.isoformat(),
                ),
            )
            connection.execute("DELETE FROM research_obligations WHERE run_id = ?", (run.run_id,))
            connection.executemany(
                """
                INSERT INTO research_obligations(run_id, kind, payload_json)
                VALUES (?, ?, ?)
                """,
                [
                    (run.run_id, obligation.kind.value, obligation.model_dump_json())
                    for obligation in run.obligations
                ],
            )
            connection.commit()

    def get_run(self, run_id: str) -> ResearchRun | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM research_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return ResearchRun.model_validate_json(row["payload_json"]) if row else None

    def save_source(self, run_id: str, source: SourceRecord) -> None:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_run(connection, run_id)
            existing = connection.execute(
                "SELECT payload_json FROM source_records WHERE source_id = ?",
                (source.source_id,),
            ).fetchone()
            if existing is not None and existing["payload_json"] != source.model_dump_json():
                raise ValueError("source_id is immutable and already has different content")
            connection.execute(
                """
                INSERT INTO source_records(source_id, payload_json, expires_at)
                VALUES (?, ?, ?)
                ON CONFLICT(source_id) DO NOTHING
                """,
                (source.source_id, source.model_dump_json(), source.expires_at.isoformat()),
            )
            connection.execute(
                "INSERT OR IGNORE INTO run_sources(run_id, source_id) VALUES (?, ?)",
                (run_id, source.source_id),
            )
            connection.commit()

    def get_source(self, source_id: str) -> SourceRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM source_records WHERE source_id = ?", (source_id,)
            ).fetchone()
        return SourceRecord.model_validate_json(row["payload_json"]) if row else None

    def list_sources(self, run_id: str) -> list[SourceRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT source_records.payload_json
                FROM source_records
                JOIN run_sources USING (source_id)
                WHERE run_sources.run_id = ?
                ORDER BY source_records.source_id
                """,
                (run_id,),
            ).fetchall()
        return [SourceRecord.model_validate_json(row["payload_json"]) for row in rows]

    def save_evidence(self, run_id: str, evidence: EvidenceSpan) -> None:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_run(connection, run_id)
            linked = connection.execute(
                "SELECT 1 FROM run_sources WHERE run_id = ? AND source_id = ?",
                (run_id, evidence.source_id),
            ).fetchone()
            if linked is None:
                raise ValueError("evidence source must be linked to the research run")
            existing = connection.execute(
                """SELECT payload_json FROM evidence_spans
                   WHERE run_id = ? AND evidence_id = ?""",
                (run_id, evidence.evidence_id),
            ).fetchone()
            if existing is not None and existing["payload_json"] != evidence.model_dump_json():
                raise ValueError("evidence_id is immutable and already has different content")
            connection.execute(
                """
                INSERT INTO evidence_spans(evidence_id, run_id, source_id, payload_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(run_id, evidence_id) DO NOTHING
                """,
                (evidence.evidence_id, run_id, evidence.source_id, evidence.model_dump_json()),
            )
            connection.commit()

    def get_evidence(self, evidence_id: str, *, run_id: str | None = None) -> EvidenceSpan | None:
        with self._connection() as connection:
            if run_id is None:
                row = connection.execute(
                    """SELECT payload_json FROM evidence_spans
                       WHERE evidence_id = ? ORDER BY run_id LIMIT 1""",
                    (evidence_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    """SELECT payload_json FROM evidence_spans
                       WHERE run_id = ? AND evidence_id = ?""",
                    (run_id, evidence_id),
                ).fetchone()
        return EvidenceSpan.model_validate_json(row["payload_json"]) if row else None

    def save_cache_entry(
        self,
        cache_key: str,
        source: SourceRecord,
        evidence: list[EvidenceSpan],
    ) -> None:
        """Cache a verified snapshot already persisted by at least one run."""

        if not cache_key.strip():
            raise ValueError("cache_key is required")
        if any(item.source_id != source.source_id for item in evidence):
            raise ValueError("cached evidence must belong to the cached source")
        payload = {"evidence": [item.model_dump(mode="json") for item in evidence]}
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            exists = connection.execute(
                "SELECT 1 FROM source_records WHERE source_id = ?",
                (source.source_id,),
            ).fetchone()
            if exists is None:
                raise ValueError("cached source must be persisted before cache linkage")
            connection.execute(
                """
                INSERT INTO cache_entries(cache_key, source_id, payload_json, expires_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    source_id = excluded.source_id,
                    payload_json = excluded.payload_json,
                    expires_at = excluded.expires_at
                """,
                (
                    cache_key,
                    source.source_id,
                    _json_dump(payload),
                    source.expires_at.isoformat(),
                ),
            )
            connection.commit()

    def get_fresh_cache_entry(
        self,
        cache_key: str,
        *,
        now: datetime | None = None,
    ) -> tuple[SourceRecord, list[EvidenceSpan]] | None:
        cutoff = (now or datetime.now(UTC)).isoformat()
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT source_records.payload_json AS source_json,
                       cache_entries.payload_json AS cache_json
                FROM cache_entries
                JOIN source_records USING (source_id)
                WHERE cache_entries.cache_key = ?
                  AND cache_entries.expires_at > ?
                  AND source_records.expires_at > ?
                """,
                (cache_key, cutoff, cutoff),
            ).fetchone()
        if row is None:
            return None
        source = SourceRecord.model_validate_json(row["source_json"])
        payload = json.loads(row["cache_json"])
        evidence = [EvidenceSpan.model_validate(item) for item in payload.get("evidence", [])]
        if any(item.source_id != source.source_id for item in evidence):
            raise ValueError("cached evidence/source mismatch")
        return source, evidence

    def has_cache_entry(self, cache_key: str) -> bool:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT 1 FROM cache_entries WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        return row is not None

    def list_evidence(self, run_id: str) -> list[EvidenceSpan]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM evidence_spans
                WHERE run_id = ? ORDER BY evidence_id
                """,
                (run_id,),
            ).fetchall()
        return [EvidenceSpan.model_validate_json(row["payload_json"]) for row in rows]

    def save_candidate(
        self,
        run_id: str,
        candidate: ProviderCandidate,
        *,
        expires_at: datetime,
    ) -> None:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_run(connection, run_id)
            existing = connection.execute(
                """SELECT payload_json FROM retrieval_candidates
                   WHERE run_id = ? AND candidate_id = ?""",
                (run_id, candidate.candidate_id),
            ).fetchone()
            if existing is not None and existing["payload_json"] != candidate.model_dump_json():
                raise ValueError("candidate_id is immutable and already has different content")
            connection.execute(
                """
                INSERT INTO retrieval_candidates(candidate_id, run_id, payload_json, expires_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(run_id, candidate_id) DO NOTHING
                """,
                (
                    candidate.candidate_id,
                    run_id,
                    candidate.model_dump_json(),
                    expires_at.isoformat(),
                ),
            )
            connection.commit()

    def list_candidates(self, run_id: str) -> list[ProviderCandidate]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM retrieval_candidates
                WHERE run_id = ? ORDER BY candidate_id
                """,
                (run_id,),
            ).fetchall()
        return [ProviderCandidate.model_validate_json(row["payload_json"]) for row in rows]

    def record_operation(
        self,
        run_id: str,
        operation_id: str,
        result: dict[str, Any],
    ) -> OperationRecordResult:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_run(connection, run_id)
            row = connection.execute(
                "SELECT result_json FROM operations WHERE run_id = ? AND operation_id = ?",
                (run_id, operation_id),
            ).fetchone()
            if row is not None:
                connection.commit()
                return OperationRecordResult(created=False, result=json.loads(row["result_json"]))
            connection.execute(
                """
                INSERT INTO operations(run_id, operation_id, result_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, operation_id, _json_dump(result), datetime.now(UTC).isoformat()),
            )
            connection.commit()
            return OperationRecordResult(created=True, result=result)

    def complete_operation(
        self,
        run_id: str,
        operation_id: str,
        result: dict[str, Any],
    ) -> OperationRecordResult:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE operations
                SET result_json = ?
                WHERE run_id = ? AND operation_id = ?
                """,
                (_json_dump(result), run_id, operation_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"operation not found: {run_id}/{operation_id}")
            connection.commit()
        return OperationRecordResult(created=True, result=result)

    def cleanup_expired(self, *, now: datetime | None = None) -> CleanupResult:
        cutoff = (now or datetime.now(UTC)).isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            expired_runs = connection.execute(
                "SELECT COUNT(*) FROM research_runs WHERE expires_at <= ?", (cutoff,)
            ).fetchone()[0]
            connection.execute("DELETE FROM research_runs WHERE expires_at <= ?", (cutoff,))
            before_sources = connection.execute("SELECT COUNT(*) FROM source_records").fetchone()[0]
            connection.execute(
                """
                DELETE FROM source_records
                WHERE expires_at <= ?
                   OR NOT EXISTS (
                       SELECT 1 FROM run_sources WHERE run_sources.source_id = source_records.source_id
                   )
                """,
                (cutoff,),
            )
            after_sources = connection.execute("SELECT COUNT(*) FROM source_records").fetchone()[0]
            connection.execute("DELETE FROM cache_entries WHERE expires_at <= ?", (cutoff,))
            connection.execute(
                "DELETE FROM retrieval_candidates WHERE expires_at <= ?", (cutoff,)
            )
            connection.commit()
        return CleanupResult(
            expired_runs=int(expired_runs),
            deleted_sources=int(before_sources - after_sources),
        )

    def purge_run(self, run_id: str) -> PurgeResult:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            exists = connection.execute(
                "SELECT 1 FROM research_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if exists is None:
                connection.commit()
                return PurgeResult(success=True, scope="run", already_absent=True)
            before_sources = connection.execute("SELECT COUNT(*) FROM source_records").fetchone()[0]
            connection.execute("DELETE FROM research_runs WHERE run_id = ?", (run_id,))
            connection.execute(
                """
                DELETE FROM source_records
                WHERE NOT EXISTS (
                    SELECT 1 FROM run_sources WHERE run_sources.source_id = source_records.source_id
                )
                """
            )
            after_sources = connection.execute("SELECT COUNT(*) FROM source_records").fetchone()[0]
            connection.commit()
        return PurgeResult(
            success=True,
            scope="run",
            deleted_runs=1,
            deleted_sources=int(before_sources - after_sources),
        )

    def purge_all(self) -> PurgeResult:
        failures: list[str] = []
        with self._lock:
            for path in (
                self.database_path,
                Path(f"{self.database_path}-wal"),
                Path(f"{self.database_path}-shm"),
            ):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    failures.append(path.name)
            try:
                if self.temp_path.exists():
                    shutil.rmtree(self.temp_path)
            except OSError:
                failures.append("tmp")
        return PurgeResult(
            success=not failures,
            scope="all",
            failures=failures,
            error_code="PURGE_PARTIAL_FAILURE" if failures else None,
        )

    @staticmethod
    def _require_run(connection: sqlite3.Connection, run_id: str) -> None:
        exists = connection.execute(
            "SELECT 1 FROM research_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if exists is None:
            raise KeyError(f"research run not found: {run_id}")
