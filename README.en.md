# Taiwan Legal RAG / MCP Trust Infrastructure

Languages: [繁體中文](README.zh-TW.md) | English

This repository is a database framework and legal-data tooling reference implementation for building Taiwan-focused Legal RAG and MCP systems. Its goal is to help legal AI systems retrieve sources, classify authority, validate citations, and stop before producing confident answers when the available evidence is not sufficient.

In a Taiwan legal AI product, this framework can act as the legal data foundation behind a chatbot, research assistant, or legal operations workflow. Instead of relying on model memory, the upper-layer AI can request statutes, judgments, Constitutional Court materials, source status, and citation validation results from this data layer.

This project is not an out-of-the-box legal database and does not provide legal advice. It shows how users can connect government open data, official APIs, external semantic recall services, and local verified caches, while keeping a testable tool layer for search, citation validation, source classification, coverage checks, version timelines, appellate lineage graphs, and answer trust gates.

> [!IMPORTANT]
> This project is a technical framework and reference implementation. All bundled data is synthetic demo data for development, testing, and workflow demonstration only. This project does not provide real legal database content or legal advice.

In short, this repository does not try to include all Taiwan legal data. It demonstrates how Taiwan legal materials can be organized into a RAG foundation that is searchable, citation-aware, and controlled for risk.

## How This Can Serve Taiwan Legal RAG

In a production system, this framework can sit behind an LLM or AI agent as a legal retrieval and verification layer:

```text
User question
-> Taiwan legal database / external semantic recall / official API
-> candidate recall
-> statutes, judgments, Constitutional Court materials, legal knowledge cards
-> citation validation
-> trust gate
-> context for LLM answers or research summaries
```

Supported RAG use cases include:

- Searching for potentially relevant statutes, judgments, and legal materials with natural language questions
- Treating semantic search results as candidates, then verifying them against official sources or verified caches
- Checking whether citations in an AI answer exist, are citable, or are only candidate leads
- Reporting whether source coverage is sufficient, missing, unchecked, or low-confidence
- Blocking answers when there is no validated final citation, and asking for official review or human judgment instead

For example, if a user asks what can be done when a landlord refuses to return a deposit after a lease ends, the AI can first use this framework to retrieve potentially relevant Civil Code provisions, rental dispute judgments, and coverage status before asking the model to summarize the findings.

## How This Can Support AI-Assisted Legal Work

This framework can support lawyers, legal teams, researchers, and legal-tech products in AI-assisted workflows such as:

- Issue triage: identifying whether a query is closer to lease, tort, labor, criminal, constitutional, or other legal topics
- Statute and judgment recall: collecting possibly relevant laws, judgments, or Constitutional Court materials
- Citation safety checks: classifying a citation as official, verified cache, candidate-only, or unknown
- Research preparation: preparing issue briefs, version timelines, and appellate lineage before LLM summarization
- Risk signaling: blocking answers when sources are insufficient, external-only, or low-confidence
- Tool interfaces: exposing search, exact lookup, citation validation, and trust gates as MCP tools

The framework is designed for the pre-answer stage of legal AI: find sources, check citations, mark risks, and then let the model produce a summary, memo, or follow-up checklist. It does not replace legal professional judgment. It provides the data tool layer that forces AI systems to verify before answering.

## Legal Data Tools Provided

The current reference implementation demonstrates the following tools with synthetic data:

| Tool | Purpose |
|---|---|
| `legal_search` | Main legal retrieval entry point, combining query understanding, coverage, ranking, and trust gating |
| `validate_citation` | Checks citation status and whether a source can be used as a final citation |
| `exact_law_lookup` | Exact lookup by law name and article number |
| `exact_judgment_lookup` | Exact lookup by judgment `jid` |
| `exact_constitutional_lookup` | Exact lookup by synthetic Constitutional Court id |
| `source verification batch` | Batch source verification with de-duplication and final / candidate-only counts |
| `authority recall` | Retrieves citable sources that may be used as final citations; here, authority means source authenticity and citation eligibility |
| `stateful coverage report` | Reports coverage status, reasons, and evidence counts |
| `law version timeline` | Demonstrates a statute version timeline structure |
| `appellate lineage graph` | Demonstrates judgment appellate lineage |
| `search baseline / snapshot / soak` | Demonstrates retrieval baselines, result snapshots, and stability checks |
| `retriever cache` | Demonstrates an in-memory retriever cache without persisted cache data |

