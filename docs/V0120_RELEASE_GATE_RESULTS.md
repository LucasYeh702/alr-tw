# ALR-TW v0.12.0 Release Gate Results

Audit date: 2026-09-07 (Asia/Taipei). Package target: `0.12.0`.

This report covers local prepublication checks on the sanitized release tree.
It does not report a public push, public CI run, tag, or GitHub Release. The
containing Git revision identifies this report's source; the separate local
handoff manifest binds the frozen commit, tree, changed-path list, and exact
distribution SHA-256 values. Recheck public CI on the actual publication commit.

## Mandatory lanes

| Lane | Reproducible evidence | Result |
|---|---|---|
| A: deterministic trust-boundary attacks | `tests/integration/test_v012_release_gates.py` | Six attack classes blocked or constrained as specified; false refusals `0 / 2` on two positive synthetic fixtures |
| B: same-run snapshot receipts | `tests/unit/test_v012_snapshot_receipts.py` | 9 tests: issue, persist/reopen, exact-set binding, missing/forged/cross-run/expired receipts, purge, large passage sets, non-answer brief |
| C: verified-profile pass and refusal | `test_lane_c_pass_and_refuse_paths_finish_under_ten_minutes` | Synthetic pass/refusal pair runs through MCP dispatch; measured below 600 seconds |

Lane A covers caller-labelled official URLs, candidate-as-citation, legacy
metadata self-attestation, court/party role confusion, bounded absence as
consensus, and one-sided reversal markers. Some attack assertions exercise
the underlying deterministic gate directly; they are not all full MCP runs.
Lane C exercises `capabilities -> research -> continue -> finalization ->
validate` through MCP dispatch with injected synthetic transports, not live
official-network latency.

The valid statute path reaches pre-draft `ordinary`, then presentation only
after bound-answer validation. The fake JID path stays `refusal_only` / blocked,
with no answer body and with human-readable blockers and `safe_next_actions`.
Missing receipts allow at most `conditional`; expired, cross-run, or mismatched
persisted receipts fail closed. `ordinary` alone never grants `safe_to_present`.

## Reproduction

Use Python 3.11 or newer and an isolated environment with `.[dev,live]` and
build dependencies installed. The recorded local host uses Python 3.12.13.

```bash
ruff check .
mypy src
pytest -q --durations=10
pytest -q tests/integration/test_v012_release_gates.py --durations=10
pytest -q tests/unit/test_v012_snapshot_receipts.py --durations=10
python scripts/check_no_forbidden_files.py
python scripts/check_public_boundary.py
git diff --check HEAD
python -m build
python scripts/check_release_artifacts.py --version 0.12.0 dist/*.whl dist/*.tar.gz
```

## Local measured results

| Check | Observed result |
|---|---|
| Runtime and metadata | `0.12.0`, Python 3.12.13 |
| Static checks | Ruff 0.15.19 pass; mypy 2.3.1 pass, 128 source files |
| Full regression | 746 tests passed after selective RC3 integration; frozen-tree rerun retained in the refreshed local handoff |
| Lane A/C suite | 6 passed; pass/refusal pair 0.11 seconds in the recorded pre-freeze run |
| Lane B suite | 9 passed |
| Source privacy boundaries | Both public-boundary guards passed |
| Built distributions | Wheel and sdist metadata, paths and expanded contents passed both guards |
| Independent secret scan | Gitleaks 8.30.1: source, public history and both expanded distributions passed |
| Fresh base wheel | Import/version isolation and synthetic doctor passed without live/MCP SDK dependencies |
| Installed MCP stdio | Current `2025-11-25` and legacy `2024-11-05` passed; unsupported protocol rejected; verified profile exposes 13 tools |
| Installed answer boundary | Quick run stops before answer validation; unbound draft blocked and answer body null |
| Standalone `tlr` extra | Python 3.11.15 and 3.12.13 isolated installs passed; real TLS context and synthetic adapter transport, no `live` dependencies |

Durations are local observations, not a performance guarantee. Final frozen-tree
logs and exact artifact hashes are held in the non-published handoff. The
three-reviewer scope and finding dispositions are recorded in
[V0120_THREE_WAY_REVIEW.md](V0120_THREE_WAY_REVIEW.md).
AGY completed and its confirmed findings were repaired locally. Grok's first
run timed out with no report; the maintainer elected not to request another
external review. This is not a claim of unanimous three-reviewer approval.

## Optional live dependency observation

The observation below is historical (2026-09-05), not a refreshed live probe of
the RC3-integrated candidate. The integration audit uses synthetic transports.

An installed-wheel `alr-tw doctor --live` probe on 2026-09-05 reported the MOJ
law and Constitutional Court providers healthy with `system_truststore`. The
Judicial Yuan judgment website returned `OFFICIAL_SOURCE_BLOCKED` /
`OFFICIAL_SITE_WAF_BLOCKED`; doctor exited 1 and `live_ready=false` as intended.
No TLS bypass or alternate evidence promotion was used. This is an external
availability limitation, not a passing end-to-end live legal-research test.
No new live TLR recall, real judgment verification, full research timing, or
ChronoLex accuracy evaluation was performed in this final-release audit.

## Interpretation limits

- A gate may allow verified material while the ultimate legal conclusion is
  incomplete, irrelevant, or wrong. This third outcome class remains a known
  limitation, not a re-labelled deterministic test failure. Semantic entailment,
  legal subsumption, model correctness, and global recall are not measured here.
- The `0 / 2` false-refusal denominator is deliberately small; it is not a
  model-accuracy or real-user experience estimate.
- No live timing, speed-up factor, or accuracy comparison is claimed from
  withheld user examples. Public tests use synthetic/reduced engineering inputs.
- A passing receipt binds same-run material, not corpus completeness, judgment
  finality, absence of opposing views, or national consensus.
- Similar-case quick mode remains bounded to at most five verification attempts
  and at most `qualified` / `conditional`; zero verified sources still refuses.
- Lane D and broad live-provider acceptance remain optional and cannot replace
  mandatory lanes. Legislative locators remain candidate-only; no PDF/DOC
  parsing, semantic opposition classifier, or expanded analysis envelope is
  claimed. This remains a public preview, not production readiness.
