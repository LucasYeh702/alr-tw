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

## Citation Eligibility

`citation_eligibility` is separate from claim support:

- `final_eligible`: source tier and metadata can support final-citation eligibility.
- `candidate_only`: source may help discovery only.
- `demo_only`: source is synthetic demonstration data only.
- `rejected`: source tier or metadata failed the policy.
- `missing`: citation was not found.

`support: not_checked` means the public harness has not verified that a source
actually entails a legal claim. Production systems should add a separate
claim-support or legal-effect layer before presenting legal analysis.

## Fail-Closed Rules

ALR-TW refuses when there is no final citation, a rejected or unverifiable
source, or low required coverage. It may return `human_review_required` only
when final citation eligibility exists and the remaining blocker is unchecked
claim support. Non-answer traces must keep `answer` as `null`.