These tools map to three broad stages in a RAG workflow: `legal_search` and exact lookup find materials, `validate_citation`, `source verification batch`, and `authority recall` verify sources, and coverage reports plus trust gates decide whether the AI can safely answer.

All bundled tools currently use synthetic data. In real use, adapters can be replaced to connect Judicial Yuan open data, Ministry of Justice law data, Constitutional Court data, internal legal-team materials, or other compliant data sources.

## Why This Project Exists

The risk in legal AI is not only that an answer may be wrong. The deeper risk is that it may be wrong with confidence and without traceable authority. Common failures include:

- Treating semantically similar materials as citable sources, or treating a verifiable source as if its legal reasoning has general precedential or normative authority
- Mixing official sources, unverified datasets, and retrieval candidates
- Producing plausible-looking citations without support
- Giving confident answers when retrieval coverage is insufficient
- Promoting staging data into citable indexes before official verification
- Sending sensitive user queries to external recall systems without masking

This repository uses reproducible synthetic data to demonstrate the trust infrastructure around legal retrieval and legal-agent tools: source trust, citation verification, privacy masking, and fail-closed answer validation.

## Core Capabilities

Core components:

- MCP-style legal retrieval tools
- Query understanding: privacy masking, citation parsing, issue tags, and intent detection
- Source trust policy: official, verified cache, staging, external semantic recall, synthetic, and unknown source tiers
- Citation validation with `exists`, `not_found`, and `unverifiable` states; `unverifiable` should be treated like `not_found` by the trust gate and must not become a final citation unless a separate human review process is used
- Answer trust gate: fail closed when there is no final citation
- Stateful coverage flags: `present`, `absent`, `not_checked`, and `low_confidence`

Advanced synthetic-demo patterns:

- Source verification batch
- Authority recall for final-citation-capable citable sources only; here, authority means source authenticity and citation eligibility
- Search baseline, snapshot, and soak checks
- In-memory retriever cache
- Appellate lineage graph
- Law version timeline
- Legal knowledge layer scaffold
- Judgment ranking evaluation
- Exact law, judgment, and constitutional lookup tools

## Architecture Overview

```text
User Query
-> Privacy Masking
-> Query Normalization
-> Citation Parsing
-> Query Understanding
-> Candidate Retrieval
-> Authority Recall
-> Ranking / Coverage / Knowledge Layer
-> Source Trust Policy
-> Citation Validation
-> Trust Gate
-> Answer Wrapper
```

The core rule is simple: retrieval candidates are not citable sources. A final citation must come from an official source, or from a verified cache that can be traced back to an official URL, content hash, and verification time.

A final citation only means that the source is verifiable and citation-eligible. It does not mean the legal reasoning in that source has general precedential force or the highest normative weight. Production implementations should separately track `legal_effect_type` or `normative_weight`, such as current statute, Constitutional Court holding, Constitutional Court reasoning, concurring or dissenting opinion, Grand Chamber ruling, Supreme Court or Supreme Administrative Court judgment, lower-court case-specific judgment, and external candidate material.

## Demo Data

All bundled data is synthetic data. It exists only to test retrieval, validation, and trust-gate workflows. This repository does not distribute production legal corpora, official full-text caches, user logs, or private evaluation sets.

Synthetic data can demonstrate that the demo pipeline can retrieve an item, but it is always `demo_only` and must never be treated as current Taiwan law.

## Data Source Integration

This project does not bundle production data and does not download official data for users. In real use, users should obtain data from government open-data platforms or competent authorities according to their own research, product, and compliance needs, then implement adapters and ingestion pipelines.

When integrating government open data or official APIs, users should follow applicable government open-data licenses, agency data-use declarations, attribution duties, and usage restrictions in addition to the technical integration steps.

Each data source should keep a minimal `source_manifest`, so source and licensing information can be shown in UI, exports, or downstream documents:

```yaml
provider: "data provider"
dataset_name: "dataset name"
dataset_version: "dataset version or release date"
license_name: "license name"
license_url: "license URL"
attribution_text: "recommended attribution text"
source_url: "official source URL"
retrieved_at: "retrieval time"
terms_reviewed_at: "terms review time"
redistribution_allowed: false
```

Agency data-use declarations may differ. Implementations should not assume that all government datasets share the same reproduction, redistribution, or commercial-use conditions.

Recommended integration flow:

```text
Government open data / official API / official downloads
-> source adapter
-> staging index
-> official verification
-> source trust policy
-> promotion manifest
-> retriever / MCP tools
```

