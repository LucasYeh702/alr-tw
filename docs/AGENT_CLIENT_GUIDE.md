# ALR-TW Agent Client Guide

ALR-TW records and gates externally driven tool runs. This repository ships no
LLM and no agent implementation. The external MCP client supplies the agent
role; the harness records tool calls, validates citations, computes the trust
gate, and returns a canonical trace.

## v0.12.0 agent tool profiles and selection

v0.12.0 provides a profile-gated MCP catalog and an optional Legislative Yuan
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
| Fast bounded judgment research | `/quick` with `execute_legal_research` | At most five exact official checks; verified subset only, no completeness, finality, or consensus claim |
| Bounded appeal-chain check for a same-run verified judgment | `inspect_judgment_lineage` | TLR history is candidate metadata; related nodes require official verification, no upper record does not establish finality, and opinion comparison is not performed |
| Granular or client-assisted research | `research_legal_question` and `continue_legal_research` | Continue server-owned obligations by `operation_id` |
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

## v0.12.0 agent-neutral research flow

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
4. Before relying on a verified judgment's view, a deployment with TLR enabled
   may call `inspect_judgment_lineage` with that same-run six-part JID. Review
   officially verified disposition codes and evidence; do not infer finality
   from an absent upper record or infer a different opinion from the chain alone.
5. Call `get_legal_research_finalization` to read server-owned Coverage v2,
   `research_sufficiency`, `answer_mode`, snapshot receipts, blockers, and
   qualifications. Submit `alr-tw.legal-analysis/v1` to `validate_legal_analysis` when a
   structured analysis is needed. One envelope may combine civil substantive,
   civil procedure, substantive criminal, criminal procedure, administrative,
   and constitutional-review branches.
   Treat `qualified` as a mandatory disclosure and discard `blocked`; even
   `validated` does not authorize an answer.
6. Draft externally from server-owned evidence.
7. Call `validate_legal_answer` with evidence IDs and, when a plan is
   registered, the corresponding issue IDs.
8. Treat finalization as a pre-draft posture only. Render only a
   `validated` or `qualified` result returned by `validate_legal_answer`; a
   `refusal_only` finalization must not render a draft.

### Quick server-managed path

For a judgment-finding task, the client may call `execute_legal_research` with a
query beginning `/quick ` or `快速模式：`, or set
`constraints.research_depth=quick`. The composite tool creates the run and
executes its currently available server-owned obligations in one request. It
returns a bounded evidence bundle only at `ready_for_draft`; the bundle is not
an answer and is marked `answer_authorized=false`.

Quick mode changes breadth, not authenticity. It still performs privacy
screening in hybrid mode, candidate recall, canonical-JID/formal-citation
resolution, at most five exact official checks, and evidence sufficiency. It
does not schedule counter-authority or lineage expansion by default, and only
schedules law research when the query explicitly cites a statute article. A
verified subset with gaps is `qualified` / `conditional`; no verified source is
`refusal_only`. In both cases the final draft must pass
`validate_legal_answer`.

When the run is incomplete or blocked, read `research_brief` from
`get_legal_research_state`. It is the supported non-answer exit: it contains
verified source locators, obligation progress, blockers, and safe next actions,
but never a draft conclusion and always sets `answer_authorized=false` and
`safe_to_present=false`. Do not bypass the service by reading its SQLite store.

The evidence bundle is passage-oriented. It returns at most five judgment
sources while reserving bounded capacity for law and constitutional sources.
For large runs, `allowed_evidence_ids` is only a 512-ID compatibility preview;
the full passage set is digest-bound in `evidence_authorization`, and final
validation resolves only the IDs actually named by `claim_bindings` against
the server-owned run.

The bundled `ResearchService` issues and persists a provider-neutral snapshot
receipt for each provider's exact, eligible official/verified-cache material
set in the same run. Finalization recomputes that server-owned binding and does
not trust caller receipts. `ordinary` is reachable only when the receipt set and
all other gates pass; a missing receipt is at most `conditional`, while an
expired, cross-run, or mismatched set fails closed. A finalization result may
expose `safe_to_draft`; it never authorizes presentation.

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

The v0.12.0 public contracts also expose structural applicability resolution,
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
