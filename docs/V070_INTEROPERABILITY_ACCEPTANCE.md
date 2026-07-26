# ALR-TW v0.7.0 Interoperability Acceptance

This is the release acceptance record for the v0.7.0 public preview.

ALR-TW v0.7.0 is an agent-neutral Taiwan-law research verification runtime.
It preserves server-owned research state,
TLR candidate-only recall, official evidence promotion, claim validation,
short-lived storage, and purge while allowing an arbitrary external reasoning
client to propose legal issues and authority locators.

The private Legal Portal is the upstream incubator and internal
production/reference implementation. ALR-TW is its independently implemented
public-safe contract and validator extraction, not a parallel full deployment
and not a reduced corpus. The public package has no private runtime dependency.

## Required invariants

- Core contracts and tool names do not depend on a named agent frontend.
- `get_legal_research_capabilities` reports ownership and limitations before a run.
- `server_managed` remains the backward-compatible default discovery mode.
- `client_assisted` requires an immutable registered plan before research.
- Every registered plan is `untrusted_client_proposal`.
- External authority locators are candidate-only and cannot contain evidence,
  source-tier attestations, content hashes, or final trust decisions.
- Client-assisted judgment discovery skips duplicate keyword/TLR recall and
  still performs official exact lookup.
- 外部 agent 不能注入正式證據或自行決定 final status.
- Every core issue requiring a conclusion must be explicitly bound to at least
  one final claim.
- Issue binding coverage does not claim semantic entailment.
- `CivilLawAnalysis` remains `untrusted_client_proposal` and contains only
  server-resolved IDs, never client-supplied source bodies or trust attestations.
- A `met` element requires a normative source plus a server-owned fact or
  eligible evidence reference.
- Every element has an explicit burden-of-proof record.
- Legal effects distinguish right-constituting, right-impeding,
  right-extinguishing, defense, liability-reduction, and remedy-calculation
  roles.
- Temporal applicability, authority, and legal validity are provider-neutral
  server assessments; unresolved normative context fails closed.
- `not_found_in_scope` cannot establish that no counter-authority exists.
- `validate_civil_analysis` never authorizes a final answer.
- blocked 不包含 answer body.
- Existing server-managed tools remain backward compatible.

## Taiwan civil-law structure

The proposal contract distinguishes claim basis, constitutive elements,
defenses, burden of proof, procedural prerequisites, legal effect, temporal
applicability, norm hierarchy, authority weight, and counter-authority issues.
These classifications remain client proposals until server-side source,
role, time, and evidence checks pass.

The public P0 contract also records `alleged`, `admitted`, `disputed`,
`supported`, `proven`, `contradicted`, `inadmissible`, and `excluded`
fact/evidence states. These labels do not become authoritative merely because
the client submitted them.

## Not claimed

The public-preview version 不宣稱 it provides an LLM, 完整台灣法律資料庫, full
historical-law coverage, systematic counter-authority search, semantic
entailment, legal advice, or a production SLA. It also does not claim:

- formal resolution of uncertain legal concepts;
- automatic special-law priority, claim concurrence, or damage aggregation;
- complete evidence admissibility, probative weight, or procedural timing;
- complete criminal-law, administrative-law, labor, family, consumer,
  corporate, securities, intellectual-property, tax, procurement, or
  enforcement templates.

## Release evidence

Acceptance requires contract validation tests, MCP schema and JSON-RPC tests,
client-assisted no-duplicate-recall integration tests, explicit core-issue
coverage tests, synthetic validated／qualified／blocked civil-analysis flows,
all legacy regressions, Ruff, mypy, public-boundary checks, forbidden-file checks,
and a fresh wheel smoke test. The v0.7.0 release run recorded 326 passing tests,
98 mypy-checked source files, 23 MCP tools including `validate_civil_analysis`,
and no public-boundary violations. Green synthetic tests prove contract
behavior, not production legal correctness.