This project publishes replaceable data-flow interfaces and verification boundaries, not production tuning details. `src/tw_legal_rag_mcp/contracts.py` and `tests/integration/test_synthetic_contract_pipeline.py` use synthetic data to demonstrate how source metadata, adapter output, retrieval candidates, citation verification, trust gates, and answer validation connect. Real deployments should choose chunking strategy, ranking behavior, embedding models, index settings, and data sources according to their own scale, hardware, and compliance requirements.

The following boundaries should remain in place after integration:

- Unverified data should enter staging first, not the final citation index
- Only official sources or verified caches can become final citation candidates
- External semantic recall returns candidates only and does not provide citation authority
- Removed, withdrawn, changed, or non-public materials must have update and removal handling
- API secrets, caches, full-text data, and private query logs must not be committed to the repository

## Importing Statutes, Judgments, And Constitutional Court Materials

Demo flows only show how the tools work. In real use, different classes of legal materials should be imported through separate adapters, then governed by the same source trust policy and citation validation rules.

### Statutes

Statutory materials are well suited for exact lookup, version comparison, and foundational RAG citations. Recommended fields include:

- Law name, article number, paragraph, subparagraph, and provision text
- Promulgation date, amendment date, effective date, and version status
- Official source URL, fetch time, content hash, and source identifier
- Repeal, suspension, historical-version, or inactive-status markers
- `legal_effect_type` or `normative_weight`, such as current statute, historical statute, or repealed statute

After statutory materials enter the system, law names and article numbers should be normalized first, followed by a version timeline. When an AI answer cites a statute, it should prefer `exact_law_lookup` and `validate_citation` instead of relying only on semantic similarity.

### Judgments

Judgment materials can support case recall, issue summaries, comparison of court reasoning, and appellate lineage tracking. Recommended fields include:

- Judgment `jid`, court, year, case type, case number, judgment date, and cause of action
- Holding, reasoning, outcome, and public full-text status
- Instance level, prior and later case relationships, related judgments, and change status
- Official source URL, fetch time, content hash, and source identifier
- `legal_effect_type` or `normative_weight`, such as Grand Chamber ruling, Supreme Court judgment, Supreme Administrative Court judgment, or lower-court case-specific judgment

Judgments should enter a staging index first. They should be promoted to `official` or `verified_cache` only after official-source verification. Judgments found through external semantic recall are candidate leads only and must not become final citations by themselves.

### Constitutional Court Materials

Constitutional Court materials can support constitutional issue retrieval, holding and reasoning summaries, and review of constitutional-law context. Recommended fields include:

- Decision or interpretation identifier, year, case number, case title, and decision date
- Holding, reasoning, and public status of concurring or dissenting opinions
- Related statutes, constitutional provisions, issue tags, and linked materials
- Official source URL, fetch time, content hash, and source identifier
- `citation_role` or `opinion_role`, such as holding, majority reasoning, concurring opinion, dissenting opinion, or procedural order

Taiwan constitutional materials include both the former Grand Justice interpretations, such as `釋字`, and the newer Constitutional Court decisions, such as `憲判字` and `憲裁字`. Import-time normalization should support both identifier systems so exact lookup does not fail because of citation-format differences.

Because citation risk is high for constitutional materials, systems should clearly separate "related material was found" from "this can be used as a formal citation." In this framework, `exact_constitutional_lookup`, the source trust policy, and the trust gate should work together before the material is passed to AI as answer evidence. The trust gate should also prevent concurring or dissenting opinions from being presented as the Constitutional Court holding or majority reasoning.

### Recommended Import Order

```text
Statutes
-> build exact lookup and version timelines
-> judgments
-> build case recall and appellate lineage
-> Constitutional Court materials
-> build constitutional issue and linked-material indexes
-> unify citation validation and trust gates
```

After import, AI systems should not answer by directly reading raw source files. They should use MCP tools or retrievers that return source status, coverage status, and citation eligibility.

### Why Chunking And Index Parameters Are Not Bundled

This repository intentionally does not prescribe a fixed chunk size, overlap, embedding model, vector dimension, HNSW configuration, or SQLite FTS configuration. This is not an omission. It preserves the user's ability to tune precision, recall, storage footprint, and deployment cost for their own data and environment.

