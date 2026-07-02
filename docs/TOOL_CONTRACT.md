# ALR-TW Tool Contract

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

## Citation Validation Metadata

`validate_citation` accepts:

- `citation_id`
- `source_tier`
- optional `official_url`
- optional `official_hash`
- optional `verified_at`
- optional `source_label`

`verified_cache` may become final-eligible only when the official URL, hash, and
verification time are all present. Otherwise it fails closed.

The field `citation_eligibility` describes source-tier eligibility only. The
field `support` remains `not_checked`; this public harness does not claim
claim-level entailment.
