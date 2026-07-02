# ALR-TW Trace Schema

The public trace schema version is `alr-tw.agentic_trace/v1`.

## Main Objects

- `AgenticRunTrace`: query, normalized query, steps, tool calls, decision trace, evidence, coverage, trust gate, final action, optional answer, and human review notes.
- `ToolCallTrace`: tool name, execution mode, input summary, output summary, status, and optional error code.
- `EvidenceRecord`: citation id, source id, source tier, citation use, title, snippet, official URL, and validation status.
- `TrustGateTrace`: safe flag, failure reasons, validation summary, and recommended action.

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
final action. The public harness currently records citation-validation counts
and the trust-gate decision.

Clients should render answer content only when both conditions are true:

1. `trust_gate.safe_to_present == true`
2. `final_action == "answer"`

When `final_action != "answer"`, `answer` must be `null`.

Example traces live under `examples/agentic_runs/*.json` and are validated by tests.
