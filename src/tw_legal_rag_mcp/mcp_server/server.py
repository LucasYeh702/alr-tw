from __future__ import annotations

from dataclasses import dataclass, field
import json
import sys
from typing import Any, TextIO
from uuid import uuid4

from alr_tw.harness.constants import FinalAction, ToolExecutionMode
from alr_tw.harness.orchestrator import _trust_gate_trace
from alr_tw.harness.trace_schema import AgenticRunTrace, EvidenceRecord, ToolCallTrace
from alr_tw.verification.claim_support import (
    AnswerClaim,
    ClaimSupport,
    SemanticGroundingSummary,
    claim_support_failure_reasons,
)

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
from ..legal_nlp.privacy import mask_sensitive_text
from ..legal_nlp.query_normalizer import normalize_query

SERVER_NAME = "alr-tw"
SERVER_VERSION = "0.5.0"
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
RECORDED_AGENTIC_TOOLS = {
    "legal_search",
    "validate_citation",
    "exact_law_lookup",
    "exact_judgment_lookup",
    "exact_constitutional_lookup",
    "extract_answer_claims",
    "check_claim_support",
}


@dataclass
class AgenticRunState:
    run_id: str
    query: str
    normalized_query: str
    tool_calls: list[ToolCallTrace] = field(default_factory=list)
    validations: list[dict[str, Any]] = field(default_factory=list)
    answer_claims: list[dict[str, Any]] = field(default_factory=list)
    claim_support: list[dict[str, Any]] = field(default_factory=list)
    semantic_summary: dict[str, Any] | None = None
    semantic_failure_reasons: list[str] = field(default_factory=list)


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
        self._agentic_runs: dict[str, AgenticRunState] = {}
        self._active_agentic_run_id: str | None = None

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
                    call_tool(
                        _object_params(message.get("params"), "tool call params"),
                        session=self,
                    ),
                )
        except ValueError as exc:
            return error_response(request_id, -32602, str(exc))
        except Exception as exc:
            return error_response(request_id, -32000, str(exc))

        return error_response(request_id, -32601, f"Unknown method: {method}")

    def begin_agentic_run(self, query: str) -> dict[str, Any]:
        if self._active_agentic_run_id is not None:
            raise ValueError("agentic run already open")
        public_query = mask_sensitive_text(query.strip(), mask_names=True)
        normalized_query = normalize_query(public_query)
        run_id = f"run_{uuid4().hex}"
        self._agentic_runs[run_id] = AgenticRunState(
            run_id=run_id,
            query=public_query,
            normalized_query=normalized_query,
        )
        self._active_agentic_run_id = run_id
        return {
            "schema_version": "alr-tw.agentic_run_session/v1",
            "run_id": run_id,
            "trace_kind": "externally_driven",
            "query": public_query,
            "normalized_query": normalized_query,
        }

    def record_agentic_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        if self._active_agentic_run_id is None:
            return
        state = self._agentic_runs[self._active_agentic_run_id]
        state.tool_calls.append(
            ToolCallTrace(
                tool_name=tool_name,
                execution_mode=ToolExecutionMode.ACTUAL_TOOL.value,
                input_summary=_summarize_tool_input(tool_name, arguments),
                output_summary=_summarize_tool_output(tool_name, payload),
                status="success",
            )
        )
        if tool_name == "validate_citation":
            state.validations.append({"input": dict(arguments), "output": dict(payload)})
        elif tool_name == "extract_answer_claims":
            state.answer_claims = list(payload.get("claims", []))
        elif tool_name == "check_claim_support":
            state.answer_claims = list(arguments.get("claims", state.answer_claims))
            state.claim_support = list(payload.get("claim_support", []))
            summary = payload.get("summary")
            state.semantic_summary = dict(summary) if isinstance(summary, dict) else None
            state.semantic_failure_reasons = list(payload.get("failure_reasons", []))

    def finalize_agentic_run(self, run_id: str, answer: str) -> dict[str, Any]:
        state = self._agentic_runs.get(run_id)
        if state is None:
            raise ValueError(f"unknown run_id: {run_id}")
        trace = _external_agentic_trace(state, answer)
        del self._agentic_runs[run_id]
        if self._active_agentic_run_id == run_id:
            self._active_agentic_run_id = None
        return trace.model_dump()


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
            "name": "begin_agentic_run",
            "description": (
                "Begin recording an externally driven tool run. The repo ships no LLM "
                "or agent; the MCP client supplies that role."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Public-safe synthetic legal query.",
                    }
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
        {
            "name": "finalize_agentic_run",
            "description": (
                "Assemble and gate the recorded externally driven tool run. The server "
                "computes the final action and presentation safety."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "string"},
                    "answer": {
                        "type": "string",
                        "description": "Client-drafted answer retained only when the gate passes.",
                    },
                },
                "required": ["run_id", "answer"],
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


