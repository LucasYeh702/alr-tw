# ALR-TW: Agentic Legal RAG / MCP Harness for Taiwan Law

Languages: [繁體中文](README.zh-TW.md) | English

ALR-TW is short for **Agentic Legal RAG / MCP Harness for Taiwan Law**. It is an AI-agent-driven agentic RAG harness: an agent may call tools, produce traces, and make trust-gate decisions, but it must operate inside the harness's deterministic graph, citation validation, and trust gate. It is not an autonomous legal agent that practices law or independently completes legal judgment.

This repository is a public-safe reference implementation that demonstrates how a legal AI agent can plan retrieval, recall candidate materials, classify source tiers, validate citations, check coverage, and fail closed when evidence is not sufficient.

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

This is an AI-agent-driven bounded agentic workflow, not an unrestricted autonomous legal agent. The agent may use tools, produce a trace, and choose a final action, but it cannot bypass citation validation or the trust gate.

Current ALR-TW capabilities:

- query understanding: apply demo heuristic sensitive-text masking, normalize the query, parse legal citations, and extract issue tags
- source planning: separate official sources, verified caches, staging data, external semantic recall, and synthetic fixtures
- candidate retrieval: retrieve synthetic statute, judgment, Constitutional Court, and external-candidate records
- exact lookup: look up law articles, judgment `jid` values, and synthetic Constitutional Court ids
- citation validation: decide whether a citation exists, is verifiable, and may become a final citation
- coverage gate: report laws, judgments, constitutional materials, and other coverage states
- trust gate: refuse output when final citations are missing, sources are unverifiable, coverage is low-confidence, or claim support is unchecked
- claim grounding: v0.3 adds answer claim splitting and semantic alignment checks so each claim is traceable to evidence
- trace schema: emit `alr-tw.agentic_trace/v1` with steps, tool calls, decision trace, evidence, coverage, trust-gate output, and final action
- validation report: convert an agent run into a Markdown review report
- MCP server: expose agentic legal RAG tools over stdio for local MCP clients

## MCP Tools

| Tool | Capability | Output focus |
|---|---|---|
| `agentic_legal_research` | Runs the synthetic agentic RAG loop | Canonical trace, candidates, final citations, trust gate |
| `run_agentic_demo` | Runs a deterministic ALR-TW scenario | `answer`, `refuse`, or `human_review_required` |
| `build_validation_report` | Builds a validation report | Markdown review artifact |
| `get_trust_model` | Returns source tiers and fail-closed policy | Trust model |
| `get_claim_grounding_policy` | Returns v0.3 claim grounding contract | Claim policy |
| `extract_answer_claims` | Splits answer text into traceable claims | Answer claims |
| `check_claim_support` | Checks claim support against evidence segments | Claim support status |
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

Example traces mark `tool_calls` with `execution_mode: "harness_recorded"`. That means they are deterministic harness records, not live external tool execution logs.

## Claim Grounding (v0.3)

ALR-TW v0.3 adds a semantic safety layer without changing the source-first safety model:

- `extract_answer_claims`: split answer text into trackable claim units (`alr-tw.answer-claim/v1`)
- `check_claim_support`: evaluate each claim against evidence segments (`alr-tw.claim-support/v1`)
- `get_claim_grounding_policy`: expose public claim-policy, status labels, and risk flags (`alr-tw.claim-grounding-policy/v1`)

This remains a public-safe harness: it publishes schema, synthetic fixtures, MCP contracts, and tests. It does not publish the full private production semantic inference stack.

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
- claim support status is not safe-to-present (e.g., `partially_supported`, `overstated`, `unsupported`, `contradicted`, `role_error`, `unchecked`, `needs_review`)
- coverage is absent or low-confidence
- claim support has not been checked; the run can only require human review and must not return a directly presentable answer body

## Demo Scenarios

`examples/agentic_runs/*.json` stores deterministic traces. `examples/reports/*.md` stores matching validation reports.

| Scenario | Expected result |
|---|---|
| `pass_official_source` | Final citation exists and claim support is accepted; answer is allowed |
| `pass_claim_supported` | Final citation exists and claim support status is supported; answer is allowed |
| `fail_candidate_only` | External recall is candidate-only; answer is refused |
| `fail_synthetic_only` | Synthetic fixture is not current law; answer is refused |
| `fail_verified_cache_incomplete` | Verified-cache metadata is incomplete; answer is refused |
| `fail_no_final_citation` | No final citation exists; answer is refused |
| `fail_low_coverage` | Coverage is low-confidence; answer is refused |
| `fail_party_argument_as_court_view` | Party-argument segment is misread as court view; refused/human review |
| `fail_overstated_case_specific_rule` | Case-specific finding was over-generalized; human review/refusal |
| `fail_unsupported_paraphrase` | Claim paraphrase is unsupported by evidence; answer is refused |
| `human_review_required_claim_support` | Source exists, but claim support was not checked; human review is required |
| `human_review_claim_unchecked` | Alias scenario for explicit unchecked claim support path |

