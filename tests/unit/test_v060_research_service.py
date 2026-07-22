from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from alr_tw.contracts.providers import DataMode
from alr_tw.contracts.research import ResearchDepth, ResearchState
from alr_tw.contracts.sources import EvidenceSpan, MaterialType, SourceRecord, SourceTier, TrustStatus
from alr_tw.research.service import ResearchService
from alr_tw.storage.sqlite_store import SqliteStore


def test_continue_executes_one_server_owned_obligation_and_is_idempotent(tmp_path: Path):
    service = ResearchService(SqliteStore(tmp_path / "cache"))
    run = service.create_run(
        "民法第184條",
        mode=DataMode.SYNTHETIC,
        depth=ResearchDepth.QUICK,
        now=datetime.now(UTC),
    )

    first = service.continue_run(run.run_id, "operation_1")
    repeated = service.continue_run(run.run_id, "operation_1")
    stored = service.get_run(run.run_id)

    assert first == repeated
    assert first["outcome"]["obligation"] == "query_understanding"
    assert stored is not None
    assert stored.state is ResearchState.RESEARCHING
    assert sum(item.status.value == "completed" for item in stored.obligations) == 1


def test_synthetic_quick_run_reaches_ready_for_draft_without_final_validation(tmp_path: Path):
    service = ResearchService(SqliteStore(tmp_path / "cache"))
    run = service.create_run(
        "民法第184條",
        mode=DataMode.SYNTHETIC,
        depth=ResearchDepth.QUICK,
    )

    counter = 0
    current = service.get_run(run.run_id)
    assert current is not None
    while current.state is not ResearchState.READY_FOR_DRAFT:
        counter += 1
        service.continue_run(run.run_id, f"operation_{counter}")
        assert counter < 10
        current = service.get_run(run.run_id)
        assert current is not None

    ready = service.get_run(run.run_id)
    assert ready is not None
    assert ready.state is ResearchState.READY_FOR_DRAFT
    assert ready.obligations[-1].kind.value == "final_answer_validation"
    assert ready.obligations[-1].status.value == "pending"


def test_hybrid_run_starts_with_privacy_screen_and_never_silently_downgrades(tmp_path: Path):
    service = ResearchService(SqliteStore(tmp_path / "cache"))
    run = service.create_run("侵權責任", mode=DataMode.HYBRID_VERIFIED)

    assert run.requested_mode is DataMode.HYBRID_VERIFIED
    assert run.effective_mode is DataMode.HYBRID_VERIFIED
    assert run.privacy_status.value == "uncertain"
    assert "privacy_screen" in [item.kind.value for item in run.obligations]


def _advance_to_ready(service: ResearchService, run_id: str) -> None:
    for index in range(10):
        run = service.get_run(run_id)
        assert run is not None
        if run.state is ResearchState.READY_FOR_DRAFT:
            return
        service.continue_run(run_id, f"advance_{index}")
    raise AssertionError("run did not reach ready_for_draft")


def test_validate_answer_blocks_and_removes_untrusted_answer_without_evidence(tmp_path: Path):
    service = ResearchService(SqliteStore(tmp_path / "cache"))
    run = service.create_run("民法第184條", mode=DataMode.SYNTHETIC, depth=ResearchDepth.QUICK)
    _advance_to_ready(service, run.run_id)

    result = service.validate_answer(run.run_id, "本案依法一定勝訴", "validate_1")

    assert result["decision"] == "blocked"
    assert result["safe_to_present"] is False
    assert result["answer_text"] is None
    assert result["binding_mode"] == "legacy_unbound"
    assert "CLAIM_CITATION_BINDING_REQUIRED" in result["blockers"]


def test_validate_answer_uses_only_server_owned_eligible_evidence(tmp_path: Path):
    now = datetime.now(UTC)
    store = SqliteStore(tmp_path / "cache")
    service = ResearchService(store)
    run = service.create_run("民法第184條", mode=DataMode.OFFICIAL_ONLY, depth=ResearchDepth.QUICK)
    _advance_to_ready(service, run.run_id)
    text = "行為人因故意或過失不法侵害他人權利應負損害賠償責任"
    digest = EvidenceSpan.hash_text(text)
    source = SourceRecord(
        source_id="server_source_1",
        source_key="law:184",
        source_version_id="law:184:v1",
        material_type=MaterialType.LAW,
        provider_id="official-law",
        source_tier=SourceTier.OFFICIAL,
        trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
        official_identifier="B0000001:184",
        official_url="https://example.test/law/184",
        citation="民法第184條",
        fetched_at=now,
        verified_at=now,
        expires_at=now + timedelta(hours=24),
        content_hash=digest,
        normalized_content_hash=digest,
        normalized_text=text,
    )
    evidence = EvidenceSpan.from_exact_text(
        evidence_id="server_evidence_1",
        source_id=source.source_id,
        section_id="article-184",
        section_type="law_text",
        exact_text=text,
        eligible_for_claim_support=True,
    )
    store.save_source(run.run_id, source)
    store.save_evidence(run.run_id, evidence)
    store.save_source(
        run.run_id,
        source.model_copy(
            update={
                "source_id": "unused-stale-source",
                "source_key": "law:unused-stale",
                "source_version_id": "law:unused-stale:v1",
                "fetched_at": now - timedelta(minutes=2),
                "verified_at": now - timedelta(minutes=2),
                "expires_at": now - timedelta(minutes=1),
            }
        ),
    )

    result = service.validate_answer(
        run.run_id,
        text,
        "validate_1",
        claim_bindings=[
            {
                "claim_id": "claim-law-184",
                "claim_text": text,
                "claim_type": "law_rule",
                "importance": "core",
                "evidence_ids": [evidence.evidence_id],
            }
        ],
    )

    assert result["decision"] == "validated"
    assert result["safe_to_present"] is True
    assert result["answer_text"] == text
    assert result["schema_version"] == "alr-tw.answer-validation/v3"
    assert result["binding_mode"] == "structured"
    assert result["verification_method"] == "deterministic_grounding_v2"
    assert result["semantic_entailment_performed"] is False
    assert result["privacy"]["status"] == "safe"
    assert result["citations"][0]["evidence_ids"] == [evidence.evidence_id]