If local hardware can support high-precision semantic chunking, vector indexing, and rebuild workflows, users can rely entirely on a local indexing layer for semantic recall without installing or connecting an external semantic layer. In this framework, an external semantic layer is only one possible dual-track option: it can supplement recall when local hardware, storage, or rebuild time is constrained, but its results must still pass source verification and trust gates.

The best chunking and indexing strategy for legal materials depends on several factors:

- Data type: statutes, judgment reasoning, and Constitutional Court opinions have different document structures
- Use case: exact statute lookup, case recall, semantic exploration, and research summaries need different granularity
- Precision needs: smaller chunks may improve pinpoint retrieval but may also lose legal context
- Storage capacity: vector count, full-text index size, and cache policy directly affect storage cost
- Update frequency: frequently changing materials require careful rebuild and version-management choices
- Deployment environment: local tools, internal team services, and cloud products have different latency and cost limits

For that reason, this project defines the framework for source handling, verification, citation eligibility, and trust gates. Actual chunking, indexing, and ranking parameters should be chosen by users according to their data scale, hardware resources, precision requirements, and compliance policies.

## Optional External Semantic Recall

The `external_semantic_recall` source tier represents a common architecture: a system may use external semantic retrieval to improve recall, but it must not treat external recall results as final citations.

If users need external semantic recall, they may consider using an open-source project from the Taiwan Legal RAG / TLR ecosystem and connect it according to its license and service terms. This framework lists the source for attribution and to keep external candidate recall separate from this framework's final citation verification flow:

