from __future__ import annotations

from datetime import UTC, datetime, timedelta
import io
from itertools import count
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping
import zipfile

from alr_tw.config import Settings
from alr_tw.contracts.finalization import CounterAuthorityGate, build_finalization_contract
from alr_tw.contracts.provider_snapshot import ProviderSnapshotReceipt
from alr_tw.contracts.providers import DataMode, ToolProfile
from alr_tw.contracts.research import ResearchSufficiency
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
    OfficialJudgmentProvider,
    OfficialLawProvider,
)
from alr_tw.providers.official.http import HttpResponse
from alr_tw.providers.official.judicial_site import JudicialSiteResponse
from alr_tw.providers.tlr import TlrCaseHistoryEntry, TlrCaseHistoryRecord
from alr_tw.research.judgment_lineage import VerifiedLineageSource, build_lineage_contract
from alr_tw.research.provider_executor import ProviderObligationExecutor, ProviderSet
from alr_tw.research.service import ResearchService
from alr_tw.storage.sqlite_store import SqliteStore
from alr_tw.verification.claim_support import (
    AnswerClaim,
    ClaimType,
    LegalSegment,
    SectionRole,
    SupportStatus,
    check_claim_support,
)
from tw_legal_rag_mcp.mcp_server.server import McpSession
from tw_legal_rag_mcp.verification.answer_validation import answer_with_validation


_REQUEST_IDS = count(1)
_LAW_TEXTS = {
    "7": "行為人違反示範義務時，應負合成測試責任。",
    "8": "管理機關應保存示範查核紀錄。",
}


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
                        "ArticleNo": f"第 {article_no} 條",
                        "ArticleContent": text,
                    }
                    for article_no, text in _LAW_TEXTS.items()
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


class _NotFoundJudgmentTransport:
    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def get(
        self,
        url: str,
        *,
        timeout: float,
        max_bytes: int,
    ) -> JudicialSiteResponse:
        del timeout, max_bytes
        return JudicialSiteResponse(404, b"", {}, url)

    async def post_form(
        self,
        url: str,
        form: Mapping[str, str],
        *,
        timeout: float,
        max_bytes: int,
    ) -> JudicialSiteResponse:
        del form, timeout, max_bytes
        return JudicialSiteResponse(200, "查無符合條件".encode(), {}, url)


def _mcp_session(tmp_path: Path) -> McpSession:
    store = SqliteStore(tmp_path / "cache")
    providers = ProviderSet(
        laws=OfficialLawProvider(_LawTransport(), verify_webpage=False),
        constitutional=OfficialConstitutionalProvider(_UnusedHttpTransport()),
        judgments=OfficialJudgmentProvider(_NotFoundJudgmentTransport()),
    )
    service = ResearchService(store, ProviderObligationExecutor(store, providers))
    settings = Settings(
        data_mode=DataMode.OFFICIAL_ONLY,
        mcp_tool_profile=ToolProfile.VERIFIED,
        storage_path=store.root_path,
    )
    return McpSession(ready=True, settings=settings, research_service=service)


