from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from .tools import (
    agentic_legal_research,
    build_validation_report_tool,
    exact_constitutional_lookup_tool,
    exact_judgment_lookup_tool,
    exact_law_lookup_tool,
    extract_answer_claims_tool,
    get_trust_model_tool,
    check_claim_support_tool,
    get_claim_grounding_policy_tool,
    legal_search,
    run_agentic_demo_tool,
    validate_citation_tool,
)

SERVER_NAME = "alr-tw"
SERVER_VERSION = "0.4.0"
DEFAULT_PROTOCOL_VERSION = "2024-11-05"
SUPPORTED_PROTOCOL_VERSIONS = {DEFAULT_PROTOCOL_VERSION}
SOURCE_TIER_VALUES = {
    "official",
    "verified_cache",
    "staging",
    "external_semantic_recall",
    "synthetic",
    "unknown",
}
LEGAL_MATERIAL_TYPE_VALUES = {"judgment", "law", "constitutional"}


def main() -> None:
    run_stdio_server(sys.stdin, sys.stdout)


def run_stdio_server(input_stream: TextIO, output_stream: TextIO) -> None:
    session = McpSession()
    for line in input_stream:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = session.handle_message(request)
        except Exception as exc:
            response = error_response(None, -32700, f"Invalid request: {exc}")
        if response is not None:
            output_stream.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            output_stream.flush()


def handle_message(message: dict[str, Any]) -> dict[str, Any] | None:
    return McpSession(ready=True).handle_message(message)


class McpSession:
    def __init__(self, *, ready: bool = False) -> None:
        self._initialize_seen = ready
        self._ready = ready

    def handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(message, dict):
            return error_response(None, -32600, "Invalid request")

        has_request_id = "id" in message
        request_id = message.get("id") if has_request_id else None
        method = message.get("method")

        if not has_request_id:
            if method == "notifications/initialized" and self._initialize_seen:
                self._ready = True
            return None

        try:
            if method == "initialize":
                result = initialize_result(_object_params(message.get("params"), "initialize params"))
                self._initialize_seen = True
                return success_response(request_id, result)
            if method == "ping":
                return success_response(request_id, {})
            if not self._ready:
                return error_response(request_id, -32002, "Server not initialized")
            if method == "tools/list":
                return success_response(request_id, {"tools": tool_definitions()})
            if method == "tools/call":
                return success_response(
                    request_id,
                    call_tool(_object_params(message.get("params"), "tool call params")),
                )
        except ValueError as exc:
            return error_response(request_id, -32602, str(exc))
        except Exception as exc:
            return error_response(request_id, -32000, str(exc))

        return error_response(request_id, -32601, f"Unknown method: {method}")