- [`aa0101181514/tw-legal-rag`](https://github.com/aa0101181514/tw-legal-rag): a Taiwan Legal RAG CLI that connects to the Taiwan judgment semantic retrieval service built by Legal Detective / Dr.Lawbot.
- TLR / Legal Detective semantic recall can help locate candidate judgments or related materials, but in this framework it remains classified as `external_semantic_recall`.

To avoid confusion, this repository is an independent framework. It does not bundle a TLR endpoint, proxy the TLR service, distribute TLR response caches, or guarantee the availability or stability of third-party external services. It also does not claim that external semantic recall results have legal citation authority. If users connect TLR, tw-legal-rag, or another external semantic layer, the recommended boundary is:

> [!WARNING]
> This repository has no official partnership, authorization, or endorsement relationship with TLR, Legal Detective, Dr.Lawbot, or other third-party semantic recall services. Before connecting an external service, users should review its terms of service, authorization scope, rate limits, and privacy policy. Privacy masking is best-effort risk reduction, not a guarantee of anonymization or confidentiality compliance; highly sensitive matters should default to no external transfer or use a local-only fallback.

- External semantic layers provide candidate recall only
- Final citations must still return to official sources or verified caches
- Before using external services, users should confirm lawful basis, party consent or confidentiality duties, and review log retention, data-processing agreements, and transfer restrictions
- Attribution and usage limits should be preserved
- External service responses should not be committed to a public repository

## Judicial Yuan Judgment Data Sources: Online API And Downloadable Datasets

Judicial Yuan judgment data should not be treated as a single ingestion path. Production adapters should distinguish at least two source types: the online judgment open API and dataset / file download APIs. They serve different purposes and require different sync, verification, and removal-handling strategies.

### 1. Online Judgment Open API: Incremental Sync And JID Lookup

The online judgment open API is suitable for recurring update sync, looking up a specific judgment by `jid`, and tracking updated or removed judgments. According to the official specification, the API uses Judicial Yuan open-data account credentials to obtain an access credential valid for 6 hours. That access credential is then used when requesting update lists and judgment contents.

Key points from the official specification:

- API style: RESTful
- Data format: JSON
- Auth API: `POST https://data.judicial.gov.tw/jdg/api/Auth`
- Judgment update list API: `POST https://data.judicial.gov.tw/jdg/api/JList`
- Judgment content API: `POST https://data.judicial.gov.tw/jdg/api/JDoc`
- According to the official specification, JList returns the judgment update list for the date that is 7 days before the current date; it is not a rolling 7-day aggregate
- Judgment contents are queried by `jid`
- Judgment full text may be text, PDF, or attachment links
- According to the official specification, this API is available from 00:00 to 06:00; implementations should follow the latest official specification
- If a judgment is removed or no longer public, users should remove previously obtained content

Production adapters should implement checkpoints, backfill, retry, deletion handling, and tombstone/removal manifests to avoid missed updates or retained removed judgments. JList should not be treated as the source for historical bulk ingestion; it is better suited for update tracking and freshness maintenance.

### 2. Dataset / File Download APIs: Initial Corpus Build And Batch Backfill

The Judicial Yuan open-data platform also provides dataset discovery and file download capabilities. In practice, judgment data may be available as monthly packages or dataset files. These sources are better suited for initial corpus builds, historical backfill, reproducible research snapshots, and large batch indexing.

Download-based ingestion should be implemented separately from the `Auth` / `JList` / `JDoc` online judgment API flow:

- Do not assume the same endpoints, tokens, or schedule limits
- Read dataset metadata, file format, update date, license, and download conditions before ingestion
- Store a `source_manifest` for each download, including at least dataset name, source URL, retrieved_at, license, attribution, checksum, or file size
- After importing monthly packages or downloaded files, reconcile the local corpus against online API updates and removal states
- If an official dataset is removed, withdrawn, marked non-public, or changes its licensing conditions, local data should be downgraded, removed, or no longer redistributed according to policy

This repository does not include Judicial Yuan API credentials, tokens, judgment full text, downloadable files, or caches. Production adapters should store credentials in environment variables or a secret manager, and must follow Judicial Yuan open-data platform usage rules, service-time limits, license terms, and attribution duties.

Official references:

- [Judicial Yuan Open Data Platform](https://opendata.judicial.gov.tw/)
- [Judicial Yuan Open Data Platform Development Guide](https://opendata.judicial.gov.tw/DevelopmentGuide)
- [Judicial Yuan Judgment Open API Specification](https://opendata.judicial.gov.tw/api/Newses/42/file)

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]

python examples/build_demo_index.py
python examples/basic_legal_search.py
python examples/validate_citation.py
python examples/trust_pipeline_demo.py
python examples/v02_sync_demo.py

python -m pytest
python scripts/check_no_forbidden_files.py
```

## Demo Flows

`examples/basic_legal_search.py` demonstrates synthetic lease-deposit retrieval:

```text
query
-> privacy masking
-> normalization
-> synthetic retrieval
-> coverage report
-> citation validation
-> demo-only answer wrapper
```

`examples/trust_pipeline_demo.py` demonstrates the trust pipeline:

```text
query understanding
-> classifier shadow / overlay
-> stateful coverage
-> synthetic issue brief
-> ranking evaluation
-> trust gate
```

`examples/v02_sync_demo.py` demonstrates operational trust checks:

```text
source verification batch
-> authority recall
-> baseline / snapshot / soak checks
-> retriever cache
-> appellate lineage
-> law version timeline
-> exact lookup
```

## Source Trust Policy

| Source tier | Purpose | Can be final citation |
|---|---|---|
| `official` | Official source | Yes |
| `verified_cache` | Cache verified by official URL, content hash, and verification time | Conditional |
| `staging` | External or unverified dataset | No |
| `external_semantic_recall` | TLR-like semantic recall candidate | No |
| `synthetic` | Demo and tests | No, demo-only |
| `unknown` | Unclassified source | No |

Candidate-only sources may be used for recall, ranking, or human review, but not as final legal citations.

`verified_cache` can be a final citation candidate only when it is traceable to an official URL, content hash, and verification time, and only when the source has not been withdrawn, removed, or marked non-public.

Production implementations should define a source-specific freshness policy, such as the maximum acceptable age of `verified_at`, whether official status must be rechecked before final citation, backfill strategy when an official update list is missed, and tombstone/removal manifests. Verified cache is an internal verification mechanism. It does not grant permission to redistribute official full text and does not replace official licensing, attribution, or privacy duties.

## Repository Boundaries

This repository does not include:

- Production legal datasets
- Government open-data downloads
- Judgment SQLite shards
- Law Chroma databases
- Vector indexes
- Official full-text caches
- TLR response caches
- HF verified full datasets
- Real user query logs
- Complete proprietary thesauri
- Private gold evaluation holdouts
- Credentials, tokens, private endpoints, or local sensitive paths

## Safety Checks

Before committing or publishing, run at least:

```bash
python scripts/check_no_forbidden_files.py
```

Recommended additional checks:

- GitHub secret scanning
- gitleaks
- trufflehog
- manual git history review
- license text review

## Legal Disclaimer

This project is for legal AI architecture demonstration and research only. It does not provide legal advice, does not constitute legal services, and does not guarantee the completeness, correctness, timeliness, or applicability of any legal information.

Actual legal analysis or citation should be verified against official sources and reviewed by qualified legal professionals.
