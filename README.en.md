# ALR-TW: Agentic Legal RAG / MCP Harness for Taiwan Law

Languages: [繁體中文](README.zh-TW.md) | English

ALR-TW is short for **Agentic Legal RAG / MCP Harness for Taiwan Law**. It is a public-safe reference implementation that demonstrates how a legal AI agent can plan retrieval, recall candidate materials, classify source tiers, validate citations, check coverage, and fail closed when evidence is not sufficient.

This repository is not a bundled Taiwan legal database. Its purpose is to make sure a legal RAG agent does not skip verification. It provides a deterministic execution graph, MCP tools, trust gates, trace schemas, validation reports, and synthetic scenarios so developers can inspect the engineering boundary of agentic legal RAG without exposing private or production data.

> [!IMPORTANT]
> This project contains only synthetic demo data, framework code, tests, CI, and documentation. It does not provide real legal full text, a production corpus, official full-text caches, vector databases, user records, private evaluation sets, or legal advice.

## Agentic RAG Capabilities

ALR-TW decomposes legal RAG into an auditable agent loop:

```text
User Query
-> Query Understanding
-> Source Plan
-> Retrieval
-> Source Classification
-> Citation Validation
-> Coverage Gate
-> Trust Gate
-> Final Decision
```

This is a bounded agentic workflow, not an unrestricted autonomous legal agent. The agent may use tools, produce a trace, and choose a final action, but it cannot bypass citation validation or the trust gate.

Current ALR-TW capabilities:

- query understanding: mask sensitive text, normalize the query, parse legal citations, and extract issue tags
- source planning: separate official sources, verified caches, staging data, external semantic recall, and synthetic fixtures
- candidate retrieval: retrieve synthetic statute, judgment, Constitutional Court, and external-candidate records
- exact lookup: look up law articles, judgment `jid` values, and synthetic Constitutional Court ids
- citation validation: decide whether a citation exists, is verifiable, and may become a final citation
- coverage gate: report laws, judgments, constitutional materials, and other coverage states
- trust gate: refuse output when final citations are missing, sources are unverifiable, coverage is low-confidence, or claim support is unchecked
- trace schema: emit `alr-tw.agentic_trace/v1` with steps, tool calls, evidence, coverage, trust-gate output, and final action
- validation report: convert an agent run into a Markdown review report
- MCP server: expose agentic legal RAG tools over stdio for local MCP clients

## MCP Tools

| Tool | Capability | Output focus |
|---|---|---|
| `agentic_legal_research` | Runs the synthetic agentic RAG loop | Tool trace, candidates, final citations, trust gate |
| `run_agentic_demo` | Runs a deterministic ALR-TW scenario | `answer`, `refuse`, or `human_review_required` |
| `build_validation_report` | Builds a validation report | Markdown review artifact |
| `get_trust_model` | Returns source tiers and fail-closed policy | Trust model |
| `legal_search` | Synthetic legal search demo | Candidate retrieval |
| `validate_citation` | Validates citation tier and use | Final eligibility |
| `exact_law_lookup` | Synthetic exact statute lookup | Demo-only result |
| `exact_judgment_lookup` | Synthetic exact judgment lookup | Demo-only result |
| `exact_constitutional_lookup` | Synthetic Constitutional Court lookup | Demo-only result |

All MCP tool results use the same envelope:

```json
{
  "ok": true,
  "schema_version": "alr-tw.mcp_tool_result/v1",
  "data": {},
  "error": null
}
```

## Trust Gate

The core ALR-TW rule is simple: a retrieval candidate is not a final citation.

| Source tier | Role | Final citation |
|---|---|---|
| `official` | Official or official-grounded source | Yes |
| `verified_cache` | Cache with official URL, content hash, and verified time | Conditional |
| `staging` | Ingestion or audit candidate | No |
| `external_semantic_recall` | External semantic recall candidate | No |
| `synthetic` | Demo and test fixture | No |
| `unknown` | Unknown source | No |

The trust gate fails closed when:

- there is no final citation
- a citation is rejected or unverifiable
- only candidate-only sources were found
- only synthetic demo sources were found
- a verified cache lacks official URL, hash, or verification time
- coverage is absent or low-confidence
- claim support has not been checked and human review is required

## Demo Scenarios

