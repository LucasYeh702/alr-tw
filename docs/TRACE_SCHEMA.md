# ALR-TW Trace Schema

The public trace schema version is `alr-tw.agentic_trace/v1`.

This repository does not ship an LLM or agent implementation. Traces emitted by
`agentic_legal_research` and `run_agentic_demo` are deterministic synthetic
harness outputs that an external MCP client or LLM runtime can inspect. The
files under `examples/agentic_runs/*.json` are not recordings of agent
reasoning or live external tool execution.

## Main Objects

- `AgenticRunTrace`: query, normalized query, steps, tool calls, decision trace, evidence, coverage, trust gate, claim grounding outputs (`answer_claims`, `claim_support`, `semantic_grounding_summary`, `semantic_failure_reasons`), final action, optional answer, and human review notes.
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
| `actual_tool` | Reserved for implementations that record a live external tool call. |

The public examples use `harness_recorded` and
`output_summary.trace_kind: "deterministic_harness_step"`. They are not live
external tool execution logs.

## Decision Trace

`decision_trace` records the auditable decisions that connect evidence to the
final action. The public harness records citation-validation counts,
claim-support decision trace, and the trust-gate decision.

Clients should render answer content only when both conditions are true:

1. `trust_gate.safe_to_present == true`
2. `final_action == "answer"`

When `final_action != "answer"`, `answer` must be `null`.

Example traces live under `examples/agentic_runs/*.json` and are validated by tests.
