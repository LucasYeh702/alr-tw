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

For judgment candidates, a stable official identifier such as a JID may stand in
for an official URL when the verifier can map it to a downloaded official
original record and compute a documented content hash for that record.

HF-like data may support staging, audit, or evaluation, but it cannot be final citation authority.

Synthetic data is included only to make the demo reproducible without production data.
