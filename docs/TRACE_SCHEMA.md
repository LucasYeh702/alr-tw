# ALR-TW Trace Schema

## v0.6 research state records

v0.6 高階流程以持久化 `ResearchRun` 與逐步 result 取代 caller 組裝 authority trace：

- `alr-tw.research-run/v1`：狀態、mode、privacy、obligations、coverage、source/evidence ids、TTL；
- `alr-tw.research-step-result/v1`：本次 obligation、provider calls、warnings、剩餘 obligations；
- `alr-tw.legal-source-lookup/v1`：精確來源結果，固定 `claim_verified=false`；
- `alr-tw.answer-validation/v2`：decision、claim support、citations、qualification 或 blockers。

Trace 不得記錄 API secret。TLR privacy metadata 不得包含未遮罩的 sensitive input。Blocked validation 的 `answer_text` 必須是 `null`；ephemeral validation 另回 `storage_purged=true`。

舊 `alr-tw.agentic_trace/v1` 保留 synthetic／externally-driven compatibility，但不得用它把 caller-attested source 注入 v0.6 evidence。

The public trace schema version is `alr-tw.agentic_trace/v1`.

This repository does not ship an LLM or agent implementation. Traces emitted by
`agentic_legal_research` and `run_agentic_demo` are deterministic synthetic
harness outputs that an external MCP client or LLM runtime can inspect. The
files under `examples/agentic_runs/*.json` are not recordings of agent
reasoning or live external tool execution.

## Main Objects

- `AgenticRunTrace`: optional trace kind, query, normalized query, steps, tool calls, decision trace, evidence, coverage, trust gate, claim grounding outputs (`answer_claims`, `claim_support`, `semantic_grounding_summary`, `semantic_failure_reasons`), final action, optional answer, and human review notes.
- `ToolCallTrace`: tool name, execution mode, input summary, output summary, status, and optional error code.
- `EvidenceRecord`: citation id, source id, source tier, citation use, title, snippet, official URL, and validation status.
- `TrustGateTrace`: safe flag, failure reasons, validation summary, and recommended action.
- `AnswerClaim`: claim id, claim text, claim type, referenced citation IDs, and importance.
- `ClaimSupport`: per-claim support status, supporting legal segments, risk flags, and review requirement.
- `SemanticGroundingSummary`: claim-support counts by status and semantic safety flag.

## Tool Execution Semantics

`execution_mode` is required to avoid overclaiming what happened inside the
public demo.

| Value | Meaning |
|---|---|
| `harness_recorded` | Deterministic harness step recorded by the public demo graph. |
| `actual_tool` | Server-recorded MCP tool call made by an external client during an open run. |

The public examples use `harness_recorded` and
`output_summary.trace_kind: "deterministic_harness_step"`. They are not live
external tool execution logs.

## Trace Kind

`trace_kind` is optional at the top level.

| Value | When it appears | Meaning |
|---|---|---|
| absent | `agentic_legal_research`, `run_agentic_demo`, and existing example traces | Deterministic harness trace with per-tool `output_summary.trace_kind: "deterministic_harness_step"`. |
| `externally_driven` | `begin_agentic_run` / `finalize_agentic_run` session traces | The server records and gates externally driven tool runs. Tool calls in these traces use `execution_mode: "actual_tool"`. |

Externally driven traces prove tool invocation through the MCP server. They do
not prove answer quality beyond the deterministic validation, claim-support,
coverage, and trust-gate checks represented in the trace.

## Decision Trace

`decision_trace` records the auditable decisions that connect evidence to the
final action. The public harness records citation-validation counts,
claim-support decision trace, and the trust-gate decision.

Clients should render answer content only when both conditions are true:

1. `trust_gate.safe_to_present == true`
2. `final_action == "answer"`

When `final_action != "answer"`, `answer` must be `null`.

Example traces live under `examples/agentic_runs/*.json` and are validated by tests.
