"""Agent-neutral interoperability contracts for external legal reasoning clients."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .legal_analysis import LegalAnalysisProfile
from .providers import DataMode, ToolProfile
from .sources import MaterialType

_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$"


class DiscoveryMode(str, Enum):
    """Who proposes initial source locators for a research run."""

    SERVER_MANAGED = "server_managed"
    CLIENT_ASSISTED = "client_assisted"


class ExecutionOwner(str, Enum):
    SERVER = "server"
    EXTERNAL_CLIENT = "external_client"


class LegalIssueCategory(str, Enum):
    CLAIM_BASIS = "claim_basis"
    CONSTITUTIVE_ELEMENT = "constitutive_element"
    DEFENSE = "defense"
    BURDEN_OF_PROOF = "burden_of_proof"
    PROCEDURAL_PREREQUISITE = "procedural_prerequisite"
    LEGAL_EFFECT = "legal_effect"
    TEMPORAL_APPLICABILITY = "temporal_applicability"
    NORM_HIERARCHY = "norm_hierarchy"
    AUTHORITY_WEIGHT = "authority_weight"
    COUNTER_AUTHORITY = "counter_authority"
    OTHER = "other"


class PlanItemImportance(str, Enum):
    CORE = "core"
    SUPPORTING = "supporting"
    CONTEXT = "context"


class AuthorityPurpose(str, Enum):
    PRIMARY_RULE = "primary_rule"
    INTERPRETATION = "interpretation"
    COUNTER_AUTHORITY = "counter_authority"
    PROCEDURE = "procedure"
    LEGAL_EFFECT = "legal_effect"
    TEMPORAL_CONTEXT = "temporal_context"
    OTHER = "other"


class ResearchResponsibility(BaseModel):
    """Fixed trust ownership plus the selectable discovery strategy."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.research-responsibility/v1"] = (
        "alr-tw.research-responsibility/v1"
    )
    discovery_mode: DiscoveryMode = DiscoveryMode.SERVER_MANAGED
    reasoning_owner: ExecutionOwner = ExecutionOwner.EXTERNAL_CLIENT
    verification_owner: ExecutionOwner = ExecutionOwner.SERVER
    evidence_promotion_owner: ExecutionOwner = ExecutionOwner.SERVER
    final_decision_owner: ExecutionOwner = ExecutionOwner.SERVER

    @model_validator(mode="after")
    def preserve_server_owned_trust_boundary(self) -> ResearchResponsibility:
        if self.reasoning_owner is not ExecutionOwner.EXTERNAL_CLIENT:
            raise ValueError("natural-language reasoning must remain external-client owned")
        for field_name in (
            "verification_owner",
            "evidence_promotion_owner",
            "final_decision_owner",
        ):
            if getattr(self, field_name) is not ExecutionOwner.SERVER:
                raise ValueError(f"{field_name} must remain server owned")
        return self


class ProposedLegalIssue(BaseModel):
    """Untrusted issue or element proposed by an external reasoning client."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    issue_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    label: str = Field(min_length=1, max_length=160)
    proposition: str = Field(min_length=1, max_length=2000)
    category: LegalIssueCategory
    importance: PlanItemImportance = PlanItemImportance.CORE
    parent_issue_id: str | None = Field(default=None, pattern=_IDENTIFIER_PATTERN)
    requires_conclusion: bool = True


class AuthorityLocatorProposal(BaseModel):
    """Identifier or formal citation hint; never client-supplied evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    locator_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    material_type: MaterialType
    citation: str = Field(min_length=1, max_length=500)
    identifier: str | None = Field(default=None, min_length=1, max_length=500)
    purpose: AuthorityPurpose = AuthorityPurpose.PRIMARY_RULE
    issue_ids: list[str] = Field(min_length=1, max_length=32)

    @property
    def lookup_text(self) -> str:
        return (self.identifier or self.citation).strip()


