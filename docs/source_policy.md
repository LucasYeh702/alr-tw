# Source Policy

Final citations must be official-grounded or verified cache with traceable official metadata.

TLR-like data may improve recall, but it cannot provide final citation
authority. It should be represented as `external_semantic_recall` and
`allow_candidate_only` until separately verified against an official source or a
complete verified cache.

Recommended production pattern: use TLR-like data as a high-recall source for
candidate discovery, then verify candidates against original files downloaded
from the Judicial Yuan or another official source. A local verified cache should
record official URL or identifier, content hash, download time, and verification
time before it can satisfy final-citation eligibility.

This repository does not provide Judicial Yuan API credentials or redistribute
official data. Operators must obtain any required official access themselves and
build the local verified cache from lawfully downloaded original files.

For judgment candidates, a stable official identifier such as a JID may stand in
for an official URL, but only through the opt-in identifier-backed capability
(`ALR_TW_IDENTIFIER_BACKED_VERIFIED_CACHE`, default off): a resolver must map
the identifier to a downloaded official original record and the recomputed
content hash must match the declared hash. This is enforced in code
(`verification/source_policy.py`, `verification/identifier_resolver.py`), not
only described here; an unresolved identifier or a hash mismatch fails closed.
Laws and constitutional materials always require an official URL.

HF-like data may support staging, audit, or evaluation, but it cannot be final citation authority.

Synthetic data is included only to make the demo reproducible without production data.
