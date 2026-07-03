# Release Notes

## v0.3.0 Claim-Grounding Patch

- Adds v0.3 trace fields for claim grounding:
  `answer_claims`, `claim_support`, `semantic_grounding_summary`, and
  `semantic_failure_reasons`.
- Adds MCP tools:
  `get_claim_grounding_policy`, `extract_answer_claims`, `check_claim_support`.
- Adds synthetic claim-grounding scenarios:
  `pass_claim_supported`, `fail_party_argument_as_court_view`,
  `fail_overstated_case_specific_rule`, `fail_unsupported_paraphrase`,
  `human_review_claim_unchecked`.
- Extends validation report to include sections:
  Answer Claims / Claim Support Review / Semantic Hallucination Risk.
- Documents v0.3 claim-grounding contract and updates v0.3 acceptance scope.
- Keeps public-safe boundary: only synthetic fixtures, schemas, harness logic,
  tests, and docs are included; no production legal full-text data.

## v0.2.1 Hardening Patch

This patch tightens the public Agentic Legal RAG / MCP Harness claim.

- Adds explicit `execution_mode` to trace tool calls.
- Adds `decision_trace` to canonical agentic traces.
- Ensures non-answer traces keep `answer` as `null`.
- Makes `agentic_legal_research` return the canonical
  `alr-tw.agentic_trace/v1` shape.
- Adds MCP support for complete `verified_cache` citation metadata.
- Splits citation eligibility from claim support; public support remains
  `not_checked`.
- Improves demo sensitive-text masking for unsegmented Chinese names and Taiwan
  ID patterns.
- Expands MCP coverage for trust model and exact lookup tools.
- Regenerates public synthetic examples and validation reports.

No production corpus, real legal full text, cache, index, user log, credential,
or private retrieval parameter is included.
