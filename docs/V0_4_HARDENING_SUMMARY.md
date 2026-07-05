# ALR-TW v0.4 Public Hardening Summary

This document records the public-safe hardening work shipped in ALR-TW v0.4.
It summarizes the release-facing capability and safety boundaries without
including internal review labels, private parameters, production corpus details,
or non-public operational notes.

## Release Outcome

ALR-TW v0.4 keeps the public repository within the reference-harness boundary:

- synthetic fixtures only
- deterministic harness and MCP tool contracts
- source tier and citation validation policy
- claim-grounding schema and demo checks
- public/private boundary checks
- CI gates and release audit procedure
- no production legal full text, cache, index, user log, credential, or private
  ranking / chunking / index parameter

The v0.4 release adds one behavior-changing capability and several release-safety
improvements. The behavior change is intentionally opt-in and fail-closed by
default.

## Identifier-Backed Verified Cache

v0.4 adds an opt-in path for judgment records where a stable official identifier
such as a JID can participate in `verified_cache` final-citation eligibility.
This path is not a relaxation of citation policy. It is a resolver-backed
verification control point:

- The capability is disabled by default.
- Deployers must explicitly enable `ALR_TW_IDENTIFIER_BACKED_VERIFIED_CACHE`.
- The path is limited to `legal_material_type: "judgment"`.
- Laws and constitutional materials still require an official URL.
- A server-side resolver must map the official identifier to a local official
  original record.
- The resolver must recompute the content hash and match the declared
  `official_hash`.
- Unresolved identifiers, hash mismatches, disabled opt-in state, and
  non-judgment materials fail closed with explicit error codes.

The public repository includes only a synthetic demo resolver and extension
point. A real deployment must provide its own official-data download,
verified-cache promotion, hash recomputation, access-control, and review
pipeline.

## Claim And Agent Boundary Calibration

v0.4 also makes the public description of ALR-TW stricter and more precise:

- ALR-TW constrains an external MCP client or LLM runtime; this repository does
  not ship an LLM or autonomous legal agent implementation.
- Trust-gate decisions are deterministic harness decisions, not caller-declared
  agent decisions.
- Demo ranking formulas and common defaults are illustrative public test
  fixtures, not production tuning parameters.
- Public code checks citation policy state and metadata presence; byte-level
  official-source promotion remains the deployer's responsibility unless
  implemented by their local verifier.
- TLR-like semantic recall remains candidate-only until separately matched to an
  official source or qualifying local `verified_cache`.

## Release Guard Improvements

The v0.4 release hardens public release checks in the repository:

- forbidden-file checks cover secret-assignment patterns
- public-boundary checks and forbidden-file checks use aligned size limits
- oversized tracked text files are not silently skipped
- non-UTF-8 tracked text files are rejected
- Taiwan-ID-shaped strings are blocked
- real-shaped judgment identifiers outside the synthetic namespace are blocked
- the synthetic judgment namespace is explicitly allowed
- CI includes a gitleaks history scan
- the release audit procedure is documented and linked from the public docs

These checks are defense-in-depth for the public reference repository. They do
not replace deployer-side security review for private adapters, private corpora,
or production runtimes.

## Public Deployment Starting Points

v0.4 adds public, illustrative deployment starting points for users who want to
replace synthetic adapters with their own legal data sources. These notes are
not production settings and do not reveal private runtime parameters. They
describe how to reason about:

- exact lookup
- lexical recall
- semantic recall
- chunking and overlap
- embedding choice
- vector-index trade-offs
- demo ranking and RRF defaults
- staging-to-verification promotion

Implementers should measure precision, recall, latency, update cadence, storage
cost, authorization constraints, and review requirements on their own data.

## Required Validation

Before publishing a v0.4-compatible release, the following commands should pass:

```bash
git diff --check
python3 scripts/check_no_forbidden_files.py
python3 scripts/check_public_boundary.py
uv run --extra dev ruff check .
uv run --extra dev pytest
uv run --extra dev alr-tw-demo
uv run --extra dev python examples/agentic_mcp_client_demo.py
```

GitHub Actions should also pass on both `main` and the release tag, including the
history secret scan.

## Done Criteria

The v0.4 public release is considered complete when:

- default citation behavior remains fail-closed
- identifier-backed verified cache is opt-in and resolver-backed
- identifier-only `verified_cache` records are rejected by default
- non-judgment materials cannot use identifier-only final citations
- claim-grounding and source-policy docs match the shipped code
- release guards cover secrets, local paths, non-UTF-8 text, oversized text,
  Taiwan-ID-shaped strings, and real-shaped judgment identifiers
- CI includes test and history-secret-scan jobs
- release notes and GitHub Releases use public-safe wording
- the worktree is clean at tag time
