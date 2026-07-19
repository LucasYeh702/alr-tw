from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from alr_tw.contracts.providers import DataMode, ProviderCandidate
from alr_tw.contracts.research import (
    CoverageState,
    PrivacyStatus,
    ResearchDepth,
    ResearchObligation,
    ResearchObligationKind,
    ResearchRun,
    ResearchState,
)
from alr_tw.contracts.sources import (
    EvidenceSpan,
    MaterialType,
    SourceRecord,
    SourceTier,
    TrustStatus,
)
from alr_tw.storage.sqlite_store import SqliteStore


def _run(run_id: str, *, now: datetime, expires_at: datetime | None = None) -> ResearchRun:
    return ResearchRun(
        run_id=run_id,
        query="民法第184條",
        created_at=now,
        updated_at=now,
        expires_at=expires_at or now + timedelta(hours=24),
        requested_mode=DataMode.OFFICIAL_ONLY,
        effective_mode=DataMode.OFFICIAL_ONLY,
        research_depth=ResearchDepth.STANDARD,
        as_of_date=date(2026, 7, 19),
        privacy_status=PrivacyStatus.NOT_REQUIRED,
        state=ResearchState.CREATED,
        obligations=[
            ResearchObligation(kind=ResearchObligationKind.QUERY_UNDERSTANDING)
        ],
        coverage=CoverageState(),
    )


def _source(source_id: str, *, now: datetime) -> SourceRecord:
    text = "合成官方法規內容"
    digest = EvidenceSpan.hash_text(text)
    return SourceRecord(
        source_id=source_id,
        source_key=f"law:{source_id}",
        source_version_id=f"law:{source_id}:v1",
        material_type=MaterialType.LAW,
        provider_id="synthetic-official",
        source_tier=SourceTier.OFFICIAL,
        trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
        official_identifier=f"synthetic-{source_id}",
        official_url=f"https://example.test/law/{source_id}",
        citation="合成法規第1條",
        fetched_at=now,
        verified_at=now,
        expires_at=now + timedelta(hours=24),
        content_hash=digest,
        normalized_content_hash=digest,
        normalized_text=text,
    )


def _evidence(evidence_id: str, source_id: str) -> EvidenceSpan:
    return EvidenceSpan.from_exact_text(
        evidence_id=evidence_id,
        source_id=source_id,
        section_id="article-1",
        section_type="law_text",
        exact_text="合成官方法規內容",
        eligible_for_claim_support=True,
    )


def test_store_round_trips_run_source_evidence_and_idempotent_operation(tmp_path: Path):
    now = datetime.now(UTC)
    store = SqliteStore(tmp_path / "cache")
    run = _run("run_1", now=now)
    source = _source("source_1", now=now)

    store.save_run(run)
    store.save_source(run.run_id, source)
    store.save_evidence(run.run_id, _evidence("evidence_1", source.source_id))
    first = store.record_operation(run.run_id, "operation_1", {"step": "planning"})
    repeated = store.record_operation(run.run_id, "operation_1", {"step": "different"})

    assert store.get_run(run.run_id) == run
    assert store.get_source(source.source_id) == source
    stored_evidence = store.get_evidence("evidence_1")
    assert stored_evidence is not None
    assert stored_evidence.source_id == source.source_id
    assert first.created is True
    assert repeated.created is False
    assert repeated.result == {"step": "planning"}
    assert store.database_path.stat().st_mode & 0o077 == 0


def test_source_and_evidence_ids_are_immutable(tmp_path: Path):
    now = datetime.now(UTC)
    store = SqliteStore(tmp_path / "cache")
    run = _run("run_1", now=now)
    source = _source("source_1", now=now)
    store.save_run(run)
    store.save_source(run.run_id, source)
    evidence = _evidence("evidence_1", source.source_id)
    store.save_evidence(run.run_id, evidence)

    changed_source = source.model_copy(update={"normalized_text": "變造內容"})
    changed_evidence = evidence.model_copy(update={"section_id": "different"})

    with pytest.raises(ValueError, match="immutable"):
        store.save_source(run.run_id, changed_source)
    with pytest.raises(ValueError, match="immutable"):
        store.save_evidence(run.run_id, changed_evidence)


