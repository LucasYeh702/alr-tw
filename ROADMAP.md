# Roadmap

## v0.1

- synthetic demo data
- source trust policy
- citation validation
- forbidden file checker
- CI test workflow

## v0.2

- ALR-TW Agentic Legal RAG / MCP Harness positioning
- release acceptance contract for the harness name
- deterministic execution graph
- agentic trace schema
- MCP stdio server with wrapped tool results
- validation report builder
- public / private boundary checker
- synthetic pass / fail / human-review scenarios

## v0.3

- claim-grounding contract (LegalSegment / AnswerClaim / ClaimSupport / summary) in public schema
- MCP claim-grounding tools: `get_claim_grounding_policy`, `extract_answer_claims`, `check_claim_support`
- semantic hallucination synthetic scenarios covering supported, overstated, role errors, unsupported, unchecked
- validation report sections for answer claims, claim-support review, semantic risk
- v0.3 acceptance docs and boundary alignment

## v0.4

- opt-in identifier-backed `verified_cache` for judgment records
- resolver extension point with synthetic demo resolver (resolve + rehash)
- fail-closed identifier error codes and gate assertion tests
- MCP `validate_citation` support for `legal_material_type`

## v0.5

- session-recorded MCP runs that record and gate externally driven tool runs
- externally-driven traces with `trace_kind: "externally_driven"` and
  `execution_mode: "actual_tool"`
- external MCP client guide and stdio JSON-RPC example
- identifier-backed quickstart example
- contribution templates, platform protections, and pinned gitleaks action SHA

## Future

- official adapter contracts without bundled production cache
- time-law versioning
- citation graph
- administrative letter ingestion
- enterprise RBAC / audit trail
- Taiwan-specific legal reranker
