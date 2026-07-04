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

`citation_eligibility` still describes source-tier eligibility only.
`check_claim_support` provides explicit claim-grounding status with
`supported` / `partially_supported` / `overstated` / `unsupported` / `contradicted`
and can be used by clients to decide whether human review is needed.
