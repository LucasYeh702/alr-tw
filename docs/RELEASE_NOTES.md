# Release Notes

## v0.2.1 Hardening Patch

This patch tightens the public Agentic Legal RAG / MCP Harness claim.

- Adds explicit `execution_mode` to trace tool calls.
- Adds `decision_trace` to canonical agentic traces.
- Ensures non-answer traces keep `answer` as `null`.
- Makes `agentic_legal_research` return the canonical
  `alr-tw.agentic_trace/v1` shape.
- Adds MCP support for complete `verified_cache` citation metadata.
- Splits citation eligibility from claim support; public support remains
  `not_checked`.
- Improves demo sensitive-text masking for unsegmented Chinese names and Taiwan
  ID patterns.
- Expands MCP coverage for trust model and exact lookup tools.
- Regenerates public synthetic examples and validation reports.

No production corpus, real legal full text, cache, index, user log, credential,
or private retrieval parameter is included.
