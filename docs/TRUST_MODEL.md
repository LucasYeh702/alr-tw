# ALR-TW Trust Model

ALR-TW separates source discovery from final citation authority.

## Source Tiers

| Tier | Role | Final citation |
|---|---|---|
| `official` | Official or official-grounded source | Yes |
| `verified_cache` | Cache with official URL, hash, and verified time | Yes, if complete |
| `staging` | Ingestion or audit candidate | No |
| `external_semantic_recall` | Candidate recall from an external semantic system | No |
| `synthetic` | Demo and test fixture | No |
| `unknown` | Missing or unsupported source tier | No |

## Citation Use

- `allow_final`: may satisfy final citation requirement.
- `allow_candidate_only`: may help discovery but cannot support final answer.
- `demo_only`: synthetic fixture only.
- `reject`: cannot be used.

## Fail-Closed Rules

ALR-TW refuses or requires human review when there is no final citation, a rejected
or unverifiable source, low required coverage, or unchecked claim support.

