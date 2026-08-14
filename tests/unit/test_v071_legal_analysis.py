from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from alr_tw.contracts.civil_analysis import FindingState
from alr_tw.contracts.interop import DiscoveryMode, ResearchPlanProposal
from alr_tw.contracts.legal_analysis import LegalAnalysisEnvelope, LegalAnalysisProfile
from alr_tw.contracts.providers import DataMode
from alr_tw.contracts.research import ResearchDepth, ResearchState
from alr_tw.contracts.sources import (
    EvidenceSpan,
    MaterialType,
    SourceRecord,
    SourceTier,
    TrustStatus,
)
from alr_tw.providers.synthetic import SyntheticLegalContextProvider
from alr_tw.research.service import ResearchService
from alr_tw.storage.sqlite_store import SqliteStore
from alr_tw.verification.legal_analysis import validate_legal_analysis
from tw_legal_rag_mcp.mcp_server.server import McpSession

_CORE_ISSUES = {
    "civil_procedure": [
        "jurisdiction",
        "party_capacity",
        "standing",
        "claim_subject",
        "procedural_prerequisite",
    ],
    "criminal_substantive": [
        "offense_elements",
        "unlawfulness",
        "culpability",
    ],
    "criminal_procedure": [
        "proceeding_stage",
        "prosecution_prerequisite",
        "evidence_admissibility",
        "burden_and_standard",
    ],
    "administrative": [
        "action_classification",
        "authority_basis",
        "competence",
        "procedure",
        "substantive_legality",
        "discretion_and_purpose",
        "remedy_type",
        "standing",
        "prior_proceeding",
        "filing_period",
        "remedy_interest",
    ],
    "constitutional_review": [
        "protected_right",
        "interference",
        "legal_reservation",
        "legitimate_aim",
        "proportionality",
    ],
}
_ADMINISTRATIVE_REMEDY_ISSUES = {
    "remedy_type",
    "standing",
    "prior_proceeding",
    "filing_period",
    "remedy_interest",
    "suspension",
    "scope_of_review",
}


