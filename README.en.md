# ALR-TW: Agentic Legal RAG / MCP Harness for Taiwan Law

[繁體中文](README.zh-TW.md) | English

ALR-TW v0.6.0 is a public-preview safety harness for Taiwan-law research. An external agent or LLM may create and advance a research run over MCP, while source acquisition, research obligations, evidence promotion, answer validation, retention, and purge remain server-owned. The model is civil-law oriented: statutory text and legal time come first; ordinary judgments are classified by court and section role; Constitutional Court majority reasoning is kept separate from individual opinions.

In `hybrid_verified` mode, this project uses [TLR (Taiwan Legal RAG)](https://github.com/aa0101181514/tw-legal-rag) to recall ordinary-judgment candidates, then asks ALR-TW to verify them against Judicial Yuan official full text. TLR results are not final citation evidence by themselves.

This project is neither legal advice nor a complete Taiwan legal database.

This repository does not ship an LLM or agent implementation. Planning, tool selection, and natural-language reasoning come from the external caller; ALR-TW supplies auditable tools and deterministic gates. The demo ranking parameters are illustrative test settings, not production ranking configuration.

## Safety boundary

```text
External agent asks and drafts
  -> server-owned research obligations
  -> official providers + optional TLR candidate recall
  -> server-owned source and evidence snapshots
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

Ordinary-judgment lookup does not require a Judicial Yuan API token. In a live mode, search terms and filters are sent directly to `judgment.judicial.gov.tw`; do not use confidential or unpublished case facts as search terms.

Secrets are redacted from `doctor` output and must not be committed, traced, or persisted in SQLite.

## v0.6 MCP tools

| Tool | Purpose |
|---|---|
| `research_legal_question` | Create a server-owned research run without drafting an answer |
| `continue_legal_research` | Execute exactly one next obligation using an idempotent `operation_id` |
| `get_legal_research_state` | Read run state without network activity or TTL extension |
| `lookup_legal_source` | Exact lookup for a law article, Constitutional identifier, JID, or formal judgment citation |
| `validate_legal_answer` | Validate a draft only against evidence owned by that run |
| `purge_research_storage` | Synchronously purge one run or all managed storage |

Legacy synthetic and trace tools remain temporarily available for compatibility. New integrations should use the server-owned research flow.

Supported MCP protocol versions are `2025-11-25`, `2025-06-18`, `2025-03-26`, and `2024-11-05`. Unsupported versions are rejected during initialization.

## Official providers

- Statutes: official Ministry of Justice structured data, with official-page consistency checks.
- Ordinary judgments: parse the official search pages to resolve a JID, then download and parse full text directly from the official `data.aspx` page.
- Constitutional materials: judgments, substantive rulings, legacy interpretations, and available individual opinions.

The first release does not promise complete historical statute versions, exhaustive ordinary-judgment recall, every procedural ruling, complete case-history graphs, or full attachment/OCR coverage. See [Official Providers](docs/OFFICIAL_PROVIDERS.md).

## Final decisions

- `validated`: source, role, time, and claim support passed.
- `qualified`: verified evidence supports the draft, but a disclosed recall-coverage limitation remains.
- `blocked`: the draft must not be shown; only blockers are returned.

Finding a source does not validate a claim. A draft must still pass `validate_legal_answer`.

## Retention and purge

Managed SQLite storage defaults to `~/.cache/alr-tw`, with a `24h` default and `7d` maximum retention. A run may request `retention: "ephemeral"`; it is purged synchronously after final validation.

```bash
alr-tw purge --run RUN_ID --confirm
alr-tw purge --all --confirm
```

Local purge cannot retract a query already transmitted to an external provider or erase that provider's logs. See [Storage and Purge](docs/STORAGE_AND_PURGE.md).

## Development verification

```bash
uv run ruff check .
uv run mypy src
uv run pytest -q
python3 scripts/check_no_forbidden_files.py
python3 scripts/check_public_boundary.py
uv build
```

## Documentation

- [Architecture](ARCHITECTURE.md)
- [Data Policy](DATA_POLICY.md)
- [Security](SECURITY.md)
- [Trust Model](docs/TRUST_MODEL.md)
- [Tool Contract](docs/TOOL_CONTRACT.md)
- [TLR Provider](docs/TLR_PROVIDER.md)
- [Official Providers](docs/OFFICIAL_PROVIDERS.md)
- [Storage and Purge](docs/STORAGE_AND_PURGE.md)
- [v0.6.0 Release Audit](docs/V060_RELEASE_AUDIT.md)
- [Changelog](CHANGELOG.md)

## Legal notice

ALR-TW is provided for software architecture, research, and testing. It is not legal advice, a legal service, or a case-specific conclusion, and it does not guarantee completeness, accuracy, currency, or applicability.
