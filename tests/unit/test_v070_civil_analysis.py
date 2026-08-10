from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from alr_tw.contracts.civil_analysis import (
    FindingState,
    LegalEffectType,
)
from alr_tw.contracts.interop import DiscoveryMode, ResearchPlanProposal
from alr_tw.contracts.legal_analysis import LegalAnalysisEnvelope
from alr_tw.contracts.providers import DataMode
from alr_tw.contracts.research import ResearchDepth, ResearchState
from alr_tw.contracts.sources import (
    EvidenceSpan,
    MaterialType,
    SourceRecord,
    SourceTier,
    TrustStatus,
)
from alr_tw.research.service import ResearchService
from alr_tw.providers.synthetic import SyntheticLegalContextProvider
from alr_tw.storage.sqlite_store import SqliteStore


def _plan() -> ResearchPlanProposal:
    return ResearchPlanProposal.model_validate(
        {
            "plan_id": "plan-civil",
            "issues": [
                {
                    "issue_id": "issue-duty",
                    "label": "示範義務",
                    "proposition": "行為人是否違反示範義務？",
                    "category": "constitutive_element",
                }
            ],
            "authority_locators": [
                {
                    "locator_id": "law-demo",
                    "material_type": "law",
                    "citation": "示範責任法第7條",
                    "issue_ids": ["issue-duty"],
                }
            ],
        }
    )


def _analysis_payload(
    *,
    counter_status: str = "found",
    evidence_id: str = "evidence-law",
) -> dict:
    counter_authority = {
        "status": counter_status,
        "source_ids": ["source-counter"] if counter_status == "found" else [],
    }
    if counter_status == "not_found_in_scope":
        counter_authority["scope_description"] = "僅限合成測試資料的有界查詢"
    return {
        "analysis_id": "analysis-civil",
        "analyses": [
            {
                "profile": "civil_substantive",
                "scope": "complete",
                "claims": [
                    {
                        "claim_id": "claim-duty",
                        "label": "示範責任請求",
                        "legal_basis_source_ids": ["source-law"],
                        "requested_effects": ["right_constituting"],
                    }
                ],
                "elements": [
                    {
                        "element_id": "element-duty",
                        "claim_id": "claim-duty",
                        "label": "違反示範義務",
                        "proposition": "行為人違反示範責任法第7條的示範義務。",
                        "legal_effect": "right_constituting",
                        "status": "met",
                        "normative_source_ids": ["source-law"],
                        "evidence_ids": [evidence_id],
                    }
                ],
                "burden_of_proof": [
                    {
                        "element_id": "element-duty",
                        "burden_type": "persuasion",
                        "burden_bearer": "claimant",
                        "presumption": "none",
                        "burden_shift": "none",
                        "standard_of_proof": "ordinary_civil",
                        "rebuttal_status": "not_applicable",
                        "normative_source_ids": ["source-law"],
                    }
                ],
                "defenses": [],
            }
        ],
        "facts": [],
        "evidence_assessments": [
            {
                "evidence_id": evidence_id,
                "status": "supported",
            }
        ],
        "counter_authority": counter_authority,
        "procedural_posture": {
            "stage": "first_instance",
            "description": "合成測試第一審情境",
            "source_ids": ["source-counter"],
        },
    }


