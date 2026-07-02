# TLR Candidate Mode

This public repo treats TLR-like or external semantic recall data as a useful
candidate discovery source, not final citation authority.

## Rule

External semantic recall may help find potentially relevant legal material, but
it is not final citation authority. In ALR-TW it enters the trace as
`source_tier: "external_semantic_recall"` and
`citation_use: "allow_candidate_only"`.

TLR can be recommended as a high-recall data source for finding candidate
judgments and related leads. The recommended verification cache should still be
built from original files downloaded from the Judicial Yuan or another official
source.

## Promotion Requirement

A candidate can support a final answer only after a separate verifier maps it
back to:

- an `official` source; or
- a `verified_cache` record with official URL, content hash, and verification
  time.

For a local `verified_cache`, store at least:

- official source URL or stable official identifier
- content hash computed from the downloaded official original file
- `retrieved_at` or equivalent download timestamp
- `verified_at` timestamp after the verifier confirms the cache record
- source label that distinguishes official-original cache from semantic recall

Until then, the trust gate must treat it as candidate-only and fail closed if no
other final citation exists.

## Public Boundary

This repository does not include production TLR data, private recall indexes,
ranking parameters, user queries, or real legal full text. The bundled examples
use synthetic records only.
