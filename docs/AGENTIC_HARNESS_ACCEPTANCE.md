# ALR-TW Agentic Harness Acceptance

This document defines the minimum public evidence required before ALR-TW can
describe itself as an Agentic Legal RAG / MCP Harness.

## Accepted v0.4 Claim

ALR-TW v0.4 may claim to be a bounded agentic legal RAG harness that constrains
an external agent because the repository includes:

1. A deterministic execution graph:
   `query_understanding -> source_plan -> retrieval -> source_classification ->
   citation_validation -> coverage_gate -> trust_gate -> final_decision`.
2. Runnable local harness code under `src/alr_tw/harness/`.
3. MCP stdio tools for agentic demo runs, validation reports, trust model
   inspection, search, exact lookup, and citation validation.
4. A stable MCP result envelope:
   `alr-tw.mcp_tool_result/v1`.
5. A stable run trace schema:
   `alr-tw.agentic_trace/v1`.
6. Deterministic synthetic scenarios covering answer, refusal, and
   human-review-required outcomes.
7. Trace fields that distinguish deterministic harness records from live tool
   execution logs through `execution_mode`.
8. Decision traces that show citation-validation counts and trust-gate output.
9. Fail-closed trust behavior for candidate-only sources, synthetic-only
   sources, incomplete verified-cache metadata, identifier-backed verified
   cache without resolver confirmation, missing final citations, and low
   coverage.
10. Human-review-required traces that do not include directly presentable
    answer bodies.
11. A public claim-grounding contract (AnswerClaim / ClaimSupport / Semantic
    Grounding Summary) and dedicated synthetic failure scenarios for claim-level
    overclaim checks.
12. MCP tool extensions for `get_claim_grounding_policy`,
    `extract_answer_claims`, and `check_claim_support`.
13. Markdown validation reports that include answer claims, claim-support review,
    and semantic hallucination risk.
14. An opt-in identifier-backed `verified_cache` path for judgment records,
    where a server-side resolver must map the identifier to a locally stored
    official original record and verify a matching content hash before final
    citation eligibility is allowed.
15. Fail-closed tests and error codes for disabled identifier-backed cache,
    unresolved identifiers, hash mismatches, and non-judgment materials.
16. Public/private boundary checks that block production data, caches, indexes,
    logs, credentials, and local sensitive paths.
17. Tests and CI gates for the harness, trace schema, MCP server, reports,
    source policy, claim-grounding outputs, and public boundary.

## Not Claimed

ALR-TW v0.4 does not claim to be:

- an unrestricted autonomous legal agent
- an autonomous legal agent that practices law or independently completes legal judgment
- a production legal research agent
- an LLM or agent implementation shipped in this repo
- a real Taiwan legal database
- a source of legal advice
- an external LLM provider runtime
- a production citation-freshness watcher
- a full claim-support entailment engine
- a claim-support entailment engine that can always output legal conclusions without human review
- a temporal law applicability engine
- a procedural posture or appellate-lineage classifier
- a bundled TLR service or third-party recall provider
- a provider of Judicial Yuan API credentials or downloaded official data
- a production raw-backed verifier over real Judicial Yuan archives
- a replacement for official-source verification or human legal review

## Required Evidence Before Release

Before publishing a release that uses the Agentic Legal RAG / MCP Harness name,
complete the audit steps in `docs/RELEASE_AUDIT_PROCEDURE.md` and make sure
the following commands pass:

```bash
python3 scripts/check_no_forbidden_files.py
python3 scripts/check_public_boundary.py
uv run --extra dev ruff check .
uv run --extra dev pytest
uv run --extra dev alr-tw-demo
uv run --extra dev python examples/agentic_mcp_client_demo.py
```

The release must also include at least these public artifacts:

- `docs/AGENTIC_WORKFLOW.md`
- `docs/TRUST_MODEL.md`
- `docs/TLR_CANDIDATE_MODE.md`
- `docs/TLR_CANDIDATE_MODE.zh-TW.md`
- `docs/TOOL_CONTRACT.md`
- `docs/TRACE_SCHEMA.md`
- `docs/VALIDATION_REPORT.md`
- `docs/RELEASE_NOTES.md`
- `docs/RELEASE_AUDIT_PROCEDURE.md`
- `docs/DEPLOYMENT_STARTING_POINTS.md`
- `docs/PUBLIC_PRIVATE_BOUNDARY.md`
- `examples/agentic_runs/*.json`
- `examples/reports/*.md`
