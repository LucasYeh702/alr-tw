# v0.6.0 Baseline Audit

Status: WP-00 implementation baseline for the v0.6.0 public preview.

This audit records the dependency and trust-boundary conditions that must be
preserved or corrected while the server-owned research flow is introduced. It
does not claim that live providers are available yet.

## Existing entry points

- `alr-tw-demo`: deterministic synthetic harness.
- `alr-tw-mcp`: compatibility entry point delegating to the existing MCP server.
- `tw-legal-rag-mcp`: existing low-level MCP server.
- `alr-tw-boundary-check`: public/private boundary guard.

## Import baseline

The v0.5 code contains imports in both directions:

```text
alr_tw.harness.orchestrator
  -> tw_legal_rag_mcp.legal_nlp
  -> tw_legal_rag_mcp.verification

tw_legal_rag_mcp.mcp_server / agentic / verification
  -> alr_tw.harness
  -> alr_tw.verification
```

The v0.6 migration rule is:

```text
alr_tw contracts and research core
  <- provider implementations and compatibility namespace
```

The new `alr_tw.contracts` and `alr_tw.config` modules must not import
`tw_legal_rag_mcp`. Existing harness imports are compatibility debt to be
removed in later work packages, not a pattern for new code.

## Reusable components

- MCP result envelope and JSON-RPC compatibility tests.
- Synthetic fixtures and deterministic execution graph.
- Trace and validation report shapes.
- Citation, coverage and claim-support test fixtures.
- Public boundary and forbidden-file guards.
- Identifier-backed verified-cache resolver.

## Required restructuring

- Move provider-neutral source, research and storage contracts under `alr_tw`.
- Make all recommended live flows use one server-owned state machine and one
  final policy engine.
- Replace caller-supplied evidence text and source-tier declarations with
  server-issued source and evidence identifiers.
- Keep TLR-specific transport outside the provider-neutral core.
- Treat the existing `tw_legal_rag_mcp` contracts as compatibility surface,
  with tested re-exports where identities must remain stable.

## Trust-boundary blockers

The following v0.5 behavior must not be inherited by the recommended live flow:

1. A caller can submit `source_tier=official` to the low-level citation tool.
2. The legacy source policy allows the official tier without proving that the
   server fetched and pinned the cited bytes.
3. Caller-supplied claims and evidence segments can reach lexical
   claim-support checks.
4. Externally driven runs can finalize without proving that every mandatory
   research stage ran.
5. The legacy agentic runner and external finalizer use different trust-gate
   paths.

Until the compatibility tools are migrated, they remain synthetic/reference
interfaces and must not be advertised as the v0.6 live evidence path.

## Public-only boundary

The v0.6 public repository may contain contracts, provider code, synthetic
fixtures and public-safe parser fixtures. It must not contain production legal
corpora, TLR credentials, private indexes, real user queries, private deployment
paths or Legal Portal internals.
