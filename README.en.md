# ALR-TW: Agentic Legal RAG / MCP Harness for Taiwan Law

[繁體中文](README.zh-TW.md) | English

ALR-TW v0.12.0 is the agent-neutral public preview of the Taiwan-law research safety harness. An external agent or LLM may create and advance a research run over MCP and propose issues or authority locators, while source acquisition, research obligations, evidence promotion, answer validation, retention, and purge remain server-owned. The model is civil-law oriented: statutory text and legal time come first; ordinary judgments are classified by court and section role; Constitutional Court majority reasoning is kept separate from individual opinions.

In `hybrid_verified` mode, this project uses [TLR (Taiwan Legal RAG)](https://github.com/aa0101181514/tw-legal-rag) to recall ordinary-judgment candidates, then asks ALR-TW to verify them against Judicial Yuan official full text. The TLR provider can also return typed administrative-interpretation candidates and read long judgment text through bounded paging. No TLR result is final citation evidence by itself.

For a judgment already verified in the same research run,
`inspect_judgment_lineage` can also read TLR's database-recorded upper/lower
history candidates and verify each bounded related decision through the
configured official judgment provider.

This project is neither legal advice nor a complete Taiwan legal database.

This repository does not ship an LLM or agent implementation. Planning, tool selection, and natural-language reasoning come from the external caller; ALR-TW supplies auditable tools and deterministic gates. The demo ranking parameters are illustrative test settings, not production ranking configuration.

> v0.12.0 remains a public preview (package version `0.12.0`). A qualified professional must still verify every answer against official text, the applicable legal time, and the facts of the matter.

> This tree targets v0.12.0; publication is tracked by the matching tag and
> GitHub Release. It does not claim complete production legal reasoning.

## Agentic RAG capabilities

ALR-TW decomposes legal research into an observable, retryable, and auditable server-owned flow:

```text
User query
  -> query understanding and privacy screen
  -> law / judgment / constitutional source plan
  -> retrieval and candidate classification
  -> official-source resolution and evidence promotion
  -> time, role, coverage and claim-support checks
  -> citation validation
  -> validated | qualified | blocked
```

The v0.12.0 surface provides legacy `hlExportPDF` and
`/EXPORTFILE/ExportToPdf.aspx` compatibility, official identity verification
for five-part TLR document IDs, agent-neutral interoperability, and one unified
legal-analysis envelope with composable branches for civil substantive law,
civil procedure, substantive criminal law, criminal procedure, administrative
law, and constitutional review. The administrative branch contains separate
legality and remedy tracks.
These checks validate structure and trust references, not semantic entailment.
The v0.12.0 surface also includes a provider-neutral applicability resolver for
explicit special/general, superior/inferior, and successor/version metadata;
authority and judgment-lineage contracts for court level, procedural posture,
appeal/review edges, and bounded negative-treatment results; and public-law
contracts plus a provider SDK for administrative rules, interpretations,
appeals, legislative materials, procedure/remedy stages, and server metadata
binding. These interfaces fail closed when provider-owned relationships cannot
be confirmed and do not infer legal effects from source text.

`ready_for_draft` means workflow completion only; it is not a sufficiency claim.
The server computes `research_sufficiency` (`sufficient`, `qualified`,
`insufficient`, or `retry_required`) and `answer_mode` (`ordinary`,
`conditional`, or `refusal_only`) and exposes the server-owned finalization
contract. Synthetic fixtures are for demos and contract tests only and cannot
support a legal answer. Counter-authority remains bounded lexical candidate
discovery followed by official verification; there is no semantic opposition
classifier and no basis for global absence or consensus claims.

The current v0.12.0 contracts also provide an optional semantic
verifier sidecar, common provider conformance, a receipt-aware adapter, and a
deployer boundary validator. Sidecars remain shadow/advisory-only; provider
source/evidence references require independent server binding and snapshot
consistency; deployer-supplied corpora, models, credentials, and deployment
parameters are not bundled. These interfaces validate structure and trust, not
semantic entailment or legal-answer authorization.

### Snapshot receipts and bundled-runtime limits

In v0.12.0 the bundled `ResearchService` issues and persists a provider-neutral
snapshot receipt for each provider's exact, unexpired official/verified-cache
source and claim-supporting evidence set in the same run. Finalization reads the
server-owned set and recomputes its material digest; caller-supplied, cross-run,
expired, or mismatched receipts cannot self-certify. `ordinary` is reachable only
when the receipt set and every other gate pass. A missing receipt is at most
`conditional`, while an inconsistent set fails closed. Finalization only
authorizes entering the drafting phase (`safe_to_draft`); only
`validate_legal_answer` can authorize presentation. A receipt does not establish
global recall completeness, judgment finality, or consensus.

An external agent may plan research and draft an answer, but it cannot declare a source official, promote a candidate into evidence, or bypass final validation.

## Optional external integration examples

The deployer may choose the recall or locator data layer. The current integration
paths are:

| Project | Optional role | ALR-TW boundary |
|---|---|---|
| [TLR (Taiwan Legal RAG)](https://github.com/aa0101181514/tw-legal-rag) | Semantic candidate recall for ordinary judgments and administrative interpretations; bounded judgment-text paging | Ordinary judgments are supported through `hybrid_verified`; administrative materials require a deployer-supplied official public-law verifier. Every TLR result remains candidate-only |
| `mcp-taiwan-legal-db` or another compatible legal-data service | External candidate or locator source | The frontend or deployer calls it and submits selected locators through a `client_assisted` research plan; evidence exists only after ALR-TW official verification |

If a frontend has already called TLR or another data service, that run should
submit the selected locators through a `client_assisted` research plan so
ALR-TW does not repeat the same recall. External results remain candidates until
official identity, content, and source/evidence binding have been verified.

Deployments may also set `ALR_TW_LOCAL_PORTAL_ROOT` to use an existing compatible
read-only local judgment provider. Candidate and verified-cache requirements are
documented in [Official Providers](docs/OFFICIAL_PROVIDERS.md).

## Safety boundary

```text
External agent asks and drafts
  -> server-owned research obligations
  -> official providers + optional TLR candidate recall
  -> server-owned source/evidence (optional provider snapshot receipt)
  -> claim, role, time, privacy, and citation validation
  -> validated | qualified | blocked
```

- A caller cannot make content authoritative by declaring `source_tier=official`.
- TLR always produces `external_semantic_recall` candidates, never final evidence.
- Final evidence must be fetched and fixed by an ALR-TW official provider, or verified by a governed resolver and matching hash.
- Party arguments, case facts, concurrences, and dissents cannot be presented as the court's majority reasoning.
- Unsupported historical-law timing, expired evidence, role errors, and unsupported claims fail closed.
- A `blocked` result never returns the draft answer body.

## Data modes

| Mode | Behavior |
|---|---|
| `synthetic` | Default; offline demos, tests, and CI |
| `official_only` | Connect only to official law, judgment, and Constitutional Court sources |
| `hybrid_verified` | After a local privacy gate, send a safe query to TLR for recall, then verify candidates against official sources |

In `hybrid_verified`, query text that passes the privacy gate is transmitted to TLR. Do not send personal secrets, unpublished case facts, private contracts, litigation strategy, evidentiary weaknesses, or negotiation limits. See [TLR Provider](docs/TLR_PROVIDER.md) and [Data Policy](DATA_POLICY.md).

### Quick mode

For judgment retrieval, use `/quick <question>`, `快速模式：<question>`, or the
structured `constraints.research_depth=quick`. With `execute_legal_research`, the
server performs privacy screening, candidate recall, at most five canonical-JID
or formal-citation checks against official text, and evidence sufficiency in one
MCP call. In `hybrid_verified`, quick mode queries TLR or another compatible
candidate provider first and falls back to Judicial Yuan keyword search only
when that provider fails or yields no usable candidate.

Quick mode reduces breadth only: it omits counter-authority, lineage, and
unrequested statute expansion by default, but never skips official verification
or final `validate_legal_answer`. Similar-case quick research always discloses
its bounded top-K scope and remains `qualified` / `conditional`, even when all
selected candidates verify; zero verified sources remains `refusal_only`.

For an incomplete or blocked run, read
`get_legal_research_state.research_brief`. It exposes verified-source locators,
obligation progress, blockers, and safe next actions without a draft conclusion;
it always sets `answer_authorized=false` and `safe_to_present=false`.

## Install and configure

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[all]'

alr-tw doctor
```

Live official mode must be selected explicitly:

```bash
export ALR_TW_DATA_MODE=official_only
export ALR_TW_RETENTION=24h
alr-tw doctor --live
```

Official HTTPS providers use the operating-system certificate store through
`truststore`. `doctor --live` probes the MOJ, Constitutional Court, and Judicial
Yuan providers and reports certificate deployment failures explicitly.

Ordinary-judgment lookup does not require a Judicial Yuan API token. In a live mode, search terms and filters are sent directly to `judgment.judicial.gov.tw`; do not use confidential or unpublished case facts as search terms.

Secrets are redacted from `doctor` output and must not be committed, traced, or persisted in SQLite.

## v0.12.0 MCP tools

| Tool | Purpose |
|---|---|
| `get_legal_research_capabilities` | Report active modes, supported profiles, and fixed trust ownership |
| `research_legal_question` | Create a server-owned research run without drafting an answer |
| `execute_legal_research` | Create a run and execute bounded server-owned obligations in one call, returning elapsed time and a draft-stage evidence bundle |
| `submit_legal_research_plan` | Register an untrusted client-assisted issue and locator plan |
| `continue_legal_research` | Execute exactly one next obligation using an idempotent `operation_id` |
| `get_legal_research_state` | Read run state and its non-answer `research_brief` without network activity or TTL extension |
| `get_legal_research_finalization` | Return server-owned research sufficiency, Coverage v2, snapshot receipts, and answer posture |
| `lookup_legal_source` | Exact lookup for a law article, Constitutional identifier, JID, or formal judgment citation |
| `inspect_judgment_lineage` | Inspect TLR-recorded upper/lower history for a same-run verified six-part JID and officially verify up to 1–20 related decisions |
| `lookup_legislative_history` | Explicitly query bounded, candidate-only Legislative Yuan locators in a live mode |
| `validate_legal_analysis` | Validate six composable branches, civil element-level burdens, server-owned references, and legal context |
| `validate_legal_answer` | Validate a draft only against evidence owned by that run |
| `purge_research_storage` | Synchronously purge one run or all managed storage |

Legacy synthetic and trace tools remain temporarily available for compatibility. New integrations should use the server-owned research flow.
The bundled managed `ResearchService` does not persist server-owned fact
records and reports `managed_fact_state_store_available=false`. Unless a
deployment integrates its own fact-state provider, analysis proposals should
bind eligible evidence IDs; caller-supplied fact status never establishes
trust.

Supported MCP protocol versions are `2025-11-25`, `2025-06-18`, `2025-03-26`, and `2024-11-05`. Unsupported versions are rejected during initialization.

Every tool result uses a fixed envelope:

```json
{
  "ok": true,
  "schema_version": "alr-tw.mcp_tool_result/v1",
  "data": {},
  "error": null
}
```

`request_id` and `client_id` are correlation metadata only. State-changing operations use `operation_id` for idempotency. Unknown fields, unsupported protocol versions, caller-supplied trust decisions, and invalid purge requests are rejected.

## Official providers

- Statutes: official Ministry of Justice structured data, with official-page consistency checks.
- Ordinary judgments: parse the official search pages to resolve a JID, then download and parse full text directly from the official `data.aspx` page.
- Constitutional materials: judgments, substantive rulings, legacy interpretations, and available individual opinions.

The project does not promise complete historical statute versions, exhaustive
ordinary-judgment recall, every procedural ruling, complete case-history graphs,
or full attachment/OCR coverage. `inspect_judgment_lineage` is limited to TLR's
database-recorded relations and the official-verification budget. No upper
record does not establish finality, and disposition classification does not
semantically compare the courts' opinions. See [Official Providers](docs/OFFICIAL_PROVIDERS.md)
and [TLR Provider](docs/TLR_PROVIDER.md).

## Final decisions

- `validated`: source, role, time, and claim support passed.
- `qualified`: verified evidence supports the draft, but a disclosed recall-coverage limitation remains.
- `blocked`: the draft must not be shown; only blockers are returned.

Finding a source does not validate a claim. A draft must still pass `validate_legal_answer`.

## Claim grounding and trust gate

ALR-TW evaluates “a source was found,” “the source is authoritative,” and “the source supports this claim” as separate questions:

| Source tier | Purpose | Direct final-citation eligibility |
|---|---|---|
| `official` | Content fetched and fixed from an official source | Yes, subject to time, role, and claim-support checks |
| `verified_cache` | Cache whose identifier and content hash were checked by a governed resolver | Conditional |
| `staging` | Imported, cleaned, or audited candidate material | No |
| `external_semantic_recall` | TLR or another external semantic-recall result | No |
| `synthetic` | Demo or test fixture | No |
| `unknown` | Unresolved identity or provenance | No |

The trust gate fails closed when there is no final citation, official resolution fails, legal time is unknown, a section role is misstated, a claim exceeds its evidence, only candidate sources are available, or the draft makes an unqualified conclusion despite incomplete authority coverage.

## Retention and purge

Managed SQLite storage defaults to `~/.cache/alr-tw`, with a `24h` default and `7d` maximum retention. A run may request `retention: "ephemeral"`; it is purged synchronously after final validation.

```bash
alr-tw purge --run RUN_ID --confirm
alr-tw purge --all --confirm
```

Local purge cannot retract a query already transmitted to an external provider or erase that provider's logs. See [Storage and Purge](docs/STORAGE_AND_PURGE.md).

## MCP client quick configuration

Start in the safe `synthetic` mode to verify that the client can launch the MCP server:

```json
{
  "mcpServers": {
    "alr-tw": {
      "command": "alr-tw-mcp",
      "env": {
        "ALR_TW_DATA_MODE": "synthetic"
      }
    }
  }
}
```

The client should create a run, follow `next_operation`, and draft only from
promoted server-owned evidence before calling `validate_legal_answer`. Only a
final-answer `validated` result, or a `qualified` result allowed by disclosure
rules, may be rendered. `lookup_legal_source` does not replace answer-level
validation.

If a forcibly terminated local stdio process leaves the host showing a stale
connected state, disable and re-enable the MCP configuration or restart the
host. If it still reports `Not connected`, remove and re-add the same
configuration. Stale host UI state is not runtime health evidence.

## Development verification

```bash
uv run ruff check .
uv run mypy src
uv run pytest -q
python3 scripts/check_no_forbidden_files.py
python3 scripts/check_public_boundary.py
uv build
```

## Public / private boundary

The public repository contains provider and resolver interfaces, one unified
multi-branch analysis validator, source tiers, evidence-promotion and citation
policies, MCP schemas, privacy and retention controls, purge and fail-closed
rules, synthetic fixtures, tests, CI, and documentation.

It does not contain a production corpus, permanent official full-text cache,
real user records, private evaluations, vector shards, credentials, private
endpoints, private manifests, operator state, gold labels, internal ranking or
chunking parameters, or unredacted case material. Synthetic data is for demos
and tests and must not be presented as current law.

## Connecting real data

```text
Choose data mode
  -> configure retention and secrets outside the repo
  -> run alr-tw doctor --live
  -> retrieve candidate sources
  -> resolve official identifier and content
  -> create server-owned evidence (bind a receipt only when the adapter issues one)
  -> validate draft claims and citations
  -> present or fail closed
```

- Statutes: the Ministry of Justice official source is the authority layer. Prefer exact lookup for an explicit law and article; block or require human review when a historical version cannot be established.
- Ordinary judgments: ALR-TW does not use a Judicial Yuan API. It parses the public judgment search page to obtain a JID, then downloads the official detail page. Search failure, site blocking, parse failure, and confirmed absence remain distinct states.
- TLR: [TLR](https://github.com/aa0101181514/tw-legal-rag) improves ordinary-judgment and administrative-interpretation candidate recall. Judgment hits must be resolved against the Judicial Yuan official source; administrative hits require an ALR-TW-governed official public-law adapter. Hit excerpts, paged TLR text, and provider status metadata never become evidence.
- Constitutional materials: holdings, majority reasons, concurrences, and dissents retain separate roles. An individual opinion cannot be presented as majority reasoning.

Applicability, authority/lineage, and public-law contracts are provider-neutral
structural interfaces. Deployments supply their own providers; candidate records
remain separate from server-owned evidence, and no contract performs semantic
entailment or semantic opposition classification.

## Documentation

- [Architecture](ARCHITECTURE.md)
- [Data Policy](DATA_POLICY.md)
- [Security](SECURITY.md)
- [Trust Model](docs/TRUST_MODEL.md)
- [Tool Contract](docs/TOOL_CONTRACT.md)
- [Agent-neutral interoperability contract](docs/INTEROPERABILITY_CONTRACT.md)
- [TLR Provider](docs/TLR_PROVIDER.md)
- [Official Providers](docs/OFFICIAL_PROVIDERS.md)
- [Storage and Purge](docs/STORAGE_AND_PURGE.md)
- [Agent Client Guide](docs/AGENT_CLIENT_GUIDE.md)
- [Error Codes](docs/ERROR_CODES.md)
- [Threat Model](docs/THREAT_MODEL.md)
- [Release Notes](docs/RELEASE_NOTES.md)
- [Agentic Harness Acceptance](docs/AGENTIC_HARNESS_ACCEPTANCE.md)
- [Changelog](CHANGELOG.md)

## Legal notice

ALR-TW is provided for software architecture, research, and testing. It is not legal advice, a legal service, or a case-specific conclusion, and it does not guarantee completeness, accuracy, currency, or applicability.