def _civil_branch(
    *,
    scope: str = "complete",
    status: str = "met",
    evidence_id: str = "evidence-law",
) -> dict:
    return {
        "profile": "civil_substantive",
        "scope": scope,
        "claims": [
            {
                "claim_id": "claim-duty",
                "label": "合成責任請求",
                "legal_basis_source_ids": ["source-law"],
                "requested_effects": ["right_constituting"],
            }
        ],
        "elements": [
            {
                "element_id": "element-duty",
                "claim_id": "claim-duty",
                "label": "違反合成義務",
                "proposition": "行為人是否違反合成義務？",
                "legal_effect": "right_constituting",
                "status": status,
                "normative_source_ids": ["source-law"],
                "evidence_ids": [evidence_id]
                if status in {"met", "not_met"}
                else [],
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


def _issue_branch(
    profile: str,
    *,
    scope: str = "complete",
    issue_types: list[str] | None = None,
    status: str = "met",
    evidence_id: str = "evidence-law",
) -> dict:
    selected_issues = issue_types or _CORE_ISSUES[profile]
    issues = []
    for index, issue_type in enumerate(selected_issues):
        issue = {
            "issue_id": f"{profile}-issue-{index}",
            "issue_type": issue_type,
            "label": f"合成議題 {issue_type}",
            "proposition": f"是否符合 {issue_type}？",
            "status": status,
            "normative_source_ids": ["source-law"],
            "evidence_ids": [evidence_id] if status in {"met", "not_met"} else [],
        }
        if profile == "administrative":
            issue["track"] = (
                "remedy"
                if issue_type in _ADMINISTRATIVE_REMEDY_ISSUES
                else "legality"
            )
        issues.append(issue)
    return {"profile": profile, "scope": scope, "issues": issues}


def _analysis_payload(
    profiles: str | list[str] = "criminal_substantive",
    *,
    scope: str = "complete",
    issue_types: list[str] | None = None,
    status: str = "met",
    evidence_id: str = "evidence-law",
    counter_status: str = "found",
) -> dict:
    selected_profiles = [profiles] if isinstance(profiles, str) else profiles
    branches = [
        _civil_branch(scope=scope, status=status, evidence_id=evidence_id)
        if profile == "civil_substantive"
        else _issue_branch(
            profile,
            scope=scope,
            issue_types=issue_types if len(selected_profiles) == 1 else None,
            status=status,
            evidence_id=evidence_id,
        )
        for profile in selected_profiles
    ]
    counter_authority = {
        "status": counter_status,
        "source_ids": ["source-law"] if counter_status == "found" else [],
    }
    if counter_status == "not_found_in_scope":
        counter_authority["scope_description"] = "僅限合成 fixture 的有界查詢"
    return {
        "analysis_id": "analysis-unified",
        "analyses": branches,
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
            "description": "合成測試程序階段",
            "source_ids": ["source-law"],
        },
    }


def _server_context(now: datetime) -> tuple[SourceRecord, EvidenceSpan]:
    text = "合成法律規定各領域的程序、要件與法律效果。"
    digest = EvidenceSpan.hash_text(text)
    source = SourceRecord(
        source_id="source-law",
        source_key="law:domain:fixture",
        source_version_id="law:domain:fixture:v1",
        material_type=MaterialType.LAW,
        provider_id="synthetic-law",
        source_tier=SourceTier.OFFICIAL,
        trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
        official_identifier="DOMAIN_FIXTURE",
        official_url="https://example.test/law/domain",
        citation="合成領域法第1條",
        fetched_at=now,
        verified_at=now,
        expires_at=now + timedelta(hours=24),
        content_hash=digest,
        normalized_content_hash=digest,
        normalized_text=text,
        metadata={"synthetic_fixture": True},
    )
    evidence = EvidenceSpan.from_exact_text(
        evidence_id="evidence-law",
        source_id=source.source_id,
        section_id="article-1",
        section_type="law_text",
        exact_text=text,
        eligible_for_claim_support=True,
    )
    return source, evidence


def _ready_service(tmp_path: Path) -> tuple[ResearchService, str, datetime]:
    now = datetime.now(UTC)
    store = SqliteStore(tmp_path / "cache")
    service = ResearchService(
        store,
        legal_context_provider=SyntheticLegalContextProvider({"source-law"}),
    )
    run = service.create_run(
        "請分析合成法律問題",
        mode=DataMode.SYNTHETIC,
        depth=ResearchDepth.QUICK,
        discovery_mode=DiscoveryMode.CLIENT_ASSISTED,
        now=now,
    )
    plan = ResearchPlanProposal.model_validate(
        {
            "plan_id": "plan-domain",
            "issues": [
                {
                    "issue_id": "issue-offense",
                    "label": "法律問題",
                    "proposition": "是否符合合成法律要件？",
                    "category": "constitutive_element",
                }
            ],
            "authority_locators": [
                {
                    "locator_id": "law-domain",
                    "material_type": "law",
                    "citation": "合成領域法第1條",
                    "issue_ids": ["issue-offense"],
                }
            ],
        }
    )
    service.register_research_plan(run.run_id, "register-plan", plan, now=now)
    source, evidence = _server_context(now)
    store.save_source(run.run_id, source)
    store.save_evidence(run.run_id, evidence)
    for index in range(12):
        current = service.get_run(run.run_id)
        assert current is not None
        if current.state is ResearchState.READY_FOR_DRAFT:
            break
        service.continue_run(run.run_id, f"advance-{index}", now=now)
    else:
        raise AssertionError("research run did not become ready")
    return service, run.run_id, now


def _validate(
    payload: dict,
    *,
    now: datetime,
    server_fact_states: dict[str, FindingState] | None = None,
):
    source, evidence = _server_context(now)
    context = SyntheticLegalContextProvider({source.source_id}).assess(
        [source],
        as_of_date=now.date(),
        assessed_at=now,
    )
    return validate_legal_analysis(
        LegalAnalysisEnvelope.model_validate(payload),
        server_sources=[source],
        server_evidence=[evidence],
        legal_context=context,
        server_fact_states=server_fact_states,
        validated_at=now,
    )


@pytest.mark.parametrize("profile", [item.value for item in LegalAnalysisProfile])
def test_contract_discriminates_exactly_six_profiles(profile: str):
    payload = _analysis_payload(profile)

    analysis = LegalAnalysisEnvelope.model_validate(payload)

    assert len(LegalAnalysisProfile) == 6
    assert analysis.analyses[0].profile == profile


def test_envelope_accepts_multiple_complementary_branches():
    payload = _analysis_payload(
        ["civil_substantive", "civil_procedure", "constitutional_review"]
    )

    analysis = LegalAnalysisEnvelope.model_validate(payload)

    assert [branch.profile for branch in analysis.analyses] == [
        "civil_substantive",
        "civil_procedure",
        "constitutional_review",
    ]


def test_envelope_rejects_duplicate_profile():
    payload = _analysis_payload(["criminal_substantive", "criminal_substantive"])

    with pytest.raises(ValidationError, match="at most one branch per profile"):
        LegalAnalysisEnvelope.model_validate(payload)


def test_administrative_branch_discriminates_legality_and_remedy_tracks():
    analysis = LegalAnalysisEnvelope.model_validate(_analysis_payload("administrative"))
    branch = analysis.analyses[0]

    assert branch.profile == "administrative"
    assert {issue.track for issue in branch.issues} == {"legality", "remedy"}  # type: ignore[union-attr]


def test_profile_rejects_issue_type_from_another_domain():
    payload = _analysis_payload(
        "criminal_substantive",
        scope="issue_limited",
        issue_types=["evidence_admissibility"],
        status="uncertain",
    )

    with pytest.raises(ValidationError):
        LegalAnalysisEnvelope.model_validate(payload)


def test_issue_rejects_duplicate_reference_ids():
    payload = _analysis_payload("criminal_substantive")
    payload["analyses"][0]["issues"][0]["normative_source_ids"] = [
        "source-law",
        "source-law",
    ]

    with pytest.raises(ValidationError, match="reference IDs must be unique"):
        LegalAnalysisEnvelope.model_validate(payload)


def test_counter_authority_found_requires_a_source_reference():
    payload = _analysis_payload()
    payload["counter_authority"]["source_ids"] = []

    with pytest.raises(ValidationError, match="requires at least one source_id"):
        LegalAnalysisEnvelope.model_validate(payload)


@pytest.mark.parametrize("profile", [item.value for item in LegalAnalysisProfile])
def test_each_profile_accepts_complete_synthetic_structure(profile: str):
    result = _validate(_analysis_payload(profile), now=datetime.now(UTC))

    assert result.decision.value == "validated"
    assert result.profiles == [LegalAnalysisProfile(profile)]
    assert result.authorizes_final_answer is False
    assert result.semantic_entailment_performed is False


def test_multi_branch_result_reports_all_profiles():
    profiles = ["civil_substantive", "criminal_substantive", "criminal_procedure"]

    result = _validate(_analysis_payload(profiles), now=datetime.now(UTC))

    assert result.decision.value == "validated"
    assert [profile.value for profile in result.profiles] == profiles
    assert result.coverage["branches"] == 3


def test_issue_limited_analysis_is_always_qualified():
    payload = _analysis_payload(
        "criminal_substantive",
        scope="issue_limited",
        issue_types=["offense_elements"],
        status="uncertain",
    )

    result = _validate(payload, now=datetime.now(UTC))

    assert result.decision.value == "qualified"
    assert "DOMAIN_ANALYSIS_SCOPE_LIMITED" in result.qualifications
    assert "DOMAIN_ISSUE_UNRESOLVED" in result.qualifications


def test_disputed_civil_element_is_unresolved_not_determinate():
    result = _validate(
        _analysis_payload("civil_substantive", status="disputed"),
        now=datetime.now(UTC),
    )

    assert result.decision.value == "qualified"
    assert "CIVIL_ELEMENT_UNRESOLVED" in result.qualifications


def test_administrative_legality_and_remedy_tracks_report_domain_refusal_codes():
    result = _validate(
        _analysis_payload("administrative", status="disputed"),
        now=datetime.now(UTC),
    )

    assert result.decision.value == "qualified"
    assert "DOMAIN_REFUSAL_CONSTRAINT_NOT_DECLARED" in result.qualifications


def test_complete_profile_missing_core_dimension_is_blocked():
    payload = _analysis_payload(
        "criminal_substantive",
        issue_types=["offense_elements", "unlawfulness"],
    )

    result = _validate(payload, now=datetime.now(UTC))

    assert result.decision.value == "blocked"
    assert "DOMAIN_PROFILE_CORE_DIMENSION_MISSING" in result.blockers


def test_civil_branch_requires_burden_and_normative_support():
    payload = _analysis_payload("civil_substantive")
    payload["analyses"][0]["burden_of_proof"] = []
    payload["analyses"][0]["elements"][0]["normative_source_ids"] = []

    result = _validate(payload, now=datetime.now(UTC))

    assert result.decision.value == "blocked"
    assert "ELEMENT_BURDEN_RECORD_REQUIRED" in result.blockers
    assert "DETERMINATE_ELEMENT_NORMATIVE_SOURCE_REQUIRED" in result.blockers


def test_caller_supplied_evidence_reference_is_blocked():
    result = _validate(
        _analysis_payload(evidence_id="caller-evidence"),
        now=datetime.now(UTC),
    )

    assert result.decision.value == "blocked"
    assert "ANALYSIS_EVIDENCE_NOT_SERVER_OWNED" in result.blockers


def test_determinate_issue_requires_server_owned_support():
    payload = _analysis_payload()
    for issue in payload["analyses"][0]["issues"]:
        issue["evidence_ids"] = []

    result = _validate(payload, now=datetime.now(UTC))

    assert result.decision.value == "blocked"
    assert "DETERMINATE_ANALYSIS_FACT_OR_EVIDENCE_REQUIRED" in result.blockers


def test_provider_neutral_validator_accepts_only_server_owned_fact_state():
    payload = _analysis_payload()
    payload["facts"] = [
        {
            "fact_id": "server-fact",
            "statement": "合成且由 server context 管理的事實。",
            "status": "proven",
        }
    ]
    for issue in payload["analyses"][0]["issues"]:
        issue["evidence_ids"] = []
        issue["fact_ids"] = ["server-fact"]

    result = _validate(
        payload,
        now=datetime.now(UTC),
        server_fact_states={"server-fact": FindingState.PROVEN},
    )

    assert result.decision.value == "validated"


def test_not_found_in_scope_never_becomes_absence_proof():
    result = _validate(
        _analysis_payload(counter_status="not_found_in_scope"),
        now=datetime.now(UTC),
    )

    assert result.decision.value == "qualified"
    assert "COUNTER_AUTHORITY_ABSENCE_NOT_ESTABLISHED" in result.qualifications


def test_unified_analysis_rejects_embedded_source_body():
    payload = _analysis_payload()
    payload["source_records"] = [{"source_id": "source-law", "text": "caller supplied"}]

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        LegalAnalysisEnvelope.model_validate(payload)


def test_research_service_validates_multi_branch_analysis_on_same_run(tmp_path):
    service, run_id, now = _ready_service(tmp_path)
    analysis = LegalAnalysisEnvelope.model_validate(
        _analysis_payload(["civil_substantive", "civil_procedure"])
    )

    result = service.validate_legal_analysis(
        run_id,
        "validate-domain-analysis",
        analysis,
        now=now,
    )

    assert result["decision"] == "validated"
    assert result["profiles"] == ["civil_substantive", "civil_procedure"]
    assert result["run_id"] == run_id
    assert result["legal_context"]["status"] == "complete"


def test_managed_service_rejects_client_self_certified_fact_state(tmp_path):
    service, run_id, now = _ready_service(tmp_path)
    payload = _analysis_payload()
    payload["facts"] = [
        {
            "fact_id": "client-fact",
            "statement": "呼叫端自行宣告的事實。",
            "status": "proven",
        }
    ]
    payload["analyses"][0]["issues"][0]["evidence_ids"] = []
    payload["analyses"][0]["issues"][0]["fact_ids"] = ["client-fact"]
    analysis = LegalAnalysisEnvelope.model_validate(payload)

    result = service.validate_legal_analysis(
        run_id,
        "reject-client-fact",
        analysis,
        now=now,
    )

    assert result["decision"] == "blocked"
    assert "ANALYSIS_FACT_NOT_SERVER_OWNED" in result["blockers"]


def test_mcp_exposes_only_unified_analysis_tool(tmp_path):
    service, run_id, _ = _ready_service(tmp_path)
    session = McpSession(ready=True, research_service=service)
    tools_response = session.handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    )
    assert tools_response is not None
    names = {tool["name"] for tool in tools_response["result"]["tools"]}
    assert "validate_legal_analysis" in names
    assert "validate_civil_analysis" not in names

    response = session.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "validate_legal_analysis",
                "arguments": {
                    "run_id": run_id,
                    "operation_id": "validate-domain-mcp",
                    "analysis": _analysis_payload("civil_substantive"),
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["data"]["decision"] == "validated"
    assert payload["data"]["profiles"] == ["civil_substantive"]
