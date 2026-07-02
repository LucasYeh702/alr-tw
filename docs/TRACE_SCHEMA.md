# ALR-TW Trace Schema

The public trace schema version is `alr-tw.agentic_trace/v1`.

Main objects:

- `AgenticRunTrace`: query, normalized query, steps, tool calls, evidence, coverage, trust gate, final action.
- `ToolCallTrace`: tool name, input summary, output summary, status, optional error code.
- `EvidenceRecord`: citation id, source id, source tier, citation use, title, snippet, official URL, validation status.
- `TrustGateTrace`: safe flag, failure reasons, validation summary, recommended action.

Example traces live under `examples/agentic_runs/*.json` and are validated by tests.

