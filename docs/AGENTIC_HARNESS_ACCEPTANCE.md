# ALR-TW Agentic Harness Acceptance

This document defines the minimum public evidence required before ALR-TW can
describe itself as an Agentic Legal RAG / MCP Harness.

## Accepted v0.2.1 Claim

ALR-TW v0.2.1 may claim to be an AI-agent-driven, bounded agentic legal RAG harness
because the repository includes:

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
   sources, incomplete verified-cache metadata, missing final citations, and
   low coverage.
10. Human-review-required traces that do not include directly presentable
    answer bodies.
11. Markdown validation reports generated from run traces.
12. Public/private boundary checks that block production data, caches, indexes,
   logs, credentials, and local sensitive paths.
13. Tests and CI gates for the harness, trace schema, MCP server, reports,
    source policy, and public boundary.

## Not Claimed

ALR-TW v0.2.1 does not claim to be:

- an unrestricted autonomous legal agent
- an autonomous legal agent that practices law or independently completes legal judgment
- a production legal research agent
- a real Taiwan legal database
- a source of legal advice
- an external LLM provider runtime
- a production citation-freshness watcher
- a full claim-support entailment engine
- a temporal law applicability engine
- a procedural posture or appellate-lineage classifier
- a replacement for official-source verification or human legal review

## Required Evidence Before Release

Before publishing a release that uses the Agentic Legal RAG / MCP Harness name,
the following commands must pass:

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
- `docs/TOOL_CONTRACT.md`
- `docs/TRACE_SCHEMA.md`
- `docs/VALIDATION_REPORT.md`
- `docs/RELEASE_NOTES.md`
- `docs/PUBLIC_PRIVATE_BOUNDARY.md`
- `examples/agentic_runs/*.json`
- `examples/reports/*.md`
