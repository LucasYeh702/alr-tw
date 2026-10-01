"""Bounded local judgment packs authenticated by an operator-managed HMAC key.

The manifest authenticates the complete SQLite image, coverage and expiry. The
verified image is deserialized into memory so subsequent path changes cannot
change the material being queried. No network fallback is performed here.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from contextlib import closing
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from alr_tw.contracts.providers import (
    CandidateIdentity,
    ProviderCandidate,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderResult,
    ProviderResultStatus,
)
from alr_tw.contracts.sources import (
    EvidenceSectionType,
    EvidenceSpan,
    MaterialType,
    SourceRecord,
    SourceTier,
    TrustStatus,
)
from alr_tw.providers.official.judgments import OfficialJudgmentProvider
from alr_tw.config import Settings

MAX_PACK_BYTES = 256 * 1024 * 1024


def configured_pack_provider(settings: Settings):
    if settings.remote_pack_endpoint:
        from alr_tw.providers.remote_pack import RemotePackProvider
        if settings.data_pack_root or not settings.remote_pack_snapshot or not settings.data_pack_key_file:
            raise ValueError("PACK_CONFIG_INVALID")
        return RemotePackProvider(settings.remote_pack_endpoint, settings.remote_pack_snapshot,
                                  settings.data_pack_key_file)
    if settings.data_pack_root is None or settings.data_pack_key_file is None:
        raise ValueError("PACK_KEY_REQUIRED")
    provider = DataPackJudgmentProvider(
        settings.data_pack_root / "pack.sqlite",
        settings.data_pack_root / "manifest.json",
        settings.data_pack_key_file,
    )
    if provider.manifest.provenance == "synthetic_fixture":
        raise ValueError("PACK_SYNTHETIC_NOT_LIVE")
    return provider


def import_pack(path: Path, manifest: Path, key: Path, destination: Path) -> dict[str, object]:
    """Install only into a new directory; never overwrite an active pack or copy its key."""
    import shutil
    import tempfile

    # Reject bad inputs before creating any output. Revalidate the actual copy
    # too, so replacement of an input between reads cannot bless different bytes.
    DataPackJudgmentProvider(path, manifest, key)
    if destination.exists() or destination.is_symlink():
        raise ValueError("PACK_DESTINATION_EXISTS")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".pack-", dir=destination.parent))
    try:
        (temporary / "pack.sqlite").write_bytes(bounded_read(path, MAX_PACK_BYTES))
        (temporary / "manifest.json").write_bytes(bounded_read(manifest, 65536))
        provider = DataPackJudgmentProvider(
            temporary / "pack.sqlite", temporary / "manifest.json", key
        )
        # mkdir rather than replacing an existing directory after a race.
        destination.mkdir(mode=0o700)
        try:
            for name in ("pack.sqlite", "manifest.json"):
                (temporary / name).rename(destination / name)
        except OSError:
            # A partial installation remains fail-closed and is not reported as active.
            raise ValueError("PACK_INSTALL_FAILED") from None
        return {
            "installed": True,
            "snapshot_id": provider.manifest.snapshot_id,
            "record_count": provider.manifest.record_count,
            "activation": "set_ALR_TW_DATA_PACK_ROOT_and_ALR_TW_DATA_PACK_KEY_FILE",
            "coverage_complete": False,
        }
    finally:
        shutil.rmtree(temporary)


class PackManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["alr-tw.judgment-pack/v1"]
    snapshot_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,80}$")
    release_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,80}$")
    key_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,80}$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provenance: Literal["official_snapshot", "synthetic_fixture"]
    coverage_start: date
    coverage_end: date
    courts: list[str] = Field(min_length=1, max_length=100)
    record_count: int = Field(ge=1, le=100_000)
    issued_at: datetime
    expires_at: datetime
    mac: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def dates(self) -> PackManifest:
        if (
            self.issued_at.tzinfo is None
            or self.expires_at.tzinfo is None
            or self.issued_at >= self.expires_at
            or self.coverage_start > self.coverage_end
        ):
            raise ValueError("PACK_MANIFEST_INVALID")
        return self

    def authenticated_bytes(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json", exclude={"mac"}),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()


def bounded_read(path: Path, maximum: int) -> bytes:
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("PACK_FILE_INVALID")
        with path.open("rb") as stream:
            value = stream.read(maximum + 1)
        if len(value) > maximum:
            raise ValueError("PACK_FILE_TOO_LARGE")
        return value
    except OSError as exc:
        raise ValueError("PACK_FILE_INVALID") from exc


class DataPackJudgmentProvider:
    provider_id = "attested_judgment_pack"

    def __init__(
        self, path: Path, manifest_path: Path, key_path: Path, *, now: datetime | None = None
    ):
        try:
            self.manifest = PackManifest.model_validate_json(bounded_read(manifest_path, 65536))
            key = bounded_read(key_path, 4096)
            if len(key) < 32:
                raise ValueError("PACK_KEY_INVALID")
            expected = hmac.new(
                key, self.manifest.authenticated_bytes(), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(expected, self.manifest.mac):
                raise ValueError("PACK_ATTESTATION_INVALID")
            self._key_path = key_path
            self._key_digest = hashlib.sha256(key).digest()
            self._check_time(now or datetime.now(UTC))
            image = bounded_read(path, MAX_PACK_BYTES)
            if not hmac.compare_digest(hashlib.sha256(image).hexdigest(), self.manifest.sha256):
                raise ValueError("PACK_DIGEST_MISMATCH")
            with closing(sqlite3.connect(":memory:")) as db:
                db.deserialize(image)
                db.execute("PRAGMA trusted_schema=OFF")
                db.execute("PRAGMA query_only=ON")
                # Bound work even for an authenticated but malformed publisher image.
                calls = 0

                def progress() -> int:
                    nonlocal calls
                    calls += 1
                    return int(calls > 10000)

                db.set_progress_handler(progress, 1000)
                schema = db.execute("SELECT type,name FROM sqlite_master").fetchall()
                if sorted(schema) != [("table", "judgments")]:
                    raise ValueError("PACK_SCHEMA_INVALID")
                rows = db.execute(
                    "SELECT jid,title,text,section_type FROM judgments LIMIT 100001"
                ).fetchall()
            if len(rows) != self.manifest.record_count:
                raise ValueError("PACK_COUNT_MISMATCH")
            self._rows: dict[str, tuple[str, str, EvidenceSectionType]] = {}
            for jid, title, text, role in rows:
                if not all(isinstance(item, str) for item in (jid, title, text, role)):
                    raise ValueError("PACK_RECORD_INVALID")
                canonical = OfficialJudgmentProvider.normalize_jid(jid)
                if canonical != jid or jid in self._rows:
                    raise ValueError("PACK_IDENTITY_INVALID")
                parts = jid.split(",")
                judgment_date = datetime.strptime(parts[-2], "%Y%m%d").date()
                if (
                    parts[0] not in self.manifest.courts
                    or not self.manifest.coverage_start
                    <= judgment_date
                    <= self.manifest.coverage_end
                ):
                    raise ValueError("PACK_COVERAGE_MISMATCH")
                if not text.strip() or len(text) > 20000 or len(title) > 500:
                    raise ValueError("PACK_RECORD_INVALID")
                self._rows[jid] = (title, text, EvidenceSectionType(role))
        except (sqlite3.Error, TypeError, ValueError) as exc:
            code = str(exc)
            if not code.startswith("PACK_") or len(code) > 80:
                code = "PACK_INVALID"
            raise ValueError(code) from exc

    def _check_time(self, now: datetime) -> None:
        # Removing or rotating the external key revokes already-open providers.
        # The key path is operator-controlled, never supplied by MCP callers.
        try:
            current_key = bounded_read(self._key_path, 4096)
        except ValueError as exc:
            raise ValueError("PACK_TRUST_REVOKED") from exc
        if not hmac.compare_digest(hashlib.sha256(current_key).digest(), self._key_digest):
            raise ValueError("PACK_TRUST_REVOKED")
        if not self.manifest.issued_at <= now < self.manifest.expires_at:
            raise ValueError("PACK_EXPIRED_OR_NOT_YET_VALID")

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            exact_lookup=True,
            keyword_search=True,
            semantic_recall=False,
            official_verification=False,
            historical_versions=False,
            current_status_check=False,
            external_query_transfer=False,
        )

    async def health_check(self) -> ProviderHealth:
        try:
            self._check_time(datetime.now(UTC))
        except ValueError as exc:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderHealthStatus.UNAVAILABLE,
                error_code="PACK_TRUST_REVOKED" if str(exc) == "PACK_TRUST_REVOKED" else "PACK_EXPIRED",
            )
        return ProviderHealth(provider_id=self.provider_id, status=ProviderHealthStatus.HEALTHY)

    async def search(self, query: str = "", *, limit: int = 10) -> ProviderResult:
        self._check_time(datetime.now(UTC))
        if not query.strip() or len(query) > 4000 or not 1 <= limit <= 20:
            raise ValueError("PACK_QUERY_INVALID")
        candidates = [
            ProviderCandidate(
                candidate_id=f"pack_{index}",
                provider_id=self.provider_id,
                title=title,
                official_identifier=jid,
                excerpt=text[:500],
                identity=CandidateIdentity(canonical_jid=jid),
                metadata={"candidate_only": True},
            )
            for index, (jid, (title, text, _)) in enumerate(sorted(self._rows.items()))
            if query in title or query in text
        ][:limit]
        return ProviderResult(
            provider_id=self.provider_id,
            status=ProviderResultStatus.FOUND if candidates else ProviderResultStatus.NOT_FOUND,
            candidates=candidates,
            coverage_complete=False,
        )

    async def exact_lookup(
        self, identifier: str, *, now: datetime | None = None
    ) -> tuple[ProviderResult, SourceRecord | None, list[EvidenceSpan]]:
        timestamp = now or datetime.now(UTC)
        self._check_time(timestamp)
        row = self._rows.get(identifier)
        if row is None:
            return (
                ProviderResult(provider_id=self.provider_id, status=ProviderResultStatus.NOT_FOUND),
                None,
                [],
            )
        title, text, role = row
        digest = "sha256:" + hashlib.sha256(text.encode()).hexdigest()
        source_id = (
            "src_pack_"
            + hashlib.sha256(
                self.manifest.authenticated_bytes()
                + f":{identifier}:{timestamp.isoformat()}".encode()
            ).hexdigest()[:24]
        )
        source = SourceRecord(
            source_id=source_id,
            source_key=f"judgment:{identifier}",
            source_version_id=f"{self.manifest.snapshot_id}:{digest[7:23]}",
            material_type=MaterialType.JUDGMENT,
            provider_id=self.provider_id,
            source_tier=(SourceTier.SYNTHETIC if self.manifest.provenance == "synthetic_fixture"
                         else SourceTier.VERIFIED_CACHE),
            trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
            official_identifier=identifier,
            citation=title,
            title=title,
            fetched_at=timestamp,
            verified_at=timestamp,
            expires_at=self.manifest.expires_at,
            content_hash=digest,
            normalized_content_hash=digest,
            normalized_text=text,
            metadata={
                "snapshot_id": self.manifest.snapshot_id,
                "manifest_digest": hashlib.sha256(self.manifest.authenticated_bytes()).hexdigest(),
                "attestation": "hmac_sha256",
                "synthetic_fixture": self.manifest.provenance == "synthetic_fixture",
                "coverage_complete": False,
            },
        )
        span = EvidenceSpan.from_exact_text(
            evidence_id=f"ev_{source_id}",
            source_id=source_id,
            section_id="pack-section",
            section_type=role,
            exact_text=text,
            eligible_for_claim_support=True,
        )
        return (
            ProviderResult(
                provider_id=self.provider_id,
                status=ProviderResultStatus.FOUND,
                source_ids=[source_id],
                evidence_ids=[span.evidence_id],
                metadata={"verified_cache": self.manifest.provenance == "official_snapshot",
                          "snapshot_id": self.manifest.snapshot_id},
            ),
            source,
            [span],
        )