def _call(session: McpSession, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    response = session.handle_message(
        {
            "jsonrpc": "2.0",
            "id": next(_REQUEST_IDS),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    assert response is not None
    assert "error" not in response
    envelope = json.loads(response["result"]["content"][0]["text"])
    assert envelope["ok"] is True
    return envelope["data"]


def _advance_by_mcp(session: McpSession, query: str) -> tuple[str, dict[str, Any]]:
    capabilities = _call(session, "get_legal_research_capabilities", {})
    assert capabilities["active_mcp_tool_profile"] == "verified"
    created = _call(
        session,
        "research_legal_question",
        {
            "query": f"/quick {query}",
            "constraints": {"include_counter_authority": False},
        },
    )
    run_id = created["run"]["run_id"]
    for index in range(10):
        step = _call(
            session,
            "continue_legal_research",
            {"run_id": run_id, "operation_id": f"lane-c-step-{index}"},
        )
        if step["remaining_obligations"] == ["final_answer_validation"]:
            break
    else:  # pragma: no cover - explicit bounded guard
        raise AssertionError("Lane C did not reach finalization within ten steps")
    return run_id, _call(session, "get_legal_research_finalization", {"run_id": run_id})


def _positive_law_flow(tmp_path: Path, article_no: str) -> dict[str, Any]:
    session = _mcp_session(tmp_path)
    text = _LAW_TEXTS[article_no]
    run_id, finalization = _advance_by_mcp(session, f"示範責任法第{article_no}條")
    assert finalization["answer_mode"] == "ordinary"
    evidence_id = finalization["allowed_evidence_ids"][0]
    return _call(
        session,
        "validate_legal_answer",
        {
            "run_id": run_id,
            "answer_text": text,
            "operation_id": f"lane-c-validate-law-{article_no}",
            "claim_bindings": [
                {
                    "claim_id": f"claim-law-{article_no}",
                    "claim_text": text,
                    "claim_type": "law_rule",
                    "importance": "core",
                    "evidence_ids": [evidence_id],
                }
            ],
        },
    )


def _lineage_source(
    source_id: str,
    evidence_id: str,
    jid: str,
    citation: str,
    text: str,
) -> tuple[SourceRecord, EvidenceSpan]:
    now = datetime.now(UTC)
    digest = EvidenceSpan.hash_text(text)
    source = SourceRecord(
        source_id=source_id,
        source_key=f"judgment:{jid}",
        source_version_id=f"judgment:{jid}:v1",
        material_type=MaterialType.JUDGMENT,
        provider_id=OfficialJudgmentProvider.provider_id,
        source_tier=SourceTier.OFFICIAL,
        trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
        official_identifier=jid,
        official_url=OfficialJudgmentProvider.official_document_url(jid),
        citation=citation,
        fetched_at=now,
        verified_at=now,
        expires_at=now + timedelta(hours=1),
        content_hash=digest,
        normalized_content_hash=digest,
        normalized_text=text,
    )
    evidence = EvidenceSpan.from_exact_text(
        evidence_id=evidence_id,
        source_id=source_id,
        section_id="disposition-1",
        section_type=EvidenceSectionType.DISPOSITION,
        exact_text=text,
        eligible_for_claim_support=True,
    )
    return source, evidence


def test_lane_a_fake_official_candidate_and_legacy_bypass_are_blocked() -> None:
    attacks = [
        {
            "citation_id": "fake-official",
            "source_id": "fake-official",
            "source_tier": "official",
            "official_url": "https://attacker.invalid/fake-official",
        },
        {
            "citation_id": "candidate-only",
            "source_id": "candidate-only",
            "source_tier": "external_semantic_recall",
        },
        {
            "citation_id": "legacy-bypass",
            "source_id": "legacy-bypass",
            "source_tier": "official",
            "official_url": "https://attacker.invalid/legacy-bypass",
            "identifier_resolution": "hash_match",
        },
    ]
    results = [answer_with_validation("攻擊內容不得呈現。", [attack]) for attack in attacks]

    assert all(result["validation_summary"]["safe_to_present"] is False for result in results)
    assert results[0]["citations"][0]["error_code"] == "CALLER_ATTESTED_SOURCE"
    assert results[1]["citations"][0]["citation_use"] == "allow_candidate_only"
    assert results[2]["citations"][0]["identifier_resolution"] == "not_attempted"


def test_lane_a_role_mismatch_is_blocked() -> None:
    text = "法院認為被告應負損害賠償責任"
    support, summary, reasons = check_claim_support(
        answer=text,
        claims=[
            AnswerClaim(
                claim_id="claim-court-view",
                claim_text=text,
                claim_type=ClaimType.COURT_VIEW,
                referenced_citation_ids=["evidence-party"],
            )
        ],
        segments=[
            LegalSegment(
                segment_id="evidence-party",
                source_id="source-party",
                citation_id="evidence-party",
                source_tier="official",
                legal_material_type="judgment",
                section_role=SectionRole.PARTY_ARGUMENT,
                text=text,
                span_start=0,
                span_end=len(text),
            )
        ],
        require_explicit_bindings=True,
    )

    assert support[0].support_status is SupportStatus.ROLE_ERROR
    assert summary.semantic_safe_to_present is False
    assert "CLAIM_ROLE_ERROR" in reasons


def test_lane_a_bounded_miss_cannot_become_consensus() -> None:
    now = datetime.now(UTC)
    receipt = ProviderSnapshotReceipt(
        receipt_id="rcpt:bounded-counter",
        provider_id="official-provider",
        snapshot_id="snap:bounded-counter",
        generation="gen:bounded-counter",
        issued_at=now,
        expires_at=now + timedelta(hours=1),
        content_digest="sha256:" + "a" * 64,
    )
    contract = build_finalization_contract(
        run_id="run_bounded_counter",
        workflow_complete=True,
        research_sufficiency=ResearchSufficiency.SUFFICIENT,
        allowed_source_ids=["source-1"],
        allowed_evidence_ids=["evidence-1"],
        server_source_ids=["source-1"],
        server_evidence_ids=["evidence-1"],
        coverage_complete=True,
        time_context_complete=True,
        authority_complete=True,
        counter_authority=CounterAuthorityGate(
            required=True,
            coverage_complete=True,
            consensus_claim_requested=True,
            consensus_claim_allowed=False,
        ),
        snapshot_receipts=[receipt],
        server_snapshot_receipts=[receipt],
        now=now,
    )

    assert contract.answer_mode.value == "conditional"
    assert any("不得作成實務見解一致" in item for item in contract.required_qualification)


def test_lane_a_one_sided_vacated_marker_is_not_confirmed_reversal() -> None:
    root_jid = "DEMO,130,測,1,20990101,1"
    upper_jid = "DEMO,131,測上,2,21000101,1"
    root_source, root_evidence = _lineage_source(
        "source-root",
        "evidence-root",
        root_jid,
        "示範地方法院130年度測字第1號判決",
        "原告之訴駁回。",
    )
    upper_source, upper_evidence = _lineage_source(
        "source-upper",
        "evidence-upper",
        upper_jid,
        "示範最高法院131年度測上字第2號判決",
        "上訴駁回。",
    )
    history_entry = TlrCaseHistoryEntry(
        direction="upper",
        provider_document_id=upper_jid,
        canonical_jid=upper_jid,
        citation_text=upper_source.citation,
        main_flag="主文含廢棄標記",
        vacated_marker=True,
    )
    history = TlrCaseHistoryRecord(
        root_provider_document_id=root_jid,
        root_canonical_jid=root_jid,
        root_citation_text=root_source.citation,
        history_present=True,
        entries=[history_entry],
    )
    contract, _validation = build_lineage_contract(
        run_id="run_lineage_gate",
        root_source=root_source,
        root_evidence=[root_evidence],
        history=history,
        related=[
            VerifiedLineageSource(
                history=history_entry,
                source=upper_source,
                evidence=(upper_evidence,),
            )
        ],
        max_related_nodes=1,
    )

    assert contract.negative_treatments == []


def test_lane_a_positive_false_refuse_metric_is_zero(tmp_path: Path) -> None:
    results = [
        _positive_law_flow(tmp_path / f"positive-{article_no}", article_no)
        for article_no in _LAW_TEXTS
    ]
    false_refuse_count = sum(result["safe_to_present"] is not True for result in results)

    assert false_refuse_count == 0
    assert len(results) == 2
    assert all(result["decision"] == "validated" for result in results)


def test_lane_c_pass_and_refuse_paths_finish_under_ten_minutes(tmp_path: Path) -> None:
    started = perf_counter()
    passed = _positive_law_flow(tmp_path / "pass", "7")

    refused_session = _mcp_session(tmp_path / "refuse")
    fake_jid = "DEMO,130,測,999,20990101,1"
    run_id, finalization = _advance_by_mcp(
        refused_session,
        f"查證裁判字號 {fake_jid}",
    )
    refused = _call(
        refused_session,
        "validate_legal_answer",
        {
            "run_id": run_id,
            "answer_text": "此虛構字號有一件官方判決。",
            "operation_id": "lane-c-validate-fake-jid",
            "claim_bindings": [],
        },
    )
    elapsed_seconds = perf_counter() - started

    assert elapsed_seconds < 600
    assert passed["decision"] == "validated"
    assert passed["safe_to_present"] is True
    assert finalization["answer_mode"] == "refusal_only"
    assert finalization["blockers"]
    assert finalization["safe_next_actions"]
    assert all(
        item["message"].strip() and item["message"] != item["code"]
        for item in finalization["blockers"]
    )
    assert refused["decision"] == "blocked"
    assert refused["safe_to_present"] is False
    assert refused["answer_text"] is None
    assert refused["structured_refusal"]["safe_next_actions"]