def call_tool(params: dict[str, Any], *, session: McpSession | None = None) -> dict[str, Any]:
    _reject_unexpected_keys(params, {"name", "arguments"})
    name = _required_string(params, "name")
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise ValueError("tool arguments must be an object")

    if name == "begin_agentic_run":
        if session is None:
            raise ValueError("begin_agentic_run requires an MCP session")
        _reject_unexpected_keys(arguments, {"query"})
        payload = session.begin_agentic_run(_required_string(arguments, "query"))
    elif name == "finalize_agentic_run":
        if session is None:
            raise ValueError("finalize_agentic_run requires an MCP session")
        _reject_unexpected_keys(arguments, {"run_id", "answer"})
        payload = session.finalize_agentic_run(
            _required_string(arguments, "run_id"),
            _required_string(arguments, "answer"),
        )
    elif name == "agentic_legal_research":
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

    if session is not None and name in RECORDED_AGENTIC_TOOLS:
        session.record_agentic_tool_call(name, arguments, payload)

    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(_tool_success(payload), ensure_ascii=False, indent=2),
            }
        ],
        "isError": False,
    }


def _summarize_tool_input(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if tool_name == "extract_answer_claims":
        return {"answer_length": len(str(arguments.get("answer", "")))}
    if tool_name == "check_claim_support":
        return {
            "answer_length": len(str(arguments.get("answer", ""))),
            "claim_count": len(arguments.get("claims", [])),
            "segment_count": len(arguments.get("segments", [])),
        }
    return {
        key: _summary_value(value)
        for key, value in arguments.items()
        if key not in {"answer", "claims", "segments"}
    }


def _summarize_tool_output(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if tool_name == "validate_citation":
        return {
            "citation_id": payload.get("citation_id"),
            "source_tier": payload.get("source_tier"),
            "citation_use": payload.get("citation_use"),
            "status": payload.get("status"),
            "citation_eligibility": payload.get("citation_eligibility"),
            "identifier_resolution": payload.get("identifier_resolution"),
        }
    if tool_name == "extract_answer_claims":
        claims = payload.get("claims", [])
        return {
            "claim_count": payload.get("count", len(claims)),
            "claim_ids": [claim.get("claim_id") for claim in claims if isinstance(claim, dict)],
        }
    if tool_name == "check_claim_support":
        items = payload.get("claim_support", [])
        return {
            "summary": payload.get("summary", {}),
            "support_statuses": [
                item.get("support_status") for item in items if isinstance(item, dict)
            ],
            "failure_reasons": payload.get("failure_reasons", []),
        }
    if tool_name == "legal_search":
        coverage = payload.get("coverage", {})
        return {
            "normalized_query": payload.get("normalized_query"),
            "coverage": coverage if isinstance(coverage, dict) else {},
            "result_keys": sorted(payload.keys()),
        }
    if tool_name.startswith("exact_"):
        return {
            "citation_id": payload.get("citation_id"),
            "source_id": payload.get("source_id"),
            "source_tier": payload.get("source_tier"),
            "status": payload.get("status"),
            "citation_use": payload.get("citation_use"),
        }
    return {"result_keys": sorted(payload.keys())}


def _summary_value(value: Any) -> Any:
    if isinstance(value, str):
        return value if len(value) <= 120 else value[:117] + "..."
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return {"type": "array", "count": len(value)}
    if isinstance(value, dict):
        return {"type": "object", "keys": sorted(value.keys())}
    return str(type(value).__name__)


def _external_agentic_trace(state: AgenticRunState, answer: str) -> AgenticRunTrace:
    evidence = _evidence_from_recorded_validations(state.validations)
    coverage = _coverage_from_recorded_validations(state.validations)
    answer_claims = [AnswerClaim.model_validate(item) for item in state.answer_claims]
    claim_support = [ClaimSupport.model_validate(item) for item in state.claim_support]
    semantic_summary = (
        SemanticGroundingSummary.model_validate(state.semantic_summary)
        if state.semantic_summary is not None
        else SemanticGroundingSummary()
    )
    semantic_reasons = state.semantic_failure_reasons or claim_support_failure_reasons(
        semantic_summary
    )
    trust_gate = _trust_gate_trace(
        evidence=evidence,
        coverage=coverage,
        semantic_summary=semantic_summary,
        semantic_reason_override=semantic_reasons,
    )
    if trust_gate.recommended_action != FinalAction.ANSWER.value:
        semantic_summary.semantic_safe_to_present = False

    final_action = trust_gate.recommended_action
    answer_to_retain = (
        answer if final_action == FinalAction.ANSWER.value and trust_gate.safe_to_present else None
    )
    final_citation_count = sum(1 for item in evidence if item.citation_use == "allow_final")
    tool_names = [tool_call.tool_name for tool_call in state.tool_calls]

    return AgenticRunTrace(
        trace_kind="externally_driven",
        query=state.query,
        normalized_query=state.normalized_query,
        steps=[
            {"from": source, "to": target}
            for source, target in zip(tool_names, tool_names[1:], strict=False)
        ],
        tool_calls=state.tool_calls,
        decision_trace=[
            {
                "step": "citation_validation",
                "final_citation_count": final_citation_count,
                "candidate_count": len(evidence),
            },
            {
                "step": "claim_support",
                "claim_count": semantic_summary.claim_count,
                "semantic_safe_to_present": semantic_summary.semantic_safe_to_present,
                "failure_reasons": list(semantic_reasons),
            },
            {
                "step": "trust_gate",
                "safe_to_present": trust_gate.safe_to_present,
                "failure_reasons": list(trust_gate.failure_reasons),
                "final_action": final_action,
                "answer_present": answer_to_retain is not None,
            },
        ],
        evidence=evidence,
        coverage=coverage,
        answer_claims=answer_claims,
        claim_support=claim_support,
        semantic_grounding_summary=semantic_summary,
        semantic_failure_reasons=list(semantic_reasons),
        trust_gate=trust_gate,
        final_action=final_action,
        answer=answer_to_retain,
        human_review_notes=_human_review_notes(final_action),
    )


def _evidence_from_recorded_validations(
    validations: list[dict[str, Any]],
) -> list[EvidenceRecord]:
    evidence: list[EvidenceRecord] = []
    for item in validations:
        tool_input = item["input"]
        output = item["output"]
        citation_id = str(output["citation_id"])
        evidence.append(
            EvidenceRecord(
                citation_id=citation_id,
                source_id=str(tool_input.get("source_id") or citation_id),
                source_tier=str(output["source_tier"]),
                citation_use=str(output["citation_use"]),
                title=tool_input.get("source_label"),
                snippet=None,
                official_url=output.get("official_url"),
                validation_status=str(output["status"]),
            )
        )
    return evidence


def _coverage_from_recorded_validations(validations: list[dict[str, Any]]) -> dict[str, str]:
    if not validations:
        return {"has_laws": "absent", "has_judgments": "not_checked"}

    material_types = {
        item["input"].get("legal_material_type")
        for item in validations
        if item["input"].get("legal_material_type")
    }
    has_laws = (
        "present"
        if not material_types or "law" in material_types
        else "not_checked"
    )
    has_judgments = "present" if "judgment" in material_types else "not_checked"
    return {"has_laws": has_laws, "has_judgments": has_judgments}


def _human_review_notes(final_action: str) -> list[str]:
    if final_action == FinalAction.HUMAN_REVIEW_REQUIRED.value:
        return ["Recorded tool run requires human legal review before presenting an answer."]
    return []


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