`examples/agentic_runs/*.json` stores deterministic traces. `examples/reports/*.md` stores matching validation reports.

| Scenario | Expected result |
|---|---|
| `pass_official_source` | Final citation exists; answer is allowed |
| `fail_candidate_only` | External recall is candidate-only; answer is refused |
| `fail_synthetic_only` | Synthetic fixture is not current law; answer is refused |
| `fail_verified_cache_incomplete` | Verified-cache metadata is incomplete; answer is refused |
| `fail_no_final_citation` | No final citation exists; answer is refused |
| `fail_low_coverage` | Coverage is low-confidence; answer is refused |
| `human_review_required_claim_support` | Source exists, but claim support was not checked; human review is required |

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]

uv run --extra dev alr-tw-demo
uv run --extra dev python examples/agentic_mcp_client_demo.py
```

MCP stdio smoke:

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"stdio-smoke","version":"0.2.0"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  | uv run --extra dev alr-tw-mcp
```

Validation:

```bash
python3 scripts/check_no_forbidden_files.py
python3 scripts/check_public_boundary.py
uv run --extra dev ruff check .
uv run --extra dev pytest
```

## Public / Private Boundary

This repository is a public reference harness. It keeps only the publish-safe engineering surface:

- source policy
- citation validator
- trust gate
- deterministic execution graph
- trace schema
- synthetic fixtures
- tests, CI, and documentation

This repository does not include:

- production legal datasets
- official full-text caches
- SQLite shards
- Chroma or vector DBs
- real verified caches
- real user query records
- private workflow data
- production ranking, chunking, or index parameters
- credentials, private endpoints, or local sensitive paths

The public repo demonstrates the boundary and contracts. Production systems may replace synthetic adapters with compliant data sources, but should preserve the same source tiers, citation validation, coverage gates, and trust gates.

## Connecting Real Data

ALR-TW intentionally does not prescribe a fixed chunk size, embedding model, vector dimension, HNSW configuration, or ranking weights. Those are deployment-specific choices that should be selected according to data scale, hardware, update frequency, licensing, precision needs, and latency budgets.

Recommended integration flow:

```text
Official data source or compliant internal source
-> Source adapter
-> Staging index
-> Official verification
-> Source trust policy
-> Citation validation
-> Retriever / MCP tools
-> Trust gate
```

External semantic recall may improve recall, but ALR-TW treats it as `external_semantic_recall` first. It is candidate-only. Final citations must come from `official` sources or qualifying `verified_cache` records.

## Specification Docs

- [docs/AGENTIC_WORKFLOW.md](docs/AGENTIC_WORKFLOW.md): agentic RAG execution graph
- [docs/AGENTIC_HARNESS_ACCEPTANCE.md](docs/AGENTIC_HARNESS_ACCEPTANCE.md): v0.2 naming and release acceptance criteria
- [docs/TRUST_MODEL.md](docs/TRUST_MODEL.md): source tiers, citation use, and fail-closed rules
- [docs/TOOL_CONTRACT.md](docs/TOOL_CONTRACT.md): MCP tool envelope and contracts
- [docs/TRACE_SCHEMA.md](docs/TRACE_SCHEMA.md): trace schema
- [docs/VALIDATION_REPORT.md](docs/VALIDATION_REPORT.md): validation report structure
- [docs/PUBLIC_PRIVATE_BOUNDARY.md](docs/PUBLIC_PRIVATE_BOUNDARY.md): public repo and private runtime boundary
- [docs/PUBLIC_PRIVATE_TRACEABILITY.md](docs/PUBLIC_PRIVATE_TRACEABILITY.md): local capability to public counterpart mapping
- [docs/ERROR_CODES.md](docs/ERROR_CODES.md): error codes
- [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md): threat model for the public reference repo
- [docs/ARCHITECTURE_CONTRACT.md](docs/ARCHITECTURE_CONTRACT.md): architecture contract to preserve when replacing adapters or retrievers

## Legal Disclaimer

This project is for legal AI architecture demonstration and engineering tests only. It does not provide legal advice, does not constitute legal services, and does not guarantee the completeness, correctness, timeliness, or applicability of any legal information.

Actual legal analysis or citation should be verified against official sources and reviewed by qualified legal professionals.
