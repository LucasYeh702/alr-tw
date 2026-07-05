# Release Notes

## v0.5.0 Externally Driven Tool Run Recording

- Adds MCP `begin_agentic_run` and `finalize_agentic_run` so the public server
  records and gates externally driven tool runs.
- Emits canonical `alr-tw.agentic_trace/v1` traces with `trace_kind:
  "externally_driven"` and recorded tool calls marked `execution_mode:
  "actual_tool"`.
- Keeps the repo boundary explicit: ALR-TW still ships no LLM and no agent
  implementation; the external MCP client supplies that role.
- Enforces non-bypass server-side computation for `final_action`,
  `safe_to_present`, `citation_use`, and `identifier_resolution`.
- Keeps answer retention fail-closed: client-drafted answer content is retained
  only when the trust gate returns `final_action == "answer"` and
  `safe_to_present == true`.
- Adds `docs/AGENT_CLIENT_GUIDE.md` with stdio MCP client configuration,
  suggested tool flow, and rendering rules.
- Adds `examples/external_agent_trace_demo.py`, a stdio JSON-RPC client demo
  showing one passing externally driven trace and one refused trace.
- Includes the identifier-backed quickstart example
  `examples/identifier_backed_demo.py`.
- Adds contribution templates for issues and pull requests.
- Notes platform protections in CI and release workflow, including the pinned
  gitleaks action SHA
  `ff98106e4c7b2bc287b24eaf42907196329070c7`.

No production corpus, real legal full text, cache, index, user log, credential,
or private retrieval parameter is included.

### Release Audit Record

- Date: 2026-07-05.
- Method: guard scripts, Ruff, full pytest suite, deterministic demo,
  agentic MCP client demo, identifier-backed demo, externally driven trace demo,
  and MCP stdio smoke over initialize, tools/list, `begin_agentic_run`, and
  `finalize_agentic_run`.
- Result: pass before tagging; no push or tag performed in this working round.

## v0.4.0 Identifier-Backed Verified Cache and Hardening

- Adds an opt-in source-policy capability
  (`ALR_TW_IDENTIFIER_BACKED_VERIFIED_CACHE`, default off): a stable official
  identifier such as a judgment JID may substitute for the official URL in
  `verified_cache` final-citation eligibility.
- The substitution is enforced by a resolver extension point: the identifier
  must resolve to a locally stored official original record and the recomputed
  content hash must match the declared `official_hash`. Unresolved identifiers
  and hash mismatches fail closed with explicit error codes
  (`IDENTIFIER_BACKED_DISABLED`, `IDENTIFIER_MATERIAL_NOT_ELIGIBLE`,
  `IDENTIFIER_UNRESOLVED`, `IDENTIFIER_HASH_MISMATCH`).
- Identifier substitution is limited to judgment-type records
  (`legal_material_type: "judgment"`); laws and constitutional materials keep
  the strict official-URL rule.
- Default behavior is unchanged from v0.3: without the opt-in, identifier-only
  `verified_cache` records are rejected.
- MCP `validate_citation` gains optional `legal_material_type`; resolution
  status is computed server-side and cannot be declared by callers. The public
  server ships only a synthetic demo resolver.
- Verified-cache rejections now return specific error codes (for example
  `VERIFIED_CACHE_INCOMPLETE`) instead of the generic rejection code.
- Clarifies the no-LLM and no-agent boundary in the READMEs and
  `docs/AGENTIC_WORKFLOW.md`: ALR-TW constrains an external MCP client or LLM
  runtime, while trust-gate decisions are deterministic harness decisions.
- Calibrates ranking wording: the repo ships demo formulas and common defaults
  for public tests, while tuned production ranking weights remain deliberately
  unpublished.
- Clarifies `docs/THREAT_MODEL.md` and `docs/TRUST_MODEL.md` responsibility
  boundaries: public code checks field presence and policy state; byte-level
  promotion verification belongs to the deployer's pipeline.
- Hardens release guards for secret-assignment patterns, non-UTF-8 handling
  including Big5 and UTF-16-like content, Taiwan-ID-shaped strings,
  judgment-identifier-shaped strings, the synthetic judgment namespace, and
  aligned file-size caps.
- Adds a gitleaks history-scan CI job and keeps release-history scanning in the
  published audit procedure.
- Adds `docs/DEPLOYMENT_STARTING_POINTS.md` with illustrative, non-production
  chunking, embedding, vector-index, lexical, and ranking starting points.
- Adds a public ingestion staging adapter skeleton and a staging to
  citation-validation test that proves staged records remain candidate-only and
  not final-eligible.
- Adopts `docs/RELEASE_AUDIT_PROCEDURE.md` as the repeatable release-readiness
  procedure.

No production corpus, real legal full text, cache, index, user log, credential,
or private retrieval parameter is included.

v0.2.1 shipped as an untagged commit on `main`; v0.3.0 is tagged on GitHub
(tag `v0.3.0`).

### Release Audit Record

- Date: 2026-07-05.
- Method: guard scripts, full test suite, demos, and manual history grep battery
  over the unpushed commits; gitleaks runs in CI.
- Result: no leaks found; all hardening gaps fixed pre-tag; publishing clone
  cleaned of non-public refs before tagging.

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
