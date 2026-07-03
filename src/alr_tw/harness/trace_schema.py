from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from alr_tw.verification.claim_support import (
    AnswerClaim,
    ClaimSupport,
    SemanticGroundingSummary,
)


class ToolCallTrace(BaseModel):
    tool_name: str
    execution_mode: Literal["harness_recorded", "actual_tool"] = "harness_recorded"
    input_summary: dict[str, Any] = Field(default_factory=dict)
    output_summary: dict[str, Any] = Field(default_factory=dict)
    status: Literal["success", "fail", "skipped"]
    error_code: str | None = None


class EvidenceRecord(BaseModel):
    citation_id: str
    source_id: str
    source_tier: str
    citation_use: str
    title: str | None = None
    snippet: str | None = None
    official_url: str | None = None
    validation_status: str | None = None


class TrustGateTrace(BaseModel):
    safe_to_present: bool
    failure_reasons: list[str] = Field(default_factory=list)
    validation_summary: dict[str, Any] = Field(default_factory=dict)
    recommended_action: Literal["answer", "refuse", "human_review_required"] = "refuse"


class AgenticRunTrace(BaseModel):
    schema_version: str = "alr-tw.agentic_trace/v1"
    query: str
    normalized_query: str | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)
    decision_trace: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    coverage: dict[str, Any] = Field(default_factory=dict)
    answer_claims: list[AnswerClaim] = Field(default_factory=list)
    claim_support: list[ClaimSupport] = Field(default_factory=list)
    semantic_grounding_summary: SemanticGroundingSummary = Field(
        default_factory=SemanticGroundingSummary,
    )
    semantic_failure_reasons: list[str] = Field(default_factory=list)
    trust_gate: TrustGateTrace
    final_action: Literal["answer", "refuse", "human_review_required"]
    answer: str | None = None
    human_review_notes: list[str] = Field(default_factory=list)
