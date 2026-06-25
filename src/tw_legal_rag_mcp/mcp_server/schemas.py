from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LegalSearchRequest(BaseModel):
    query: str


class CitationValidationRequest(BaseModel):
    citation_id: str
    source_tier: str


class ToolError(BaseModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ToolEnvelope(BaseModel):
    ok: bool
    data: dict[str, Any] | None = None
    error: ToolError | None = None