When `final_action != "answer"`, the trace `answer` must be `null`. A client may render answer content only when `trust_gate.safe_to_present == true` and `final_action == "answer"`.

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
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"stdio-smoke","version":"0.3.0"}}}' \
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

In practice, TLR or another semantic index can be a useful high-recall data source for candidate judgments and related leads. Final citations should not directly cite TLR recall results; the recommended path is still to download original files from the Judicial Yuan or another official source and build a local `verified_cache`.

A local `verified_cache` should at least keep the official URL or stable official identifier, content hash, download time, and verified time. Only `official` sources or metadata-complete `verified_cache` records can pass final-citation eligibility.

Minimum data recommendation:

- search / semantic recall: connect TLR or another semantic index first as the high-recall candidate source.
- local verification cache: download Judicial Yuan monthly judgment originals and convert them into a local `verified_cache` for jid, official-source, hash, and verified-time checks.
- law corpus: statutes are not part of the Judicial Yuan judgment monthly archives. Connect a separate official law source such as MOJ or another official legal-data provider. Based on measured official-law JSON scale, raw statute data is within a few hundred MB; a separate statute vector index is usually in the 1-2GB range. Exact article lookup should take priority for explicit article queries, with semantic recall as a supplement.
- constitutional materials: Judicial Yuan public data can also include Judicial Yuan Interpretations and Constitutional Court materials as a local verification source for constitutional materials. Based on measured scale, raw zip files are roughly 260MB and raw JSON is roughly 25MB; with attachments and OCR text retained, the total remains within about 1GB.
- Judicial Yuan scope: in this section, Judicial Yuan data mainly means public monthly judgment archives, plus separately ingestible Judicial Yuan Interpretations and Constitutional Court public materials. It does not include statute full text, administrative interpretations, MOJ law data, unpublished judgments, or private case data. Actual downloadable periods, fields, and redaction behavior depend on the Judicial Yuan open-data source.
- capacity planning: for a full historical judgment corpus, official compressed monthly archives are roughly 50GB and a local gzip verification cache is roughly 30GB. A separate judgment full-text, FTS, or vector index can grow into the hundreds of GB. A minimal deployment can reserve about 100GB for official judgment originals plus local verification cache; raw statute data and constitutional materials usually each fit within 1GB, while indexing capacity should be planned separately.

## Specification Docs

- [docs/AGENTIC_WORKFLOW.md](docs/AGENTIC_WORKFLOW.md): agentic RAG execution graph
- [docs/AGENTIC_HARNESS_ACCEPTANCE.md](docs/AGENTIC_HARNESS_ACCEPTANCE.md): v0.3.0 naming and release acceptance criteria
- [docs/TRUST_MODEL.md](docs/TRUST_MODEL.md): source tiers, citation use, and fail-closed rules
- [docs/TLR_CANDIDATE_MODE.md](docs/TLR_CANDIDATE_MODE.md): external semantic recall / TLR-like candidate-only mode
- [docs/TOOL_CONTRACT.md](docs/TOOL_CONTRACT.md): MCP tool envelope and contracts
- [docs/TRACE_SCHEMA.md](docs/TRACE_SCHEMA.md): trace schema
- [docs/VALIDATION_REPORT.md](docs/VALIDATION_REPORT.md): validation report structure
- [docs/RELEASE_NOTES.md](docs/RELEASE_NOTES.md): release notes
- [docs/PUBLIC_PRIVATE_BOUNDARY.md](docs/PUBLIC_PRIVATE_BOUNDARY.md): public repo and private runtime boundary
- [docs/PUBLIC_PRIVATE_TRACEABILITY.md](docs/PUBLIC_PRIVATE_TRACEABILITY.md): local capability to public counterpart mapping
- [docs/ERROR_CODES.md](docs/ERROR_CODES.md): error codes
- [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md): threat model for the public reference repo
- [docs/ARCHITECTURE_CONTRACT.md](docs/ARCHITECTURE_CONTRACT.md): architecture contract to preserve when replacing adapters or retrievers

## Legal Disclaimer

This project is for legal AI architecture demonstration and engineering tests only. It does not provide legal advice, does not constitute legal services, and does not guarantee the completeness, correctness, timeliness, or applicability of any legal information.

Actual legal analysis or citation should be verified against official sources and reviewed by qualified legal professionals.
