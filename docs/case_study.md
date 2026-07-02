# Case Study: ALR-TW Agentic Legal RAG Harness

## Problem

Legal AI systems often fail by producing confident but ungrounded citations, mixing unofficial sources with official ones, or treating semantic similarity as legal authority.

## Design

ALR-TW demonstrates a Taiwan-focused Legal Agentic RAG / MCP architecture with:

- official-source grounding
- citation validation
- source trust policy
- external semantic recall as candidate-only
- staging data promotion gates
- coverage flags with uncertainty states
- privacy masking
- stateful coverage with reasons and evidence counts
- classifier shadow annotation and overlay review boundaries
- synthetic legal knowledge layer scaffolding
- judgment ranking evaluation
- trust gate before answer presentation
- source verification batch handling
- authority recall sentinel
- baseline / snapshot / soak checks
- retriever cache reuse without persistence
- appellate lineage and law version synthetic views
- exact lookup tool surface

## Key trade-offs

- No production legal data is included in this repository.
- TLR-like semantic recall is treated as candidate-only.
- HF-like datasets are treated as staging / audit / eval data only.
- Final citations must be official-grounded.
- Synthetic data is used for reproducible demo.
- Production adapters, caches, credentials, logs, and real legal full text are not included in this repository.

## Why it matters

The goal is not to build a chatbot that sounds legal. The goal is to build legal AI infrastructure that knows when it is allowed to cite, when it must verify, and when it must refuse unsupported authority.

## Future extensions

- time-law versioning
- citation graph
- administrative letter ingestion
- enterprise RBAC / audit log
- Taiwan-specific legal reranker
