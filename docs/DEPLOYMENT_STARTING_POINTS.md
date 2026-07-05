# Deployment Starting Points

This document gives generic, illustrative starting points for connecting
ALR-TW to a real deployment. These are not production settings, not private
runtime parameters, and not recommendations to copy without measurement.

The values below are public engineering magnitudes only. They do not describe
any private runtime, corpus, holdout set, or tuned production configuration.

## Retrieval Shape

Illustrative only, not production: keep exact lookup, lexical recall, semantic
recall, staging, and final citation verification as separate layers. Exact
article lookup should run before semantic recall when the query names a statute
and article. SQLite FTS5 is a practical lexical complement to a vector index.

How to decide by measurement: track exact-hit rate, candidate recall, final
citation eligibility, latency, and storage cost separately for each retrieval
layer. Promote records only after the official verification layer can reproduce
the source identity and content hash.

## Chunking

Illustrative only, not production: statute text often starts with smaller
chunks, such as a few hundred CJK characters around article-level boundaries.
Judgment text often starts with larger chunks, such as several hundred to about
one thousand CJK characters, because facts, holding, and reasoning may span
longer passages. A common first overlap range is around 10-20% of the chunk
size, enough to stabilize citation spans without duplicating the whole corpus.

How to decide by measurement: compare answer-support quality, citation-span
stability, duplicate retrieval rate, index size, and update cost. If exact
article citations become unstable, shrink statute chunks or pin article-level
records; if judgment reasoning fragments, increase judgment chunk size or use
section-aware splitting.

## Embeddings

Illustrative only, not production: choose multilingual or Chinese-capable
embedding model families only after checking license, language coverage,
latency, memory footprint, and deployment constraints. Common public starting
families include multilingual E5-style models, BGE multilingual or Chinese
models, GTE multilingual models, and sentence-transformer style Chinese models.
Typical public embedding dimensions commonly fall in the 384-1024 range, with
larger models sometimes going above that range.

How to decide by measurement: evaluate recall at fixed latency budgets, Chinese
legal terminology coverage, robustness to mixed Chinese-English tokens, and
whether statute article lookup is being handled by exact retrieval instead of
semantic recall. Keep private evaluation holdouts out of this public repo.

## Vector Index

Illustrative only, not production: HNSW parameters trade memory, build time,
recall, and query latency.

- `M` controls graph connectivity; higher values usually improve recall and
  memory use.
- `efConstruction` controls build-time search breadth; higher values usually
  improve graph quality and build cost.
- `efSearch` controls query-time breadth; higher values usually improve recall
  and latency.

SQLite FTS5 should remain available as the lexical complement, especially for
exact legal terms, article numbers, and known identifiers. Exact-article lookup
stays ahead of semantic recall for explicit article queries.

How to decide by measurement: sweep HNSW settings against recall-at-k, final
citation hit rate, p95 latency, build time, memory, and index size. Measure
lexical and semantic retrieval separately before blending them.

## Ranking

Illustrative only, not production: the shipped public starting point is the
repo's own demo formula surface:

- `src/tw_legal_rag_mcp/retrieval/rrf.py` uses RRF with `k=60`.
- `src/tw_legal_rag_mcp/retrieval/authority_ranker.py` contains a demo
  source-tier score table.
- `src/tw_legal_rag_mcp/retrieval/judgment_ranking.py` combines demo authority,
  issue-tag, and lexical weights.

These formulas exist so tests can exercise a stable public contract. Tuned
production weights are deliberately not published and are not implied by this
repo.

How to decide by measurement: compare blended ranking against exact lookup,
lexical-only, semantic-only, and authority-first baselines. Track whether the
top result is final-citation eligible, not just semantically similar.

## Staging Adapter Skeleton

Illustrative only, not production:
`src/tw_legal_rag_mcp/ingestion/staging.py` contains
`SyntheticStagingAdapter` and `stage_records`. The adapter shows the public
shape: source manifest, staged records, source tier, adapter status, and no
private tuning parameters. The unit tests exercise the minimal staging to
citation-validation path and confirm staged records remain candidate-only.

How to decide by measurement: count staged records, rejected records, promoted
records, hash mismatches, unresolved identifiers, and review backlog before
allowing any adapter output to influence final citations.

## Measurement Checklist

Illustrative only, not production:

- measure exact lookup success separately from semantic recall
- measure candidate recall before final-citation eligibility
- record content hashes for promoted official originals
- track latency and index size per retrieval layer
- keep production ranking parameters and private evaluation holdouts private
