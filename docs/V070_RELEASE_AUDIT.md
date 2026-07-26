# ALR-TW v0.7.0 Release Audit

Release decision: **ACCEPTED FOR v0.7.0 PUBLIC PREVIEW**

This audit records the local release checks for the agent-neutral public-safe
verification runtime. It does not claim complete Taiwan-law corpus coverage,
semantic entailment, systematic counter-authority search, or a production SLA.

## Release identity

- package: `alr-tw 0.7.0`
- tag: `v0.7.0`
- public branch: `main`
- data boundary: contracts, validators, official-provider interfaces, and
  synthetic fixtures only; no private Legal Portal runtime or production corpus
- optional recall: TLR remains `external_semantic_recall` and candidate-only;
  official evidence still requires Judicial Yuan verification

## Checks executed

| Check | Result |
|---|---|
| Full pytest regression | **PASS** — 325 passed |
| Ruff | **PASS** |
| mypy | **PASS** — 98 source files |
| Public-boundary lint | **PASS** |
| Forbidden-file scan | **PASS** |
| `git diff --check` | **PASS** |
| Fresh wheel build/import smoke | **PASS** — 23 MCP tools; `validate_civil_analysis` present |
| Explicit secret/token and local-path pattern scan | **PASS** — no hits |

## Known release limitations

- The built-in legal-context provider is synthetic-only; live deployments must
  supply a provider-neutral temporal／authority／legal-validity provider.
- TLR and Judicial Yuan live canaries are not part of this local release run;
  network availability, source freshness, ranking, and parser behavior remain
  deployment concerns.
- Historical law versions, systematic counter-authority search, semantic
  entailment, and complete legal-domain templates remain out of scope.

Green synthetic and structural checks establish contract behavior only; they do
not establish production legal correctness.