def test_expired_server_evidence_cannot_validate_answer(tmp_path: Path):
    now = datetime.now(UTC)
    store = SqliteStore(tmp_path / "cache")
    service = ResearchService(store)
    run = service.create_run("示範法第1條", mode=DataMode.OFFICIAL_ONLY, depth=ResearchDepth.QUICK)
    _advance_to_ready(service, run.run_id)
    text = "過期的合成法規內容不得繼續引用"
    digest = EvidenceSpan.hash_text(text)
    source = SourceRecord(
        source_id="expired-server-source",
        source_key="law:expired",
        source_version_id="law:expired:v1",
        material_type=MaterialType.LAW,
        provider_id="official-law",
        source_tier=SourceTier.OFFICIAL,
        trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
        official_identifier="DEMO:expired",
        official_url="https://example.test/law/expired",
        citation="示範法第1條",
        fetched_at=now - timedelta(hours=2),
        verified_at=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),
        content_hash=digest,
        normalized_content_hash=digest,
        normalized_text=text,
    )
    evidence = EvidenceSpan.from_exact_text(
        evidence_id="expired-server-evidence",
        source_id=source.source_id,
        section_id="article-1",
        section_type="law_text",
        exact_text=text,
        eligible_for_claim_support=True,
    )
    store.save_source(run.run_id, source)
    store.save_evidence(run.run_id, evidence)

    result = service.validate_answer(
        run.run_id,
        text,
        "validate-expired",
        now=now,
        claim_bindings=[
            {
                "claim_id": "claim-expired",
                "claim_text": text,
                "claim_type": "law_rule",
                "evidence_ids": [evidence.evidence_id],
            }
        ],
    )

    assert result["decision"] == "blocked"
    assert result["decision_code"] == "ANSWER_BLOCKED"
    assert result["answer_text"] is None
    assert "SOURCE_STALE" in result["blockers"]


def test_ephemeral_run_is_purged_after_validation_response(tmp_path: Path):
    service = ResearchService(SqliteStore(tmp_path / "cache"))
    run = service.create_run(
        "民法第184條",
        mode=DataMode.SYNTHETIC,
        depth=ResearchDepth.QUICK,
        ephemeral=True,
    )
    _advance_to_ready(service, run.run_id)

    result = service.validate_answer(run.run_id, "合成答案", "validate-ephemeral")

    assert result["decision"] == "blocked"
    assert result["storage_purged"] is True
    assert service.get_run(run.run_id) is None


def test_final_validation_blocks_answer_containing_unmasked_pii(tmp_path: Path):
    now = datetime.now(UTC)
    store = SqliteStore(tmp_path / "cache")
    service = ResearchService(store)
    run = service.create_run(
        "民法第184條",
        mode=DataMode.OFFICIAL_ONLY,
        depth=ResearchDepth.QUICK,
    )
    _advance_to_ready(service, run.run_id)
    text = "行為人應負合成測試責任，聯絡信箱 test.person@example.com"
    digest = EvidenceSpan.hash_text(text)
    source = SourceRecord(
        source_id="pii-source",
        source_key="law:pii",
        source_version_id="law:pii:v1",
        material_type=MaterialType.LAW,
        provider_id="official-law",
        source_tier=SourceTier.OFFICIAL,
        trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
        official_identifier="DEMO:1",
        official_url="https://example.test/law/pii",
        citation="示範法第1條",
        fetched_at=now,
        verified_at=now,
        expires_at=now + timedelta(hours=24),
        content_hash=digest,
        normalized_content_hash=digest,
        normalized_text=text,
    )
    evidence = EvidenceSpan.from_exact_text(
        evidence_id="pii-evidence",
        source_id=source.source_id,
        section_id="article-1",
        section_type="law_text",
        exact_text=text,
        eligible_for_claim_support=True,
    )
    store.save_source(run.run_id, source)
    store.save_evidence(run.run_id, evidence)

    result = service.validate_answer(
        run.run_id,
        text,
        "validate-pii",
        claim_bindings=[
            {
                "claim_id": "claim-pii",
                "claim_text": text,
                "claim_type": "law_rule",
                "evidence_ids": [evidence.evidence_id],
            }
        ],
    )

    assert result["decision"] == "blocked"
    assert result["answer_text"] is None
    assert "ANSWER_CONTAINS_SENSITIVE_DATA" in result["blockers"]
    assert result["privacy"]["status"] == "redaction_required"
    assert "EMAIL" in result["privacy"]["redactions"]
