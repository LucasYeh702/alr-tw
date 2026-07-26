from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from alr_tw.contracts.interop import DiscoveryMode, ResearchPlanProposal
from alr_tw.contracts.providers import DataMode
from alr_tw.contracts.research import ResearchDepth, ResearchObligationKind, ResearchState
from alr_tw.contracts.sources import (
    EvidenceSpan,
    MaterialType,
    SourceRecord,
    SourceTier,
    TrustStatus,
)
from alr_tw.research.service import ResearchService
from alr_tw.storage.sqlite_store import SqliteStore


def _plan() -> ResearchPlanProposal:
    return ResearchPlanProposal.model_validate(
        {
            "plan_id": "plan-duty",
            "issues": [
                {
                    "issue_id": "issue-duty",
                    "label": "法定義務",
                    "proposition": "行為人是否負有法定義務？",
                    "category": "constitutive_element",
                    "importance": "core",
                }
            ],
            "authority_locators": [
                {
                    "locator_id": "law-7",
                    "material_type": "law",
                    "citation": "示範責任法第7條",
                    "issue_ids": ["issue-duty"],
                }
            ],
        }
    )


def _advance(service: ResearchService, run_id: str) -> None:
    for index in range(12):
        run = service.get_run(run_id)
        assert run is not None
        if run.state is ResearchState.READY_FOR_DRAFT:
            return
        service.continue_run(run_id, f"advance-{index}")
    raise AssertionError("research run did not become ready")


def _save_law_evidence(
    store: SqliteStore,
    run_id: str,
    *,
    now: datetime,
) -> EvidenceSpan:
    text = "行為人違反示範義務時，應負合成測試責任。"
    digest = EvidenceSpan.hash_text(text)
    source = SourceRecord(
        source_id=f"source-{run_id}",
        source_key=f"law:{run_id}",
        source_version_id=f"law:{run_id}:v1",
        material_type=MaterialType.LAW,
        provider_id="official-law",
        source_tier=SourceTier.OFFICIAL,
        trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
        official_identifier="DEMO0099:7",
        official_url="https://example.test/law/demo/7",
        citation="示範責任法第7條",
        fetched_at=now,
        verified_at=now,
        expires_at=now + timedelta(hours=24),
        content_hash=digest,
        normalized_content_hash=digest,
        normalized_text=text,
    )
    evidence = EvidenceSpan.from_exact_text(
        evidence_id=f"evidence-{run_id}",
        source_id=source.source_id,
        section_id="article-7",
        section_type="law_text",
        exact_text=text,
        eligible_for_claim_support=True,
    )
    store.save_source(run_id, source)
    store.save_evidence(run_id, evidence)
    return evidence


def test_client_assisted_run_requires_plan_before_any_research(tmp_path: Path):
    service = ResearchService(SqliteStore(tmp_path / "cache"))
    run = service.create_run(
        "請分析本案法定義務",
        mode=DataMode.SYNTHETIC,
        depth=ResearchDepth.QUICK,
        discovery_mode=DiscoveryMode.CLIENT_ASSISTED,
    )

    assert run.obligations[0].kind is ResearchObligationKind.EXTERNAL_PLAN_REVIEW
    with pytest.raises(ValueError, match="EXTERNAL_RESEARCH_PLAN_REQUIRED"):
        service.continue_run(run.run_id, "continue-before-plan")

    registered = service.register_research_plan(
        run.run_id,
        "register-plan",
        _plan(),
    )
    replayed = service.register_research_plan(
        run.run_id,
        "register-plan",
        _plan(),
    )
    state = service.get_state(run.run_id)

    assert registered == replayed
    assert registered["candidate_only"] is True
    assert state["awaiting_external_plan"] is False
    assert state["interoperability"]["registered_plan"]["trust_status"] == (
        "untrusted_client_proposal"
    )


def test_registered_plan_is_immutable_after_acceptance(tmp_path: Path):
    service = ResearchService(SqliteStore(tmp_path / "cache"))
    run = service.create_run(
        "請分析本案法定義務",
        mode=DataMode.SYNTHETIC,
        depth=ResearchDepth.QUICK,
        discovery_mode=DiscoveryMode.CLIENT_ASSISTED,
    )
    service.register_research_plan(run.run_id, "register-plan", _plan())

    with pytest.raises(ValueError, match="RESEARCH_PLAN_ALREADY_REGISTERED"):
        service.register_research_plan(run.run_id, "replace-plan", _plan())


def test_standard_client_assisted_run_requires_judgment_locator(tmp_path: Path):
    service = ResearchService(SqliteStore(tmp_path / "cache"))
    run = service.create_run(
        "請分析本案法定義務",
        mode=DataMode.SYNTHETIC,
        depth=ResearchDepth.STANDARD,
        discovery_mode=DiscoveryMode.CLIENT_ASSISTED,
    )

    with pytest.raises(
        ValueError,
        match="RESEARCH_PLAN_REQUIRED_LOCATOR_MISSING: judgment",
    ):
        service.register_research_plan(run.run_id, "register-plan", _plan())


def test_core_plan_issue_requires_explicit_final_claim_binding(tmp_path: Path):
    now = datetime.now(UTC)
    store = SqliteStore(tmp_path / "cache")
    service = ResearchService(store)
    run = service.create_run(
        "請分析本案法定義務",
        mode=DataMode.SYNTHETIC,
        depth=ResearchDepth.QUICK,
        discovery_mode=DiscoveryMode.CLIENT_ASSISTED,
        now=now,
    )
    service.register_research_plan(
        run.run_id,
        "register-plan",
        _plan(),
        now=now,
    )
    _advance(service, run.run_id)
    evidence = _save_law_evidence(store, run.run_id, now=now)
    answer = "行為人違反示範義務時，應負合成測試責任。"

    result = service.validate_answer(
        run.run_id,
        answer,
        "validate-without-issue",
        now=now,
        claim_bindings=[
            {
                "claim_id": "claim-duty",
                "claim_text": answer,
                "claim_type": "law_rule",
                "evidence_ids": [evidence.evidence_id],
            }
        ],
    )

    assert result["decision"] == "blocked"
    assert "CORE_RESEARCH_ISSUE_UNBOUND" in result["blockers"]
    assert result["issue_coverage"]["missing_core_issue_ids"] == ["issue-duty"]


def test_core_plan_issue_can_validate_when_bound_to_server_evidence(tmp_path: Path):
    now = datetime.now(UTC)
    store = SqliteStore(tmp_path / "cache")
    service = ResearchService(store)
    run = service.create_run(
        "請分析本案法定義務",
        mode=DataMode.SYNTHETIC,
        depth=ResearchDepth.QUICK,
        discovery_mode=DiscoveryMode.CLIENT_ASSISTED,
        now=now,
    )
    service.register_research_plan(
        run.run_id,
        "register-plan",
        _plan(),
        now=now,
    )
    _advance(service, run.run_id)
    evidence = _save_law_evidence(store, run.run_id, now=now)
    answer = "行為人違反示範義務時，應負合成測試責任。"

    result = service.validate_answer(
        run.run_id,
        answer,
        "validate-with-issue",
        now=now,
        claim_bindings=[
            {
                "claim_id": "claim-duty",
                "claim_text": answer,
                "claim_type": "law_rule",
                "evidence_ids": [evidence.evidence_id],
                "issue_ids": ["issue-duty"],
            }
        ],
    )

    assert result["decision"] == "validated"
    assert result["issue_coverage"]["missing_core_issue_ids"] == []
