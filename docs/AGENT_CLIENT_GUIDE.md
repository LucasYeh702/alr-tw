# ALR-TW Agent Client Guide

ALR-TW records and gates externally driven tool runs. This repository ships no
LLM and no agent implementation. The external MCP client supplies the agent
role; the harness records tool calls, validates citations, computes the trust
gate, and returns a canonical trace.

## v0.7.0 agent-neutral research flow

New clients should first call `get_legal_research_capabilities`.

Choose one discovery mode:

- `server_managed`: ALR-TW performs its bounded source discovery;
- `client_assisted`: the client calls `submit_legal_research_plan` with legal
  issues and exact authority locators before continuing the run.

The client name, model, framework, and prompt format are not part of the
contract. In `client_assisted`, the client owns issue analysis but does not own
source verification:

1. Create the run with `research_legal_question`.
2. Submit an `alr-tw.research-plan-proposal/v1`.
3. Continue server-owned obligations until `ready_for_draft`.
4. If the client produces a structured civil analysis, submit
   `alr-tw.civil-law-analysis/v1` to `validate_civil_analysis`. Treat
   `qualified` as a mandatory disclosure and discard `blocked`; even
   `validated` does not authorize an answer.
5. Draft externally from server-owned evidence.
6. Call `validate_legal_answer` with evidence IDs and, when a plan is
   registered, the corresponding issue IDs.
7. Render only final-answer `validated` or `qualified`.

Do not call a full second recall workflow after selecting `server_managed`.
Do not call TLR or an official judgment search again after selecting
`client_assisted` with complete locators. See
[Interoperability Contract](INTEROPERABILITY_CONTRACT.md).

The civil-analysis envelope accepts IDs only. A client must not place source
bodies, content hashes, official attestations, private case data, or provider
credentials inside it. Fact and evidence status labels remain proposals until
matched to server-owned run context.

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

## Legacy synthetic trace flow

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

An externally driven run reaches `answer` only if the client recorded a
`check_claim_support` step whose result is safe; a run with a final citation
but no claim-support step routes to `human_review_required` because claim
grounding is not optional for a presentable answer.

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
