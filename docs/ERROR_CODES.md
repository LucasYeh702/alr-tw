# ALR-TW Error Codes

| Code | Meaning | Recommended action |
|---|---|---|
| `NO_FINAL_CITATION` | No source qualified as final citation | refuse |
| `REJECTED_CITATION` | Citation source tier or metadata was rejected by trust policy | refuse |
| `UNVERIFIABLE_CITATION` | Citation could not be verified for final use | refuse |
| `LAWS_COVERAGE_LOW` | Required law coverage is absent or low confidence | refuse |
| `JUDGMENTS_COVERAGE_LOW` | Required judgment coverage is absent or low confidence | refuse |
| `CANDIDATE_ONLY_SOURCE` | Source is only a candidate lead | refuse or verify elsewhere |
| `SYNTHETIC_DEMO_ONLY` | Synthetic fixture cannot be legal authority | refuse |
| `VERIFIED_CACHE_INCOMPLETE` | Verified cache metadata is incomplete | refuse |
| `IDENTIFIER_BACKED_DISABLED` | Identifier-backed verified cache is opt-in and not enabled | refuse |
| `IDENTIFIER_MATERIAL_NOT_ELIGIBLE` | Identifier substitution is limited to judgment records | refuse |
| `IDENTIFIER_UNRESOLVED` | Official identifier did not resolve to a local original record | refuse |
| `IDENTIFIER_HASH_MISMATCH` | Recomputed hash of the resolved original record does not match | refuse |
| `COVERAGE_LOW_CONFIDENCE` | Required legal coverage is low | refuse |
| `SOURCE_REJECTED` | Source tier or metadata rejected | refuse |
| `SOURCE_UNVERIFIABLE` | Source could not be verified | refuse |
| `CLAIM_SUPPORT_NOT_CHECKED` | Source exists but claim support was not checked | human_review_required |
| `CLAIM_SUPPORT_UNCHECKED` | Claim-support not evaluated against legal evidence segments | human_review_required |
| `CLAIM_SUPPORT_NEEDS_REVIEW` | Claim support is ambiguous and needs human review | human_review_required |
| `CLAIM_UNSUPPORTED` | One or more core claims have no supporting evidence | refuse |
| `CLAIM_OVERSTATED` | Claim support is broader than provided legal segments | refuse or human_review_required |
| `CLAIM_CONTRADICTED` | Evidence conflicts with the claim text | refuse |
| `CLAIM_ROLE_ERROR` | Claim incorrectly inferred from wrong legal segment role | refuse or human_review_required |
| `HUMAN_REVIEW_REQUIRED` | Human legal review is required | human_review_required |
| `PRIVATE_DATA_NOT_ALLOWED` | Private data must not enter public harness | refuse |
| `PRODUCTION_DATA_EXCLUDED` | Production data is outside public repo | refuse |
| `SCHEMA_VALIDATION_FAILED` | Input or trace schema invalid | refuse |