def initialize_result(params: dict[str, Any]) -> dict[str, Any]:
    requested = params.get("protocolVersion") or DEFAULT_PROTOCOL_VERSION
    if not isinstance(requested, str):
        raise ValueError("protocolVersion must be a string")
    if requested not in SUPPORTED_PROTOCOL_VERSIONS:
        raise ValueError(f"Unsupported protocol version: {requested}")
    return {
        "protocolVersion": DEFAULT_PROTOCOL_VERSION,
        "serverInfo": {
            "name": SERVER_NAME,
            "version": SERVER_VERSION,
        },
        "capabilities": {
            "tools": {},
        },
    }


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "agentic_legal_research",
            "description": (
                "Run a public-safe synthetic agentic RAG loop with tool trace, citation "
                "validation, and fail-closed trust gate."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Synthetic legal research query. Do not include private facts.",
                    }
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
        {
            "name": "legal_search",
            "description": "Search the bundled synthetic legal demo data.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Synthetic legal search query."}
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
        {
            "name": "run_agentic_demo",
            "description": "Run a deterministic ALR-TW agentic legal RAG demo scenario.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "scenario": {"type": "string"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
        {
            "name": "build_validation_report",
            "description": "Build a Markdown validation report for an ALR-TW agentic demo scenario.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "scenario": {"type": "string"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
        {
            "name": "get_claim_grounding_policy",
            "description": "Return the public claim-grounding contract used by ALR-TW v0.3.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        {
            "name": "extract_answer_claims",
            "description": "Split an answer into deterministic public claim units.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "answer": {"type": "string"},
                },
                "required": ["answer"],
                "additionalProperties": False,
            },
        },
        {
            "name": "check_claim_support",
            "description": (
                "Validate whether answer claims are supported by provided evidence segments "
                "and return semantic grounding summary for human review."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "answer": {"type": "string"},
                    "claims": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "segments": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                },
                "required": ["answer", "claims", "segments"],
                "additionalProperties": False,
            },
        },
        {
            "name": "get_trust_model",
            "description": "Return the ALR-TW public source trust model.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        {
            "name": "validate_citation",
            "description": "Validate whether a citation source tier can be used as a final citation.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "citation_id": {"type": "string"},
                    "legal_material_type": {
                        "type": "string",
                        "enum": ["judgment", "law", "constitutional"],
                    },
                    "official_hash": {"type": "string"},
                    "official_identifier": {"type": "string"},
                    "official_url": {"type": "string"},
                    "source_label": {"type": "string"},
                    "source_tier": {
                        "type": "string",
                        "enum": [
                            "official",
                            "verified_cache",
                            "staging",
                            "external_semantic_recall",
                            "synthetic",
                            "unknown",
                        ],
                    },
                    "verified_at": {"type": "string"},
                },
                "required": ["citation_id", "source_tier"],
                "additionalProperties": False,
            },
        },
        {
            "name": "exact_law_lookup",
            "description": "Look up a synthetic law article by title and article number.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "article_no": {"type": "string"},
                },
                "required": ["title", "article_no"],
                "additionalProperties": False,
            },
        },
        {
            "name": "exact_judgment_lookup",
            "description": "Look up a synthetic judgment by jid.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "jid": {"type": "string"},
                },
                "required": ["jid"],
                "additionalProperties": False,
            },
        },
        {
            "name": "exact_constitutional_lookup",
            "description": "Look up a synthetic Constitutional Court record by source id.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "source_id": {"type": "string"},
                },
                "required": ["source_id"],
                "additionalProperties": False,
            },
        },
    ]


