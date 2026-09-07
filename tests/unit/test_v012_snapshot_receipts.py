from __future__ import annotations

from datetime import UTC, datetime, timedelta
import io
import json
from pathlib import Path
from typing import cast
import zipfile

from alr_tw.contracts.finalization import (
    MAX_FINALIZATION_EVIDENCE_PREVIEW,
    FinalizationContract,
    build_finalization_contract,
    validate_finalization,
)
from alr_tw.contracts.provider_snapshot import ProviderSnapshotReceipt
from alr_tw.contracts.providers import DataMode
from alr_tw.contracts.research import ResearchDepth, ResearchSufficiency
from alr_tw.contracts.sources import (
    EvidenceSectionType,
    EvidenceSpan,
    MaterialType,
    SourceRecord,
    SourceTier,
    TrustStatus,
)
from alr_tw.providers.official import (
    OfficialConstitutionalProvider,
    OfficialLawProvider,
)
from alr_tw.providers.official.http import HttpResponse
from alr_tw.research.provider_executor import (
    JudgmentProviderPort,
    ProviderObligationExecutor,
    ProviderSet,
)
from alr_tw.research.service import ResearchService
from alr_tw.storage.sqlite_store import SqliteStore
from alr_tw.verification.finalization import validate_server_finalization


def _law_archive() -> bytes:
    document = {
        "UpdateDate": "2026/09/04",
        "Laws": [
            {
                "LawName": "示範責任法",
                "LawURL": "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=DEMO0099",
                "LawModifiedDate": "20260904",
                "LawEffectiveDate": "20260904",
                "LawAbandonNote": "",
                "LawArticles": [
                    {
                        "ArticleType": "A",
                        "ArticleNo": "第 7 條",
                        "ArticleContent": "行為人違反示範義務時，應負合成測試責任。",
                    }
                ],
            }
        ],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ChLaw.json", json.dumps(document, ensure_ascii=False))
    return buffer.getvalue()


class _LawTransport:
    async def get(self, url: str, *, timeout: float, max_bytes: int) -> HttpResponse:
        del timeout, max_bytes
        return HttpResponse(200, _law_archive(), {}, url)


class _UnusedHttpTransport:
    async def get(self, url: str, *, timeout: float, max_bytes: int) -> HttpResponse:
        del timeout, max_bytes
        return HttpResponse(503, b"", {}, url)


def _official_law_service(tmp_path: Path) -> ResearchService:
    store = SqliteStore(tmp_path / "cache")
    providers = ProviderSet(
        laws=OfficialLawProvider(_LawTransport(), verify_webpage=False),
        constitutional=OfficialConstitutionalProvider(_UnusedHttpTransport()),
        judgments=cast(JudgmentProviderPort, object()),
    )
    return ResearchService(store, ProviderObligationExecutor(store, providers))


def _complete_law_run(service: ResearchService) -> tuple[str, dict]:
    run = service.create_run(
        "示範責任法第7條",
        mode=DataMode.OFFICIAL_ONLY,
        depth=ResearchDepth.QUICK,
        include_counter_authority=False,
    )
    return run.run_id, service.execute_run_to_completion(run.run_id)


def test_builtin_official_path_persists_receipt_and_reaches_ordinary(tmp_path: Path) -> None:
    service = _official_law_service(tmp_path)
    run_id, execution = _complete_law_run(service)

    receipts = service.store.list_provider_snapshot_receipts(run_id)
    persisted = SqliteStore(service.store.root_path).list_provider_snapshot_receipts(run_id)
    finalization = service.get_finalization_contract(run_id)

    assert execution["stop_reason"] == "ready_for_draft"
    assert len(receipts) == 1
    assert persisted == receipts
    assert receipts[0].provider_id == OfficialLawProvider.provider_id
    assert receipts[0].content_digest is not None
    source = service.store.list_sources(run_id)[0]
    assert source.verified_at is not None
    assert receipts[0].issued_at >= source.verified_at
    assert finalization["answer_mode"] == "ordinary"
    assert finalization["snapshot_consistency"]["status"] == "consistent"

    run = service.get_run(run_id)
    assert run is not None
    validated = validate_server_finalization(
        FinalizationContract.model_validate(finalization),
        server_run_id=run_id,
        server_source_ids=run.source_ids,
        server_evidence_ids=run.evidence_ids,
        server_snapshot_receipts=receipts,
        server_run=run,
    )
    assert validated.valid is True
    assert validated.safe_to_draft is True
    assert validated.safe_to_present is False


def test_large_passage_set_uses_digest_bound_preview_without_validation_crash() -> None:
    evidence_ids = [f"ev-{index:04d}" for index in range(3001)]
    contract = build_finalization_contract(
        run_id="run-large-evidence",
        workflow_complete=False,
        research_sufficiency=ResearchSufficiency.INSUFFICIENT,
        allowed_source_ids=["src-large-evidence"],
        allowed_evidence_ids=evidence_ids,
        server_source_ids=["src-large-evidence"],
        server_evidence_ids=evidence_ids,
    )

    assert len(contract.allowed_evidence_ids) == MAX_FINALIZATION_EVIDENCE_PREVIEW
    assert contract.evidence_authorization is not None
    assert contract.evidence_authorization.authorized_count == 3001
    assert contract.evidence_authorization.preview_complete is False

    validation = validate_finalization(
        contract,
        server_run_id="run-large-evidence",
        server_source_ids=["src-large-evidence"],
        server_evidence_ids=evidence_ids,
    )

    assert validation.safe_to_present is False
    assert "FINALIZATION_EVIDENCE_SET_MISMATCH" not in {
        item.code for item in validation.blockers
    }


def test_get_state_exposes_safe_research_brief_for_large_evidence_set(
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC)
    service = ResearchService(SqliteStore(tmp_path / "large-cache"))
    run = service.create_run(
        "民法第184條",
        mode=DataMode.SYNTHETIC,
        depth=ResearchDepth.QUICK,
    )
    text = "合成法條內容，僅供大量 passage 契約測試。"
    digest = EvidenceSpan.hash_text(text)
    source = SourceRecord(
        source_id="src-large-state",
        source_key="law:synthetic-large-state",
        source_version_id="synthetic-large-state:v1",
        material_type=MaterialType.LAW,
        provider_id="official_moj_laws",
        source_tier=SourceTier.OFFICIAL,
        trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
        official_identifier="synthetic:large-state",
        citation="合成法第1條",
        fetched_at=now,
        verified_at=now,
        expires_at=now + timedelta(hours=1),
        content_hash=digest,
        normalized_content_hash=digest,
        normalized_text=text,
    )
    service.store.save_source(run.run_id, source)
    for index in range(513):
        service.store.save_evidence(
            run.run_id,
            EvidenceSpan.from_exact_text(
                evidence_id=f"ev-large-state-{index:04d}",
                source_id=source.source_id,
                section_id=f"passage-{index:04d}",
                section_type=EvidenceSectionType.LAW_TEXT,
                exact_text=text,
                eligible_for_claim_support=True,
            ),
        )

    state = service.get_state(run.run_id, now=now + timedelta(seconds=1))

    authorization = state["finalization"]["evidence_authorization"]
    assert state["evidence_count"] == 513
    assert authorization["authorized_count"] == 513
    assert authorization["preview_count"] == MAX_FINALIZATION_EVIDENCE_PREVIEW
    assert authorization["preview_complete"] is False
    assert state["research_brief"]["answer_authorized"] is False
    assert state["research_brief"]["safe_to_present"] is False
    assert state["research_brief"]["verified_source_count"] == 1
    assert "answer_text" not in state["research_brief"]


def test_research_brief_locator_cannot_replace_passage_claim_binding(
    tmp_path: Path,
) -> None:
    service = _official_law_service(tmp_path)
    run_id, _ = _complete_law_run(service)

    brief = service.get_state(run_id)["research_brief"]
    assert brief["answer_authorized"] is False
    assert brief["safe_to_present"] is False
    assert all("evidence_ids" not in source for source in brief["verified_sources"])

    result = service.validate_answer(
        run_id,
        "行為人違反示範義務時，應負合成測試責任。",
        "validate-brief-locator-only",
    )

    assert result["safe_to_present"] is False
    assert result["answer_text"] is None
    assert "CLAIM_CITATION_BINDING_REQUIRED" in result["blockers"]


def test_evidence_bundle_keeps_law_and_caps_judgments_at_five(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    service = ResearchService(SqliteStore(tmp_path / "bundle-cache"))
    run = service.create_run(
        "民法第184條與相關判決",
        mode=DataMode.SYNTHETIC,
        depth=ResearchDepth.QUICK,
    )

    def save_material(source_id: str, material_type: MaterialType, citation: str) -> None:
        text = f"{citation}的合成可引用內容。"
        digest = EvidenceSpan.hash_text(text)
        source = SourceRecord(
            source_id=source_id,
            source_key=f"synthetic:{source_id}",
            source_version_id=f"{source_id}:v1",
            material_type=material_type,
            provider_id="official-fixture",
            source_tier=SourceTier.OFFICIAL,
            trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
            official_identifier=f"fixture:{source_id}",
            citation=citation,
            fetched_at=now,
            verified_at=now,
            expires_at=now + timedelta(hours=1),
            content_hash=digest,
            normalized_content_hash=digest,
            normalized_text=text,
        )
        service.store.save_source(run.run_id, source)
        service.store.save_evidence(
            run.run_id,
            EvidenceSpan.from_exact_text(
                evidence_id=f"ev-{source_id}",
                source_id=source_id,
                section_id="holding",
                section_type=(
                    EvidenceSectionType.LAW_TEXT
                    if material_type is MaterialType.LAW
                    else EvidenceSectionType.COURT_HOLDING
                ),
                exact_text=text,
                eligible_for_claim_support=True,
            ),
        )

    save_material("src-law", MaterialType.LAW, "民法第184條")
    for index in range(6):
        save_material(
            f"src-judgment-{index}",
            MaterialType.JUDGMENT,
            f"臺灣示範法院第{index}號判決",
        )

    bundle = service.get_evidence_bundle(
        run.run_id,
        now=now + timedelta(seconds=1),
    )
    material_types = [item["source"]["material_type"] for item in bundle["items"]]

    assert bundle["source_count"] == 6
    assert material_types[0] == "law"
    assert material_types.count("judgment") == 5
    assert bundle["truncated"] is True


def test_missing_receipt_is_conditional_and_forged_caller_receipt_is_blocked(
    tmp_path: Path,
) -> None:
    service = _official_law_service(tmp_path)
    run_id, _ = _complete_law_run(service)
    run = service.get_run(run_id)
    assert run is not None
    server_receipts = service.store.list_provider_snapshot_receipts(run_id)
    ordinary = FinalizationContract.model_validate(service.get_finalization_contract(run_id))

    service.store.replace_provider_snapshot_receipts(run_id, [])
    without_receipt = service.get_finalization_contract(run_id)
    assert without_receipt["answer_mode"] == "conditional"
    assert without_receipt["snapshot_consistency"]["status"] == "legacy_no_receipt"

    forged = ProviderSnapshotReceipt(
        receipt_id="rcpt:caller-forged",
        provider_id=server_receipts[0].provider_id,
        snapshot_id="snap:caller-forged",
        generation="gen:caller-forged",
        issued_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        content_digest="sha256:" + "f" * 64,
    )
    caller_contract = ordinary.model_copy(update={"snapshot_receipts": [forged]})
    validation = validate_server_finalization(
        caller_contract,
        server_run_id=run_id,
        server_source_ids=run.source_ids,
        server_evidence_ids=run.evidence_ids,
        server_snapshot_receipts=server_receipts,
        server_run=run,
    )
    assert validation.valid is False
    assert validation.safe_to_present is False
    assert "SNAPSHOT_RECEIPT_NOT_SERVER_OWNED" in {item.code for item in validation.blockers}


def test_material_added_without_resigning_invalidates_persisted_receipt(tmp_path: Path) -> None:
    service = _official_law_service(tmp_path)
    run_id, _ = _complete_law_run(service)
    now = datetime.now(UTC)
    text = "另一段未納入原 receipt 的官方測試材料。"
    digest = EvidenceSpan.hash_text(text)
    source = SourceRecord(
        source_id="source-added-after-receipt",
        source_key="law:added-after-receipt",
        source_version_id="law:added-after-receipt:v1",
        material_type=MaterialType.LAW,
        provider_id=OfficialLawProvider.provider_id,
        source_tier=SourceTier.OFFICIAL,
        trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
        official_identifier="DEMO0099:8",
        official_url="https://law.moj.gov.tw/LawClass/LawSingle.aspx?pcode=DEMO0099&flno=8",
        citation="示範責任法第8條",
        fetched_at=now,
        verified_at=now,
        expires_at=now + timedelta(hours=1),
        content_hash=digest,
        normalized_content_hash=digest,
        normalized_text=text,
    )
    evidence = EvidenceSpan.from_exact_text(
        evidence_id="evidence-added-after-receipt",
        source_id=source.source_id,
        section_id="article-8",
        section_type=EvidenceSectionType.LAW_TEXT,
        exact_text=text,
        eligible_for_claim_support=True,
    )
    service.store.save_source(run_id, source)
    service.store.save_evidence(run_id, evidence)

    finalization = service.get_finalization_contract(run_id)
    assert finalization["answer_mode"] == "refusal_only"
    assert finalization["snapshot_consistency"]["status"] == "mismatch"
    assert "SNAPSHOT_RECEIPT_MISMATCH" in {item["code"] for item in finalization["blockers"]}


def test_cross_run_and_expired_persisted_receipts_fail_closed(tmp_path: Path) -> None:
    service = _official_law_service(tmp_path)
    first_run_id, _ = _complete_law_run(service)
    second_run_id, _ = _complete_law_run(service)
    second_receipt = service.store.list_provider_snapshot_receipts(second_run_id)[0]

    # Simulate a corrupted store moving a valid receipt to a different run.
    service.store.replace_provider_snapshot_receipts(second_run_id, [])
    service.store.replace_provider_snapshot_receipts(first_run_id, [second_receipt])
    mixed = service.get_finalization_contract(first_run_id)
    assert mixed["answer_mode"] == "refusal_only"
    assert mixed["snapshot_consistency"]["status"] == "mismatch"
    assert "SNAPSHOT_RECEIPT_MISMATCH" in {item["code"] for item in mixed["blockers"]}

    third_run_id, _ = _complete_law_run(service)
    current = service.store.list_provider_snapshot_receipts(third_run_id)[0]
    expired_at = datetime.now(UTC) - timedelta(minutes=1)
    expired = current.model_copy(
        update={
            "issued_at": expired_at - timedelta(minutes=1),
            "expires_at": expired_at,
        }
    )
    service.store.replace_provider_snapshot_receipts(third_run_id, [expired])
    stale = service.get_finalization_contract(third_run_id)
    assert stale["answer_mode"] == "refusal_only"
    assert stale["snapshot_consistency"]["status"] == "mismatch"
    assert "SNAPSHOT_RECEIPT_MISMATCH" in {item["code"] for item in stale["blockers"]}


def test_run_purge_cascades_snapshot_receipts(tmp_path: Path) -> None:
    service = _official_law_service(tmp_path)
    run_id, _ = _complete_law_run(service)
    assert service.store.list_provider_snapshot_receipts(run_id)

    service.store.purge_run(run_id)
    assert service.store.list_provider_snapshot_receipts(run_id) == []
