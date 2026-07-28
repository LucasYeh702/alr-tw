from __future__ import annotations

from datetime import UTC, datetime
import json

import pytest
from pydantic import ValidationError

from alr_tw.contracts.interop import (
    DiscoveryMode,
    ExecutionOwner,
    RegisteredResearchPlan,
    ResearchPlanProposal,
    ResearchResponsibility,
    interoperability_capabilities,
)
from alr_tw.contracts.providers import DataMode


def _plan_payload() -> dict:
    return {
        "plan_id": "plan-demo",
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
                "locator_id": "law-1",
                "material_type": "law",
                "citation": "示範責任法第7條",
                "purpose": "primary_rule",
                "issue_ids": ["issue-duty"],
            }
        ],
    }


def test_capability_contract_is_agent_neutral_and_preserves_server_ownership():
    capabilities = interoperability_capabilities(DataMode.HYBRID_VERIFIED)

    assert capabilities.interface_family == "agent_neutral_legal_research"
    assert capabilities.supported_discovery_modes == [
        DiscoveryMode.SERVER_MANAGED,
        DiscoveryMode.CLIENT_ASSISTED,
    ]
    assert capabilities.reasoning_owner == "external_client"
    assert capabilities.verification_owner == "server"
    assert capabilities.evidence_promotion_owner == "server"
    assert capabilities.final_decision_owner == "server"
    assert capabilities.accepts_client_evidence is False
    assert capabilities.accepts_client_fact_states is False
    assert capabilities.accepts_client_trust_decisions is False
    assert capabilities.client_authority_locators_are_candidate_only is True
    assert capabilities.accepted_legal_analysis_schema == "alr-tw.legal-analysis/v1"
    assert capabilities.legal_analysis_validation_tool == "validate_legal_analysis"
    assert {profile.value for profile in capabilities.supported_legal_analysis_profiles} == {
        "civil_substantive",
        "civil_procedure",
        "criminal_substantive",
        "criminal_procedure",
        "administrative",
        "constitutional_review",
    }
    assert capabilities.managed_fact_state_store_available is False
    assert "legal analysis proposals remain untrusted until server validation" in (
        capabilities.limitations
    )
    assert all(
        "civil analysis proposals" not in limitation
        and "cross-domain legal analysis proposals" not in limitation
        for limitation in capabilities.limitations
    )
    assert json.loads(json.dumps(capabilities.model_dump()))[
        "supported_legal_analysis_profiles"
    ] == [profile.value for profile in capabilities.supported_legal_analysis_profiles]


def test_responsibility_contract_rejects_client_owned_trust_decisions():
    with pytest.raises(ValidationError, match="verification_owner must remain server owned"):
        ResearchResponsibility(
            discovery_mode="client_assisted",
            verification_owner=ExecutionOwner.EXTERNAL_CLIENT,
        )


def test_research_plan_rejects_unknown_fields_that_could_impersonate_evidence():
    payload = _plan_payload()
    payload["authority_locators"][0]["evidence"] = {
        "official": True,
        "text": "caller supplied text",
    }

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ResearchPlanProposal.model_validate(payload)


def test_research_plan_requires_locator_coverage_for_every_core_issue():
    payload = _plan_payload()
    payload["issues"].append(
        {
            "issue_id": "issue-damage",
            "label": "損害",
            "proposition": "是否發生損害？",
            "category": "constitutive_element",
            "importance": "core",
        }
    )

    with pytest.raises(ValidationError, match="issue-damage"):
        ResearchPlanProposal.model_validate(payload)


def test_research_plan_rejects_cyclic_issue_hierarchy():
    payload = _plan_payload()
    payload["issues"] = [
        {
            "issue_id": "issue-a",
            "label": "A",
            "proposition": "A？",
            "category": "other",
            "parent_issue_id": "issue-b",
        },
        {
            "issue_id": "issue-b",
            "label": "B",
            "proposition": "B？",
            "category": "other",
            "parent_issue_id": "issue-a",
        },
    ]
    payload["authority_locators"][0]["issue_ids"] = ["issue-a", "issue-b"]

    with pytest.raises(ValidationError, match="contains a cycle"):
        ResearchPlanProposal.model_validate(payload)


def test_registered_plan_is_immutable_untrusted_proposal_with_digest():
    proposal = ResearchPlanProposal.model_validate(_plan_payload())
    registered = RegisteredResearchPlan.from_proposal(
        proposal,
        received_at=datetime.now(UTC),
    )

    assert registered.trust_status == "untrusted_client_proposal"
    assert registered.proposal_digest.startswith("sha256:")