def call_tool(params: dict[str, Any]) -> dict[str, Any]:
    _reject_unexpected_keys(params, {"name", "arguments"})
    name = _required_string(params, "name")
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise ValueError("tool arguments must be an object")

    if name == "agentic_legal_research":
        _reject_unexpected_keys(arguments, {"query"})
        payload = agentic_legal_research(_required_string(arguments, "query"))
    elif name == "get_claim_grounding_policy":
        _reject_unexpected_keys(arguments, set())
        payload = get_claim_grounding_policy_tool()
    elif name == "extract_answer_claims":
        _reject_unexpected_keys(arguments, {"answer"})
        payload = extract_answer_claims_tool(_required_string(arguments, "answer"))
    elif name == "check_claim_support":
        _reject_unexpected_keys(arguments, {"answer", "claims", "segments"})
        payload = check_claim_support_tool(
            _required_string(arguments, "answer"),
            claims=_required_array_of_dict(arguments, "claims"),
            segments=_required_array_of_dict(arguments, "segments"),
        )
    elif name == "legal_search":
        _reject_unexpected_keys(arguments, {"query"})
        payload = legal_search(_required_string(arguments, "query"))
    elif name == "run_agentic_demo":
        _reject_unexpected_keys(arguments, {"query", "scenario"})
        payload = run_agentic_demo_tool(
            _required_string(arguments, "query"),
            _optional_string(arguments, "scenario", default="auto"),
        )
    elif name == "build_validation_report":
        _reject_unexpected_keys(arguments, {"query", "scenario"})
        payload = build_validation_report_tool(
            _required_string(arguments, "query"),
            _optional_string(arguments, "scenario", default="auto"),
        )
    elif name == "get_trust_model":
        _reject_unexpected_keys(arguments, set())
        payload = get_trust_model_tool()
    elif name == "validate_citation":
        _reject_unexpected_keys(
            arguments,
            {
                "citation_id",
                "source_tier",
                "official_url",
                "official_identifier",
                "official_hash",
                "verified_at",
                "source_label",
                "legal_material_type",
            },
        )
        source_tier = _required_string(arguments, "source_tier")
        if source_tier not in SOURCE_TIER_VALUES:
            raise ValueError(f"source_tier must be one of: {', '.join(sorted(SOURCE_TIER_VALUES))}")
        legal_material_type = _optional_string(arguments, "legal_material_type", default=None)
        if legal_material_type is not None and legal_material_type not in LEGAL_MATERIAL_TYPE_VALUES:
            raise ValueError(
                "legal_material_type must be one of: "
                + ", ".join(sorted(LEGAL_MATERIAL_TYPE_VALUES))
            )
        payload = validate_citation_tool(
            _required_string(arguments, "citation_id"),
            source_tier,
            _optional_string(arguments, "official_url", default=None),
            _optional_string(arguments, "official_identifier", default=None),
            _optional_string(arguments, "official_hash", default=None),
            _optional_string(arguments, "verified_at", default=None),
            _optional_string(arguments, "source_label", default=None),
            legal_material_type,
        )
    elif name == "exact_law_lookup":
        _reject_unexpected_keys(arguments, {"title", "article_no"})
        payload = exact_law_lookup_tool(
            _required_string(arguments, "title"),
            _required_string(arguments, "article_no"),
        )
    elif name == "exact_judgment_lookup":
        _reject_unexpected_keys(arguments, {"jid"})
        payload = exact_judgment_lookup_tool(_required_string(arguments, "jid"))
    elif name == "exact_constitutional_lookup":
        _reject_unexpected_keys(arguments, {"source_id"})
        payload = exact_constitutional_lookup_tool(_required_string(arguments, "source_id"))
    else:
        raise ValueError(f"Unknown tool: {name}")

    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(_tool_success(payload), ensure_ascii=False, indent=2),
            }
        ],
        "isError": False,
    }


def _required_string(arguments: dict[str, Any], name: str) -> str:
    if name not in arguments:
        raise ValueError(f"{name} is required")
    raw_value = arguments[name]
    if not isinstance(raw_value, str):
        raise ValueError(f"{name} must be a string")
    value = raw_value.strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _optional_string(arguments: dict[str, Any], name: str, *, default: str | None) -> str | None:
    if name not in arguments:
        return default
    raw_value = arguments[name]
    if not isinstance(raw_value, str):
        raise ValueError(f"{name} must be a string")
    value = raw_value.strip()
    return value or default


def _required_array_of_dict(arguments: dict[str, Any], name: str) -> list[dict[str, Any]]:
    if name not in arguments:
        raise ValueError(f"{name} is required")
    raw_value = arguments[name]
    if not isinstance(raw_value, list) or not all(isinstance(item, dict) for item in raw_value):
        raise ValueError(f"{name} must be an array of objects")
    return raw_value


def _reject_unexpected_keys(arguments: dict[str, Any], allowed: set[str]) -> None:
    unexpected = sorted(set(arguments) - allowed)
    if unexpected:
        raise ValueError(f"unexpected arguments: {', '.join(unexpected)}")


def _object_params(params: Any, label: str) -> dict[str, Any]:
    if params is None:
        return {}
    if not isinstance(params, dict):
        raise ValueError(f"{label} must be an object")
    return params


def _tool_success(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "schema_version": "alr-tw.mcp_tool_result/v1",
        "data": payload,
        "error": None,
    }


def success_response(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
        },
    }
