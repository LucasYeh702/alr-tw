# ALR-TW Agent Client Guide

ALR-TW records and gates externally driven tool runs. This repository ships no
LLM and no agent implementation. The external MCP client supplies the agent
role; the harness records tool calls, validates citations, computes the trust
gate, and returns a canonical trace.

## v0.10.0 agent tool profiles and selection

v0.10.0 adds a profile-gated MCP catalog and an optional Legislative Yuan
locator connector while preserving the server-owned trust boundary.

The MCP catalog classifies tools as `server_owned`, `legacy_compatibility`, or
`synthetic_demo`. The session resolves one profile at startup:

| Profile | Available tools |
|---|---|
| `verified` | `server_owned` only |
| `compatibility` | `server_owned` plus `legacy_compatibility` |
| `demo` | all catalog entries, including `synthetic_demo` |

`official_only` and `hybrid_verified` default to `verified`; `synthetic` defaults
to `demo`. A deployer may explicitly select a profile with
`ALR_TW_MCP_TOOL_PROFILE`. An unknown value fails closed during startup. The
same profile gate applies to both `tools/list` and `tools/call`; calling a hidden
catalog entry directly returns `TOOL_NOT_AVAILABLE_IN_PROFILE`.

### Tool selection matrix

| Use case | First choice | Boundary |
|---|---|---|
| Single formal authority lookup | `lookup_legal_source` | Source lookup is not answer validation |
| Multi-step research | `research_legal_question` and `continue_legal_research` | Continue server-owned obligations by `operation_id` |
| Analysis validation | `validate_legal_analysis` | Validate the untrusted analysis envelope and references |
| Answer validation | `validate_legal_answer` | Validate claims against evidence from the same run |
| Synthetic demo or CI | `agentic_legal_research`, `legal_search`, `run_agentic_demo`, `build_validation_report`, `exact_law_lookup`, `exact_judgment_lookup`, and `exact_constitutional_lookup` | Synthetic fixtures only; never for real cases |

This matrix is deterministic routing guidance and a server gate. It does not
guarantee that an arbitrary model will select the correct tool. Demo descriptions
are marked `[DEMO ONLY]`; compatibility entries are marked
`[LEGACY COMPATIBILITY]`.

External discovery, including a web search when the deployment permits it, is
not categorically forbidden. Its output may identify candidate identifiers or
locators only. A formal citation must return through server-owned official
verification and source promotion; discovery output itself is never evidence.

### Optional Legislative Yuan locator connector

The Legislative Yuan connector is optional, read-only, bounded, and
candidate-only. It is a locator connector, not a normative-law provider and not
a live production-ready claim. Its bounded dataset roles are:

| Dataset ID | Locator role | Boundary |
|---|---|---|
| `20` | Proposal | Proposal metadata and locator only; it does not directly provide the legislative-reason body |
| `19` | Article comparison | Candidate comparison material, not effective law |
| `46` | Committee bill material | Committee-stage candidate only |
| `8` | Caucus negotiation | Caucus-record candidate only |
| `48` | Passed third-reading bill | Third-reading candidate only, not a promulgated version |

Linked PDF and DOC files are not parsed. If no formally promulgated version can
be bound, the result remains `qualified`. Legislative material must not be
treated as effective statutory text or as the single legislative intent; it
must return to server-owned official verification before any evidence or final
answer use. Synthetic mode never calls the connector. In `official_only` or
`hybrid_verified`, a client explicitly invokes the network lookup by calling
`lookup_legislative_history`; merely starting the stdio server or listing tools
does not fetch Legislative Yuan data.

## v0.10.0 agent-neutral research flow

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
3. Continue server-owned obligations until `ready_for_draft`; this is workflow
   completion only, not a claim of research sufficiency.
4. Call `get_legal_research_finalization` to read server-owned Coverage v2,
   `research_sufficiency`, `answer_mode`, snapshot receipts, blockers, and
   qualifications. Submit `alr-tw.legal-analysis/v1` to `validate_legal_analysis` when a
   structured analysis is needed. One envelope may combine civil substantive,
   civil procedure, substantive criminal, criminal procedure, administrative,
   and constitutional-review branches.
   Treat `qualified` as a mandatory disclosure and discard `blocked`; even
   `validated` does not authorize an answer.
5. Draft externally from server-owned evidence.
6. Call `validate_legal_answer` with evidence IDs and, when a plan is
   registered, the corresponding issue IDs.
7. Treat finalization as a pre-draft posture only. Render only a
   `validated` or `qualified` result returned by `validate_legal_answer`; a
   `refusal_only` finalization must not render a draft.

The snapshot receipt is a provider-neutral contract, not a promise that the
built-in providers issue one. The bundled `ResearchService` does not currently
inject or persist live-provider generation receipts, so its live finalization
is at most `conditional` or `qualified` (normally with
`SNAPSHOT_RECEIPT_MISSING_LEGACY`). `ordinary` is reserved for a deployment
with a receipt-aware provider adapter and a server-owned receipt binding for
the same run. A finalization result may expose `safe_to_draft`; it never
authorizes presentation.

Do not call a full second recall workflow after selecting `server_managed`.
Do not call TLR or an official judgment search again after selecting
`client_assisted` with complete locators. See
[Interoperability Contract](INTEROPERABILITY_CONTRACT.md).

Analysis envelopes accept IDs only. A client must not place source bodies,
content hashes, official attestations, private case data, or provider
credentials inside them. Fact and evidence status labels remain proposals
until matched to server-owned run context. Cross-domain profiles validate
structure and trust references only; they do not perform substantive legal
subsumption.

Synthetic records are demonstration fixtures and cannot support a legal answer.
Counter-authority results are bounded lexical candidate discovery followed by
official verification; they do not establish semantic opposition, global
absence, or practice-wide consensus.

The v0.10.0 public contracts also expose structural applicability resolution,
authority/judgment lineage, and public-law provider adapters. Use the
provider-neutral interfaces for explicit source relationships, court/procedure
metadata, administrative rules or legislative materials. These records remain
provider-supplied and server-bound; they do not perform semantic entailment or
authorize a final answer.

## MCP Client Config

Use stdio. The public server needs no API keys. Synthetic mode makes no network
calls; live modes call official providers only when the client invokes a tool
whose contract requires retrieval.

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

This compatibility flow is available only with the `demo` profile. Its tools
are synthetic and must never be used for a real case or a formal citation.

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
