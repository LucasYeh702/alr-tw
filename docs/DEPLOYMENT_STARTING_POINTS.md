# Deployment Starting Points

This document gives illustrative starting points for connecting ALR-TW to a
real deployment. These are not production settings, not private runtime
parameters, and not recommendations to copy without measurement.

## Retrieval Shape

Illustrative only, not production: start by separating exact lookup, lexical
recall, semantic recall, and final citation verification. Measure precision,
recall, latency, and storage cost on the operator's own lawful corpus before
choosing any final settings.

## Chunking

Illustrative only, not production: judgment and statute records often need
different chunking strategies. Operators should measure answer support quality,
citation span stability, and update cost rather than copying a fixed chunk size
or overlap from this repo.

## Embeddings And Indexes

Illustrative only, not production: choose embedding models, vector dimensions,
HNSW or other vector-index parameters, and SQLite FTS settings according to the
deployment corpus, hardware, update cadence, and latency budget. Keep exact
article lookup ahead of semantic recall for explicit article queries.

## Demo Ranking Formula

Illustrative only, not production: this repo includes demo ranking formula
helpers such as RRF and source-tier scores so tests can exercise a stable public
contract. They are not tuned production ranking parameters and do not describe a
private runtime. Operators should measure ranking quality with their own
evaluation set and keep private evaluation holdouts out of the public repo.

## Staging Adapter Skeleton

Illustrative only, not production: `src/tw_legal_rag_mcp/ingestion/staging.py`
contains a small `SyntheticStagingAdapter` and `stage_records` helper. The
adapter shows the expected public shape: source manifest, staged records,
source tier, and adapter status. A real deployment should replace the synthetic
records with lawful source adapters and should promote records only after
official verification.

## Measurement Checklist

Illustrative only, not production:

- measure exact lookup success separately from semantic recall
- measure candidate recall before final-citation eligibility
- record content hashes for promoted official originals
- track latency and index size per retrieval layer
- keep production ranking parameters and private evaluation holdouts private
