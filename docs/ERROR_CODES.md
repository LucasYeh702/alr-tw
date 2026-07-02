# ALR-TW Error Codes

| Code | Meaning | Recommended action |
|---|---|---|
| `NO_FINAL_CITATION` | No source qualified as final citation | refuse |
| `CANDIDATE_ONLY_SOURCE` | Source is only a candidate lead | refuse or verify elsewhere |
| `SYNTHETIC_DEMO_ONLY` | Synthetic fixture cannot be legal authority | refuse |
| `VERIFIED_CACHE_INCOMPLETE` | Verified cache metadata is incomplete | refuse |
| `COVERAGE_LOW_CONFIDENCE` | Required legal coverage is low | refuse |
| `SOURCE_REJECTED` | Source tier or metadata rejected | refuse |
| `SOURCE_UNVERIFIABLE` | Source could not be verified | refuse |
| `CLAIM_SUPPORT_NOT_CHECKED` | Source exists but claim support was not checked | human_review_required |
| `HUMAN_REVIEW_REQUIRED` | Human legal review is required | human_review_required |
| `PRIVATE_DATA_NOT_ALLOWED` | Private data must not enter public harness | refuse |
| `PRODUCTION_DATA_EXCLUDED` | Production data is outside public repo | refuse |
| `SCHEMA_VALIDATION_FAILED` | Input or trace schema invalid | refuse |