def _save_synthetic_context(
    store: SqliteStore,
    run_id: str,
    *,
    now: datetime,
) -> EvidenceSpan:
    law_text = "行為人違反示範義務時，應負合成測試責任。"
    law_hash = EvidenceSpan.hash_text(law_text)
    law = SourceRecord(
        source_id="source-law",
        source_key="law:demo:7",
        source_version_id="law:demo:7:v1",
        material_type=MaterialType.LAW,
        provider_id="synthetic-law",
        source_tier=SourceTier.OFFICIAL,
        trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
        official_identifier="DEMO0007",
        official_url="https://example.test/law/demo/7",
        citation="示範責任法第7條",
        fetched_at=now,
        verified_at=now,
        expires_at=now + timedelta(hours=24),
        content_hash=law_hash,
        normalized_content_hash=law_hash,
        normalized_text=law_text,
        metadata={"synthetic_fixture": True},
    )
    counter_text = "合成測試裁判提出不同的示範解釋。"
    counter_hash = EvidenceSpan.hash_text(counter_text)
    counter = SourceRecord(
        source_id="source-counter",
        source_key="judgment:demo:counter",
        source_version_id="judgment:demo:counter:v1",
        material_type=MaterialType.JUDGMENT,
        provider_id="synthetic-judgment",
        source_tier=SourceTier.OFFICIAL,
        trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
        official_identifier="DEMO,113,測,1,20990101,1",
        official_url="https://example.test/judgment/demo-counter",
        citation="示範法院未來年度測字第1號",
        fetched_at=now,
        verified_at=now,
        expires_at=now + timedelta(hours=24),
        content_hash=counter_hash,
        normalized_content_hash=counter_hash,
        normalized_text=counter_text,
        metadata={"synthetic_fixture": True},
    )
    evidence = EvidenceSpan.from_exact_text(
        evidence_id="evidence-law",
        source_id=law.source_id,
        section_id="article-7",
        section_type="law_text",
        exact_text=law_text,
        eligible_for_claim_support=True,
    )
    store.save_source(run_id, law)
    store.save_source(run_id, counter)
    store.save_evidence(run_id, evidence)
    return evidence


def _ready_service(tmp_path: Path) -> tuple[ResearchService, str, EvidenceSpan, datetime]:
    now = datetime.now(UTC)
    store = SqliteStore(tmp_path / "cache")
    service = ResearchService(
        store,
        legal_context_provider=SyntheticLegalContextProvider(
            {"source-law", "source-counter"}
        ),
    )
    run = service.create_run(
        "請分析示範民事責任",
        # This fixture exercises downstream claim/privacy/citation gates.  Use
        # the official-only path so the synthetic records do not trigger the
        # separate offline-mode sufficiency refusal.
        mode=DataMode.OFFICIAL_ONLY,
        depth=ResearchDepth.QUICK,
        include_counter_authority=False,
        discovery_mode=DiscoveryMode.CLIENT_ASSISTED,
        now=now,
    )
    service.register_research_plan(run.run_id, "register-plan", _plan(), now=now)
    evidence = _save_synthetic_context(store, run.run_id, now=now)
    for index in range(12):
        current = service.get_run(run.run_id)
        assert current is not None
        if current.state is ResearchState.READY_FOR_DRAFT:
            break
        service.continue_run(run.run_id, f"advance-{index}", now=now)
    else:
        raise AssertionError("research run did not become ready")
    current = service.get_run(run.run_id)
    assert current is not None
    service.store.save_run(
        current.model_copy(
            update={
                "coverage": current.coverage.model_copy(
                    update={
                        "law_checked": True,
                        "coverage_complete": True,
                    }
                )
            }
        )
    )
    return service, run.run_id, evidence, now


def test_civil_analysis_contract_exposes_required_taiwan_civil_law_states():
    assert {item.value for item in LegalEffectType} == {
        "right_constituting",
        "right_impeding",
        "right_extinguishing",
        "defense",
        "liability_reduction",
        "remedy_calculation",
    }
    assert {item.value for item in FindingState} == {
        "alleged",
        "admitted",
        "disputed",
        "supported",
        "proven",
        "contradicted",
        "inadmissible",
        "excluded",
    }


def test_client_cannot_self_certify_counter_authority_absence():
    payload = _analysis_payload(counter_status="not_found_in_scope")
    payload["counter_authority"]["absence_established"] = True

    with pytest.raises(ValidationError):
        LegalAnalysisEnvelope.model_validate(payload)


