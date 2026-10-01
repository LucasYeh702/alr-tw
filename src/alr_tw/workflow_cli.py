"""Convenience commands using the same MCP dispatch and trust gates as agents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from alr_tw.config import Settings
from alr_tw.verification.claim_support import ClaimBinding
from tw_legal_rag_mcp.mcp_server.server import McpSession


MAX_DRAFT_BYTES = 1024 * 1024


class DraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    answer_text: str = Field(min_length=1, max_length=100_000)
    claim_bindings: list[ClaimBinding] = Field(max_length=256)


def read_draft(path: str) -> dict[str, Any]:
    """Read only a draft and bindings; never import caller evidence or trust."""
    try:
        with Path(path).expanduser().open("rb") as stream:
            raw = stream.read(MAX_DRAFT_BYTES + 1)
        if len(raw) > MAX_DRAFT_BYTES:
            raise ValueError("DRAFT_INPUT_TOO_LARGE")
        draft = DraftInput.model_validate_json(raw)
        if not draft.answer_text.strip():
            raise ValueError("DRAFT_INPUT_INVALID")
    except (OSError, ValidationError, UnicodeError) as exc:
        # ValidationError may include the confidential draft; do not echo it.
        raise ValueError("DRAFT_INPUT_INVALID") from exc
    return draft.model_dump(mode="json")


def call_tool(session: McpSession, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    response = session.handle_message({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    if response is not None and "error" in response:
        message = response["error"].get("message")
        if message in {
            "RESEARCH_RUN_EXPIRED", "OFFICIAL_TLS_VERIFICATION_FAILED",
            "DRAFT_INPUT_INVALID", "DRAFT_CLAIM_NOT_IN_TEXT", "WORKFLOW_STEPS_INVALID",
            "PACK_TRUST_REVOKED", "PACK_SYNTHETIC_NOT_LIVE", "PACK_KEY_REQUIRED", "PACK_EXPIRED_OR_NOT_YET_VALID", "PACK_INVALID",
            "OPERATION_FAILED", "OPERATION_REQUEST_MISMATCH", "OPERATION_RESULT_STALE", "OPERATION_IN_PROGRESS", "OPERATION_ALREADY_COMPLETED",
            "STORAGE_PATH_UNSAFE", "STORAGE_PATH_CHANGED", "STORAGE_PATH_PLATFORM_UNSUPPORTED",
        }:
            raise ValueError(message)
    if response is None or "error" in response:
        raise ValueError("WORKFLOW_DISPATCH_FAILED")
    envelope = json.loads(response["result"]["content"][0]["text"])
    if not envelope.get("ok"):
        # Server errors may contain caller input; return the stable code only.
        error = envelope.get("error", {})
        code = error.get("code", "WORKFLOW_TOOL_FAILED") if isinstance(error, dict) else "WORKFLOW_TOOL_FAILED"
        raise ValueError(str(code))
    data: dict[str, Any] = envelope["data"]
    return data


def run_workflow(args: Any, settings: Settings) -> dict[str, Any]:
    if args.storage_path:
        settings = settings.model_copy(update={"storage_path": Path(args.storage_path).expanduser()})
    # Parse a draft before creating a session or touching managed storage.
    draft = read_draft(args.input_path) if args.command in {"validate-draft", "review-draft", "complete-research", "advise-draft"} else None
    session = McpSession(ready=True, settings=settings)
    if args.command == "quick-research":
        constraints: dict[str, Any] = {
            "research_depth": "quick",
            "max_judgment_verifications": args.max_judgments,
        }
        if args.as_of_date:
            constraints["as_of_date"] = args.as_of_date
        return call_tool(session, "execute_legal_research", {
            "query": args.query, "constraints": constraints, "max_steps": args.max_steps,
        })
    if args.command == "research-status":
        return call_tool(session, "get_legal_research_state", {"run_id": args.run_id})
    assert draft is not None
    if args.command == "advise-draft":
        from alr_tw.providers.data_pack import bounded_read
        from alr_tw.research.semantic_advisor import AdvisorConfig, advise_draft

        try:
            config = AdvisorConfig.model_validate_json(bounded_read(Path(args.gateway_config), 65536))
        except ValueError as exc:
            raise ValueError("ADVISOR_CONFIG_INVALID") from exc
        return advise_draft(session.research_service().store, args.run_id, draft, config)
    if args.command == "review-draft":
        return call_tool(session, "review_legal_draft", {**draft, "run_id": args.run_id})
    if args.command == "complete-research":
        return call_tool(session, "complete_legal_research", {
            **draft, "run_id": args.run_id, "operation_id": args.operation_id,
            "max_steps": args.max_steps,
        })
    return call_tool(session, "validate_legal_answer", {
        **draft, "run_id": args.run_id,
        "operation_id": args.operation_id or f"draft-{uuid4().hex}",
    })
