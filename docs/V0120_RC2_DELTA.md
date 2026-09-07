# ALR-TW v0.12.0 pre-release contract hardening

This candidate incorporates the RC1 freeze patch and the remaining GPT-5.6 Pro review findings without adding a new product feature.

## Trust-boundary corrections

- `alr-tw verify-provider --input` is explicitly a caller-supplied structural check. It cannot emit runtime promotion authorization, ordinary eligibility, scoped-absence authorization, eligible source/evidence IDs, or a server-owned decision.
- `execute_legal_research` exposes `operation_prefix`, not `operation_id`. The value names per-step operation records and is explicitly not a composite request idempotency key. Unused `client_id` and `request_id` fields were removed from this tool surface.
- Quick judgment intent recognizes a bare canonical JID or formal judgment citation even when no natural-language marker such as 判決／字號 is present.
- RC1's explicit `quick + include_counter_authority=true` rejection is retained.

## Release evidence

The prior RC1 audit remains historical evidence. RC2 must pass the normal CI and the new `release-gate` workflow on the exact RC2 commit before any public-promotion decision. The release gate runs Ruff, mypy, public-boundary checks, the full regression suite, package build, fresh-wheel install, CLI doctor, and MCP stdio initialize/tools-list smoke.

This document is a delta record, not a release authorization.
