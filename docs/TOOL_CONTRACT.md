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
| `agentic_legal_research` | Legacy synthetic agentic RAG loop | Reports final citations |
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