def test_civil_analysis_validated_then_answer_uses_same_server_evidence(tmp_path: Path):
    service, run_id, evidence, now = _ready_service(tmp_path)
    analysis = LegalAnalysisEnvelope.model_validate(_analysis_payload())

    analysis_result = service.validate_legal_analysis(
        run_id,
        "validate-analysis",
        analysis,
        now=now,
    )
    answer = "行為人違反示範義務時，應負合成測試責任。"
    answer_result = service.validate_answer(
        run_id,
        answer,
        "validate-answer",
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

    assert analysis_result["decision"] == "validated"
    assert analysis_result["authorizes_final_answer"] is False
    assert analysis_result["semantic_entailment_performed"] is False
    assert answer_result["decision"] == "qualified"


def test_not_found_in_scope_is_qualified_never_absence_proof(tmp_path: Path):
    service, run_id, _, now = _ready_service(tmp_path)
    analysis = LegalAnalysisEnvelope.model_validate(
        _analysis_payload(counter_status="not_found_in_scope")
    )

    result = service.validate_legal_analysis(
        run_id,
        "validate-qualified",
        analysis,
        now=now,
    )

    assert result["decision"] == "qualified"
    assert "COUNTER_AUTHORITY_ABSENCE_NOT_ESTABLISHED" in result["qualifications"]


def test_caller_supplied_evidence_id_is_blocked(tmp_path: Path):
    service, run_id, _, now = _ready_service(tmp_path)
    analysis = LegalAnalysisEnvelope.model_validate(
        _analysis_payload(evidence_id="caller-evidence")
    )

    result = service.validate_legal_analysis(
        run_id,
        "validate-blocked",
        analysis,
        now=now,
    )

    assert result["decision"] == "blocked"
    assert "ANALYSIS_EVIDENCE_NOT_SERVER_OWNED" in result["blockers"]


def test_met_element_and_burden_require_normative_support(tmp_path: Path):
    service, run_id, _, now = _ready_service(tmp_path)
    payload = _analysis_payload()
    payload["analyses"][0]["elements"][0]["normative_source_ids"] = []
    payload["analyses"][0]["burden_of_proof"] = []
    analysis = LegalAnalysisEnvelope.model_validate(payload)

    result = service.validate_legal_analysis(
        run_id,
        "validate-missing-norm",
        analysis,
        now=now,
    )

    assert result["decision"] == "blocked"
    assert "DETERMINATE_ELEMENT_NORMATIVE_SOURCE_REQUIRED" in result["blockers"]
    assert "ELEMENT_BURDEN_RECORD_REQUIRED" in result["blockers"]


def test_citation_occurrence_is_verified_inside_bound_clause(tmp_path: Path):
    service, run_id, evidence, now = _ready_service(tmp_path)
    claim_text = "行為人違反示範義務時，應負合成測試責任。"
    citation_text = "示範責任法第7條"
    answer = f"{claim_text[:-1]}（{citation_text}）。"
    citation_start = answer.index(citation_text)

    result = service.validate_answer(
        run_id,
        answer,
        "validate-citation-occurrence",
        now=now,
        claim_bindings=[
            {
                "claim_id": "claim-duty",
                "claim_text": claim_text[:-1],
                "claim_type": "law_rule",
                "evidence_ids": [evidence.evidence_id],
                "issue_ids": ["issue-duty"],
                "citation_occurrences": [
                    {
                        "evidence_id": evidence.evidence_id,
                        "citation_text": citation_text,
                        "start_offset": citation_start,
                        "end_offset": citation_start + len(citation_text),
                    }
                ],
            }
        ],
    )

    assert result["decision"] == "qualified"


def test_citation_occurrence_outside_bound_clause_is_blocked(tmp_path: Path):
    service, run_id, evidence, now = _ready_service(tmp_path)
    claim_text = "行為人違反示範義務時，應負合成測試責任。"
    citation_text = "示範責任法第7條"
    answer = f"{claim_text}另參見{citation_text}。"
    citation_start = answer.index(citation_text)

    result = service.validate_answer(
        run_id,
        answer,
        "validate-unbounded-citation",
        now=now,
        claim_bindings=[
            {
                "claim_id": "claim-duty",
                "claim_text": claim_text,
                "claim_type": "law_rule",
                "evidence_ids": [evidence.evidence_id],
                "issue_ids": ["issue-duty"],
                "citation_occurrences": [
                    {
                        "evidence_id": evidence.evidence_id,
                        "citation_text": citation_text,
                        "start_offset": citation_start,
                        "end_offset": citation_start + len(citation_text),
                    }
                ],
            }
        ],
    )

    assert result["decision"] == "blocked"
    assert "CITATION_OCCURRENCE_OUTSIDE_BOUND_CLAUSE" in result["blockers"]
