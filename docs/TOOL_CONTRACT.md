# ALR-TW Tool Contract

## v0.6 high-level tools

| Tool | Required input | Contract |
|---|---|---|
| `research_legal_question` | `query` | 建立 run；optional constraints: `as_of_date`, `research_depth`, `include_counter_authority`, `retention` |
| `continue_legal_research` | `run_id`, `operation_id` | 原子執行一個 obligation；相同 operation id 回相同結果 |
| `get_legal_research_state` | `run_id` | 唯讀；無 provider call、無 TTL extension |
| `lookup_legal_source` | `text` | 精確來源 lookup；可選 run/operation linkage；`claim_verified=false` |
| `validate_legal_answer` | `run_id`, `answer_text`, `operation_id` | 只用 server-owned evidence；回 `validated`, `qualified`, `blocked` |
| `purge_research_storage` | `scope`, `confirm` | `scope=run` 需 `run_id`；同步清除 managed records |

`constraints.retention` 接受 `1s..7d` 或 `ephemeral`。`request_id`／`client_id` 是 correlation metadata，不是 authority 或 idempotency key；只有 `operation_id` 控制會改變狀態的重播。

`lookup_legal_source` 支援法規名稱＋條號、憲法裁判字號、完整 JID，以及含法院／年度／字別／號次的正式裁判字號。正式字號不唯一時回明確 ambiguity error，不猜測。

所有 tool 使用 `alr-tw.mcp_tool_result/v1` envelope。輸入採 `additionalProperties=false`；未知欄位與不支援的 MCP protocol version 都必須拒絕。

All MCP tool results are wrapped in:

```json
{
  "ok": true,
  "schema_version": "alr-tw.mcp_tool_result/v1",
  "data": {},
  "error": null
}
```

## Tools

| Tool | Purpose | Final citation effect |
|---|---|---|
| `agentic_legal_research` | Synthetic agentic RAG loop returning `alr-tw.agentic_trace/v1` | Reports final citations |
| `run_agentic_demo` | Deterministic ALR-TW scenario trace | Reports final action |
| `begin_agentic_run` | Begin recording an externally driven tool run | Opens a server-side run state |
| `finalize_agentic_run` | Assemble and gate a recorded externally driven tool run | Computes final action |
| `get_claim_grounding_policy` | Returns claim-grounding contract for v0.3 | No direct citation effect |
| `extract_answer_claims` | Split an answer into deterministic public claim units | No direct citation effect |
| `check_claim_support` | Check answer claims against evidence segments and return semantic grounding summary | No direct citation effect |
| `build_validation_report` | Markdown validation report | No direct citation effect |
| `get_trust_model` | Source tiers and trust policy | No direct citation effect |
| `legal_search` | Synthetic search demo | Candidate retrieval only |
| `validate_citation` | Validate citation tier and use | Determines final eligibility |
| `exact_law_lookup` | Synthetic exact law lookup | Demo only |
| `exact_judgment_lookup` | Synthetic exact judgment lookup | Demo only |
| `exact_constitutional_lookup` | Synthetic exact constitutional lookup | Demo only |

Invalid JSON-RPC params use protocol errors. Tool outputs use stable schema
versions and fixed error codes when an ALR-TW trust decision fails.

## Trace Output

`agentic_legal_research` and `run_agentic_demo` return the canonical public trace
schema: `alr-tw.agentic_trace/v1`.

Public example tool calls are deterministic harness records. Their
`execution_mode` is `harness_recorded`; they are not live external tool logs.

## Externally Driven Run Recording

v0.5 uses Design A: session-recorded run state. `McpSession` already owns the
stdio request lifecycle, so the server can keep one open run per session without
invasive changes. This design records and gates externally driven tool runs
because the server observes the actual MCP `tools/call` requests before it
assembles the trace. Design B was not used because a submitted transcript would
prove less about tool invocation.

Flow:

1. `begin_agentic_run` accepts only `query` and returns `run_id`.
2. While the run is open, the server records successful calls to
   `legal_search`, `validate_citation`, `exact_law_lookup`,
   `exact_judgment_lookup`, `exact_constitutional_lookup`,
   `extract_answer_claims`, and `check_claim_support`.
3. Recorded calls become `ToolCallTrace` entries with `execution_mode:
   "actual_tool"`.
4. `finalize_agentic_run` accepts only `run_id` and `answer`, assembles
   evidence from recorded `validate_citation` outputs, computes coverage from
   server-observed validation inputs, reuses the deterministic trust-gate path,
   and returns `alr-tw.agentic_trace/v1` with `trace_kind:
   "externally_driven"`.

An externally driven run reaches `answer` only if the client recorded a
`check_claim_support` step whose result is safe; a run with a final citation
but no claim-support step routes to `human_review_required` because claim
grounding is not optional for a presentable answer.

This repository still ships no LLM and no agent implementation. The external
MCP client supplies the agent role; ALR-TW records and gates externally driven
tool runs.

## Non-Bypass Rules

The following fields are always computed server-side:

- `final_action`
- `trust_gate.safe_to_present`
- `citation_use`
- `identifier_resolution`

If a client supplies any of these fields in tool arguments where the schema does
not allow them, the server returns JSON-RPC `-32602` for unexpected or invalid
arguments.

Client-supplied `answer` text is retained in the trace only when the trust gate
passes with `final_action == "answer"` and `safe_to_present == true`. Otherwise
the trace contains `answer: null`.

Source tier semantics are unchanged. `synthetic` remains demo-only,
`external_semantic_recall` remains candidate-only, and `verified_cache` keeps
the v0.4 opt-in identifier-backed rules. Identifier resolution is recomputed by
the server-side synthetic resolver when the opt-in is enabled.

## Citation Validation Metadata

`validate_citation` accepts:

- `citation_id`
- `source_tier`
- optional `official_url`
- optional `official_identifier`
- optional `official_hash`
- optional `verified_at`
- optional `source_label`
- optional `legal_material_type` (`judgment`, `law`, or `constitutional`)

`verified_cache` becomes final-eligible when it has an official URL, an
official content hash, and a verification time. Otherwise it fails closed.

Identifier-backed verified cache is a separate, opt-in capability
(`ALR_TW_IDENTIFIER_BACKED_VERIFIED_CACHE`, default off). When enabled, an
`official_identifier` may substitute for the official URL only for
judgment-type records, and only after the server-side resolver maps the
identifier to a locally stored official original record and the recomputed
content hash matches `official_hash`. The resolution status is computed by the
server; callers cannot declare it, and a bare identifier with a fabricated
hash is rejected with `IDENTIFIER_UNRESOLVED` or `IDENTIFIER_HASH_MISMATCH`.
The public server carries only a synthetic demo resolver.

That server-side rule is scoped to the MCP surface. At the Python library level,
`identifier_resolution` is part of the adapter/verifier trust boundary and must
only be set by the deployer's resolver layer, such as
`resolve_identifier_citation`; setting it by hand is vouching for the record.

`citation_eligibility` still describes source-tier eligibility only.
`check_claim_support` provides explicit claim-grounding status with
`supported` / `partially_supported` / `overstated` / `unsupported` / `contradicted`
and can be used by clients to decide whether human review is needed.
