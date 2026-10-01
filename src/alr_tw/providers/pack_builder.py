"""Build immutable local packs from an explicitly curated operator export."""
from __future__ import annotations

import hashlib
import hmac
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from alr_tw.contracts.sources import EvidenceSectionType
from alr_tw.providers.data_pack import (
    MAX_PACK_BYTES, DataPackJudgmentProvider, PackManifest, bounded_read, import_pack,
)


class PackRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    jid: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=20000)
    section_type: EvidenceSectionType


class PackExport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snapshot_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,80}$")
    release_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,80}$")
    key_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,80}$")
    provenance: Literal["official_snapshot", "synthetic_fixture"]
    issued_at: datetime
    expires_at: datetime
    records: list[PackRecord] = Field(min_length=1, max_length=100000)


def build_pack(export_path: Path, key_path: Path, destination: Path) -> dict[str, object]:
    """Validate before installation; inputs and keys are never copied to the package."""
    try:
        export = PackExport.model_validate_json(bounded_read(export_path, MAX_PACK_BYTES))
    except ValueError as exc:
        raise ValueError("PACK_EXPORT_INVALID") from exc
    key = bounded_read(key_path, 4096)
    if len(key) < 32:
        raise ValueError("PACK_KEY_INVALID")
    if destination.exists() or destination.is_symlink():
        raise ValueError("PACK_DESTINATION_EXISTS")
    rows = sorted(export.records, key=lambda item: item.jid)
    try:
        dates = [datetime.strptime(item.jid.split(",")[-2], "%Y%m%d").date() for item in rows]
        manifest = PackManifest(
            schema_version="alr-tw.judgment-pack/v1",
            snapshot_id=export.snapshot_id, release_id=export.release_id, key_id=export.key_id,
            provenance=export.provenance, sha256="0" * 64, mac="0" * 64,
            coverage_start=min(dates), coverage_end=max(dates),
            courts=sorted({item.jid.split(",")[0] for item in rows}), record_count=len(rows),
            issued_at=export.issued_at, expires_at=export.expires_at,
        )
    except (ValueError, IndexError) as exc:
        raise ValueError("PACK_EXPORT_INVALID") from exc
    with tempfile.TemporaryDirectory(prefix="alr-pack-build-") as temporary:
        root = Path(temporary)
        database = root / "pack.sqlite"
        metadata = root / "manifest.json"
        with sqlite3.connect(database) as db:
            db.execute("CREATE TABLE judgments(jid TEXT,title TEXT,text TEXT,section_type TEXT)")
            db.executemany("INSERT INTO judgments VALUES (?,?,?,?)", [
                (item.jid, item.title, item.text, item.section_type.value) for item in rows
            ])
        manifest = manifest.model_copy(update={
            "sha256": hashlib.sha256(bounded_read(database, MAX_PACK_BYTES)).hexdigest(),
        })
        manifest = manifest.model_copy(update={
            "mac": hmac.new(key, manifest.authenticated_bytes(), hashlib.sha256).hexdigest(),
        })
        metadata.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        DataPackJudgmentProvider(database, metadata, key_path)
        result = import_pack(database, metadata, key_path, destination)
    # Aggregate only: no judgment IDs, text, paths, or keys in the receipt.
    return {
        **result, "sha256": manifest.sha256, "provenance": manifest.provenance,
        "quality": {"identity_unique": True, "coverage_consistent": True,
                    "record_schema_valid": True, "legal_accuracy_verified": False},
        "update_policy": "new_directory_then_explicit_activation_keep_previous_for_rollback",
    }


def inspect_pack(root: Path, key_path: Path) -> dict[str, object]:
    provider = DataPackJudgmentProvider(root / "pack.sqlite", root / "manifest.json", key_path)
    manifest = provider.manifest
    return {
        "valid": True, "snapshot_id": manifest.snapshot_id, "release_id": manifest.release_id,
        "sha256": manifest.sha256, "provenance": manifest.provenance,
        "record_count": manifest.record_count, "court_count": len(manifest.courts),
        "coverage_start": manifest.coverage_start.isoformat(),
        "coverage_end": manifest.coverage_end.isoformat(),
        "expires_at": manifest.expires_at.isoformat(), "coverage_complete": False,
        "legal_accuracy_verified": False,
    }
