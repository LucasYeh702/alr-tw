# Architecture

```text
User Query
-> Privacy Masking
-> Query Normalizer
-> Legal Citation Parser
-> Query Understanding
    -> intent
    -> issue tags
    -> privacy-masked external recall input
-> Intent Router
-> Weighted Query Expansion
-> Source Adapter
    -> Source Manifest
    -> Staging Records
-> Candidate Retrieval
    -> Law exact lookup / vector lookup
    -> Judgment FTS / JID lookup
    -> Constitutional structured lookup
    -> TLR candidate-only semantic recall
    -> Authority recall sentinel
-> RRF / Authority Ranking
-> Judgment Ranking Eval
-> Stateful Coverage Report
-> Synthetic Knowledge Layer
    -> issue brief
    -> appellate lineage graph
    -> law version timeline
-> Search Baseline / Snapshot / Soak Check
-> In-memory Retriever Cache
-> Source Trust Policy
-> Official Verification
    -> source verification batch
-> Citation Validator
-> Trust Gate
-> Answer Wrapper
```

## Trust Boundaries

- External semantic recall may provide candidate identifiers only. It must not provide final citations.
- Third-party or HF-like datasets may be used for staging, audit, evaluation, or auxiliary enrichment only. They must not provide final citations.
- Final citations must be grounded in official sources or a verified cache with traceable official metadata.
- This repository includes synthetic demo data only. It does not include production corpora, caches, credentials, logs, or real legal full text.