class ResearchPlanProposal(BaseModel):
    """Provider-neutral proposal accepted from any MCP-capable reasoning client."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.research-plan-proposal/v1"] = (
        "alr-tw.research-plan-proposal/v1"
    )
    plan_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    issues: list[ProposedLegalIssue] = Field(min_length=1, max_length=64)
    authority_locators: list[AuthorityLocatorProposal] = Field(min_length=1, max_length=128)
    assumptions: list[str] = Field(default_factory=list, max_length=32)
    limitations: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_graph_and_references(self) -> ResearchPlanProposal:
        issue_ids = [item.issue_id for item in self.issues]
        if len(issue_ids) != len(set(issue_ids)):
            raise ValueError("research plan issue_id values must be unique")
        locator_ids = [item.locator_id for item in self.authority_locators]
        if len(locator_ids) != len(set(locator_ids)):
            raise ValueError("research plan locator_id values must be unique")

        known_issues = set(issue_ids)
        parent_map: dict[str, str] = {}
        for issue in self.issues:
            if issue.parent_issue_id is not None:
                if issue.parent_issue_id not in known_issues:
                    raise ValueError("research plan parent_issue_id is unknown")
                if issue.parent_issue_id == issue.issue_id:
                    raise ValueError("research plan issue cannot be its own parent")
                parent_map[issue.issue_id] = issue.parent_issue_id

        for start in parent_map:
            visited: set[str] = set()
            current = start
            while current in parent_map:
                if current in visited:
                    raise ValueError("research plan issue hierarchy contains a cycle")
                visited.add(current)
                current = parent_map[current]

        located_issue_ids: set[str] = set()
        for locator in self.authority_locators:
            unknown = set(locator.issue_ids) - known_issues
            if unknown:
                raise ValueError("research plan authority locator references an unknown issue")
            located_issue_ids.update(locator.issue_ids)

        required_core = {
            item.issue_id
            for item in self.issues
            if item.importance is PlanItemImportance.CORE and item.requires_conclusion
        }
        if not required_core:
            raise ValueError("research plan requires at least one core issue")
        if missing := required_core - located_issue_ids:
            raise ValueError(
                "each core research issue requires at least one authority locator: "
                + ", ".join(sorted(missing))
            )
        return self


class RegisteredResearchPlan(BaseModel):
    """Immutable server record of an untrusted client proposal."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.registered-research-plan/v1"] = (
        "alr-tw.registered-research-plan/v1"
    )
    proposal: ResearchPlanProposal
    received_at: datetime
    proposal_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    trust_status: Literal["untrusted_client_proposal"] = "untrusted_client_proposal"

    @model_validator(mode="after")
    def validate_timestamp_and_digest(self) -> RegisteredResearchPlan:
        if self.received_at.tzinfo is None or self.received_at.utcoffset() is None:
            raise ValueError("registered research plan timestamp must be timezone-aware")
        expected = self.digest(self.proposal)
        if self.proposal_digest != expected:
            raise ValueError("registered research plan digest does not match proposal")
        return self

    @staticmethod
    def digest(proposal: ResearchPlanProposal) -> str:
        payload = json.dumps(
            proposal.model_dump(mode="json", exclude_none=False, by_alias=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def from_proposal(
        cls,
        proposal: ResearchPlanProposal,
        *,
        received_at: datetime,
    ) -> RegisteredResearchPlan:
        return cls(
            proposal=proposal,
            received_at=received_at,
            proposal_digest=cls.digest(proposal),
        )


class InteroperabilityCapabilities(BaseModel):
    """Stable capability negotiation response for arbitrary agent frontends."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.interoperability-capabilities/v1"] = (
        "alr-tw.interoperability-capabilities/v1"
    )
    interface_family: Literal["agent_neutral_legal_research"] = (
        "agent_neutral_legal_research"
    )
    active_data_mode: DataMode
    active_mcp_tool_profile: ToolProfile | None = None
    available_mcp_tool_names: list[str] = Field(default_factory=list)
    supported_discovery_modes: list[DiscoveryMode]
    accepted_plan_schema: Literal["alr-tw.research-plan-proposal/v1"] = (
        "alr-tw.research-plan-proposal/v1"
    )
    accepted_legal_analysis_schema: Literal["alr-tw.legal-analysis/v1"] = (
        "alr-tw.legal-analysis/v1"
    )
    legal_analysis_validation_tool: Literal["validate_legal_analysis"] = (
        "validate_legal_analysis"
    )
    finalization_contract: Literal["alr-tw.finalization/v1"] = (
        "alr-tw.finalization/v1"
    )
    finalization_tool: Literal["get_legal_research_finalization"] = (
        "get_legal_research_finalization"
    )
    structured_refusal_contract: Literal["alr-tw.structured-refusal/v1"] = (
        "alr-tw.structured-refusal/v1"
    )
    supported_legal_analysis_profiles: list[LegalAnalysisProfile]
    legal_context_contract: Literal["alr-tw.legal-context-result/v1"] = (
        "alr-tw.legal-context-result/v1"
    )
    accepted_material_types: list[MaterialType]
    official_verification_material_types: list[MaterialType]
    reasoning_owner: Literal["external_client"] = "external_client"
    verification_owner: Literal["server"] = "server"
    evidence_promotion_owner: Literal["server"] = "server"
    final_decision_owner: Literal["server"] = "server"
    accepts_client_evidence: Literal[False] = False
    accepts_client_fact_states: Literal[False] = False
    accepts_client_trust_decisions: Literal[False] = False
    client_authority_locators_are_candidate_only: Literal[True] = True
    explicit_issue_binding_coverage: Literal[True] = True
    legal_analysis_validation_is_structural: Literal[True] = True
    managed_fact_state_store_available: Literal[False] = False
    semantic_entailment_performed: Literal[False] = False
    external_query_transfer_enabled: bool
    limitations: list[str]


def interoperability_capabilities(
    data_mode: DataMode,
    *,
    active_mcp_tool_profile: ToolProfile | None = None,
    available_mcp_tool_names: list[str] | None = None,
) -> InteroperabilityCapabilities:
    return InteroperabilityCapabilities(
        active_data_mode=data_mode,
        active_mcp_tool_profile=active_mcp_tool_profile,
        available_mcp_tool_names=list(available_mcp_tool_names or ()),
        supported_discovery_modes=[
            DiscoveryMode.SERVER_MANAGED,
            DiscoveryMode.CLIENT_ASSISTED,
        ],
        accepted_material_types=[
            MaterialType.LAW,
            MaterialType.JUDGMENT,
            MaterialType.CONSTITUTIONAL,
        ],
        official_verification_material_types=[
            MaterialType.LAW,
            MaterialType.JUDGMENT,
            MaterialType.CONSTITUTIONAL,
        ],
        supported_legal_analysis_profiles=list(LegalAnalysisProfile),
        external_query_transfer_enabled=data_mode is DataMode.HYBRID_VERIFIED,
        limitations=[
            "client plans are untrusted proposals and cannot create evidence",
            "legal analysis proposals remain untrusted until server validation",
            "managed research runs do not persist server-owned fact states; use evidence "
            "references or integrate the validator with a server-owned fact-state provider",
            "client-assisted discovery requires plan registration before research",
            "live legal-context providers are not bundled in the public development build",
            "counter-authority uses bounded lexical candidate discovery and official verification; "
            "semantic opposition classification and systematic/global coverage are not provided",
            "complete historical law versions are not implemented",
            "semantic entailment and substantive legal correctness are not performed",
        ],
    )
