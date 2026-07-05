# ALR-TW Agent Client Guide

ALR-TW records and gates externally driven tool runs. This repository ships no
LLM and no agent implementation. The external MCP client supplies the agent
role; the harness records tool calls, validates citations, computes the trust
gate, and returns a canonical trace.

## MCP Client Config

Use stdio. The public server needs no API keys and makes no network calls.

```json
{
  "mcpServers": {
    "alr-tw": {
      "command": "uv",
      "args": ["run", "--extra", "dev", "alr-tw-mcp"],
      "cwd": "/path/to/tw-legal-rag-mcp-reference"
    }
  }
}
```

## Suggested Tool Flow

1. Call `begin_agentic_run` with a public-safe query and keep the returned
   `run_id`.
2. Call `legal_search` or exact lookup tools to gather synthetic candidate
   records.
3. Call `validate_citation` for every candidate citation before treating it as
   evidence.
4. Draft answer text in the external client, then call `extract_answer_claims`.
5. Call `check_claim_support` with the extracted claims and evidence segments.
6. Call `finalize_agentic_run` with `run_id` and the drafted `answer`.
7. Render the answer only when `final_action == "answer"` and
   `trust_gate.safe_to_present == true`.

If the gate refuses or requires review, the trace keeps `answer: null`. The
client must not render the dropped answer body from its own draft state.

## Server-Side Controls

`final_action`, `trust_gate.safe_to_present`, `citation_use`, and
`identifier_resolution` are computed by the server. Client-supplied values for
those fields are rejected as invalid arguments.

`external_semantic_recall` remains candidate-only. `synthetic` remains
demo-only. `verified_cache` follows the existing opt-in identifier-backed rules
and is still resolved by the server-side synthetic resolver in the public
server.

Externally driven traces prove tool invocation through `execution_mode:
"actual_tool"` and `trace_kind: "externally_driven"`. They do not prove answer
quality beyond the deterministic checks represented in the trace.
