# TLR Candidate Mode

Languages: English | [繁體中文](TLR_CANDIDATE_MODE.zh-TW.md)

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

## Official Access Prerequisite

This repository does not provide Judicial Yuan API credentials, access approval,
or downloaded official data. Operators must obtain official Judicial Yuan access
or otherwise lawfully download the public original files themselves before
building a local verification cache.

## Why Download Official Data If TLR Is Connected?

TLR reduces discovery cost; it does not replace the local authority layer. In
this branch, TLR is used to find candidate judgments quickly, but the final
citation gate still depends on official or locally verified records.

Downloading the Judicial Yuan originals is still required when operators need:

- final citation eligibility instead of candidate-only recall
- a local content hash for the exact original record used as evidence
- reproducible results tied to a known local data snapshot
- local operation for sensitive follow-up verification and review
- resilience when an external recall service is unavailable or changes ranking

Without the local official-data cache, a TLR hit remains
`external_semantic_recall` and cannot satisfy final-citation requirements.

## Promotion Requirement

A candidate can support a final answer only after a separate verifier maps it
back to:

- an `official` source; or
- a `verified_cache` record with official URL, content hash, and verification
  time.

For a TLR-style judgment candidate, a minimal raw-backed promotion flow is:

1. Treat the TLR result as `external_semantic_recall`.
2. Extract the stable judgment identifier, such as a JID.
3. Resolve that identifier against original Judicial Yuan monthly files that the
   operator downloaded through their own official access.
4. Compute a content hash from the matched original record, for example the raw
   JSONL line or another documented canonical source representation.
5. Promote only the locally matched record as `verified_cache`; keep unmatched
   TLR candidates as candidate-only.

In ALR-TW code this identifier-backed path is an opt-in capability
(`ALR_TW_IDENTIFIER_BACKED_VERIFIED_CACHE`, default off), limited to
judgment-type records, and enforced by a resolver: the identifier must resolve
to a locally stored official original record whose recomputed content hash
matches the declared hash. A bare identifier plus a declared hash is never
sufficient on its own; unresolved identifiers and hash mismatches fail closed.
This recipe lowers onboarding friction for judgment verification, but it is not
out-of-the-box: operators still obtain official access and download the
original files themselves.

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