def test_purge_run_keeps_shared_source_until_last_reference_is_removed(tmp_path: Path):
    now = datetime.now(UTC)
    store = SqliteStore(tmp_path / "cache")
    source = _source("shared", now=now)

    for run_id in ("run_1", "run_2"):
        store.save_run(_run(run_id, now=now))
        store.save_source(run_id, source)
        store.save_evidence(run_id, _evidence(f"evidence_{run_id}", source.source_id))

    first = store.purge_run("run_1")
    assert first.success is True
    assert store.get_run("run_1") is None
    assert store.get_source(source.source_id) is not None

    second = store.purge_run("run_2")
    assert second.success is True
    assert store.get_source(source.source_id) is None

    absent = store.purge_run("run_2")
    assert absent.success is True
    assert absent.already_absent is True


def test_cleanup_expired_removes_run_and_unreferenced_sources(tmp_path: Path):
    now = datetime.now(UTC)
    store = SqliteStore(tmp_path / "cache")
    expired = _run("expired", now=now - timedelta(hours=2), expires_at=now - timedelta(hours=1))
    source = _source("expired-source", now=now - timedelta(hours=2))
    store.save_run(expired)
    store.save_source(expired.run_id, source)

    result = store.cleanup_expired(now=now)

    assert result.expired_runs == 1
    assert store.get_run(expired.run_id) is None
    assert store.get_source(source.source_id) is None


def test_same_candidate_identity_can_belong_to_separate_runs(tmp_path: Path):
    now = datetime.now(UTC)
    store = SqliteStore(tmp_path / "cache")
    candidate = ProviderCandidate(
        candidate_id="candidate-1",
        provider_id="tlr",
        title="合成裁判候選",
    )
    for run_id in ("run_1", "run_2"):
        store.save_run(_run(run_id, now=now))
        store.save_candidate(
            run_id,
            candidate,
            expires_at=now + timedelta(hours=24),
        )

    assert store.list_candidates("run_1") == [candidate]
    assert store.list_candidates("run_2") == [candidate]


def test_fresh_verified_cache_links_same_evidence_to_separate_runs(tmp_path: Path):
    now = datetime.now(UTC)
    store = SqliteStore(tmp_path / "cache")
    source = _source("cached", now=now)
    evidence = _evidence("cached-evidence", source.source_id)

    store.save_run(_run("run_1", now=now))
    store.save_source("run_1", source)
    store.save_evidence("run_1", evidence)
    store.save_cache_entry("law:synthetic:1", source, [evidence])

    cached = store.get_fresh_cache_entry("law:synthetic:1", now=now)
    assert cached == (source, [evidence])

    store.save_run(_run("run_2", now=now))
    store.save_source("run_2", cached[0])
    store.save_evidence("run_2", cached[1][0])

    assert store.list_evidence("run_1") == [evidence]
    assert store.list_evidence("run_2") == [evidence]
    assert (
        store.get_fresh_cache_entry(
            "law:synthetic:1",
            now=source.expires_at + timedelta(seconds=1),
        )
        is None
    )


def test_purge_all_removes_database_sidecars_and_temp_files(tmp_path: Path):
    now = datetime.now(UTC)
    root = tmp_path / "cache"
    store = SqliteStore(root)
    store.save_run(_run("run_1", now=now))
    store.temp_path.mkdir(parents=True, exist_ok=True)
    (store.temp_path / "response.tmp").write_text("synthetic", encoding="utf-8")
    Path(f"{store.database_path}-wal").touch()
    Path(f"{store.database_path}-shm").touch()

    result = store.purge_all()

    assert result.success is True
    assert not store.database_path.exists()
    assert not Path(f"{store.database_path}-wal").exists()
    assert not Path(f"{store.database_path}-shm").exists()
    assert not store.temp_path.exists()
