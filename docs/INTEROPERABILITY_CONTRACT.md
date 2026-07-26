# ALR-TW Agent-Neutral Interoperability Contract

本文件定義 v0.7.0 的前端無關接口。任何能呼叫 MCP tool 的法律
agent、prompt skill、workflow engine 或人工控制程式都可以使用同一套契約；
核心程式不依賴特定前端專案、模型或提示詞。

## Product lineage

The maintainer's private Legal Portal is the upstream incubator and
production/reference implementation. ALR-TW is a contract-first, public-safe
extraction of reusable trust invariants; it is not a parallel full product and
not a smaller copy of the private corpus.

The extraction direction is one-way:

```text
private upstream incubator
  -> public-safe contracts / validators / synthetic fixtures
  -> optional external reasoning clients
```

The public package must not import or require the private runtime. It contains
no private paths, corpus, indexes, manifests, production parameters, operational
state, or private evaluation labels. A user supplies a conforming provider
through public contracts.

## Responsibility boundary

| Responsibility | Owner | Can the client override it? |
|---|---|---|
| Legal issue identification and natural-language reasoning | external client | yes |
| Initial source discovery strategy | selected per run | only between supported modes |
| Official source verification | ALR-TW server | no |
| Evidence promotion | ALR-TW server | no |
| Final validation decision | ALR-TW server | no |

`get_legal_research_capabilities` returns the machine-readable
`alr-tw.interoperability-capabilities/v1` contract before a run is created.
Clients must inspect this response instead of assuming that historical law,
counter-authority search, or a particular material type is available.

## Optional integration examples

The contract is project-neutral. The following are non-normative examples, not
dependencies or co-distributed components:

| Project | Optional role | Suggested ALR-TW path |
|---|---|---|
| [TLR (Taiwan Legal RAG)](https://github.com/aa0101181514/tw-legal-rag) | Semantic recall of ordinary-judgment candidates | Let ALR-TW call it through `hybrid_verified`, or submit already selected locators through `client_assisted` |

TLR integration does not transfer evidence authority:
its results remain `external_semantic_recall` candidates. If the frontend has
already called TLR, it must not also select `server_managed` TLR recall for the
same run.

## Discovery modes

### `server_managed`

This is the v0.7.0-compatible default. ALR-TW plans and executes its bounded
official/TLR discovery obligations. No external research plan is required.

### `client_assisted`

The external client proposes legal issues and exact authority locators. The
client must call `submit_legal_research_plan` before
`continue_legal_research`.

In this mode:

- a law locator is required because statutory-law coverage remains mandatory;
- `standard` and `deep` runs also require at least one judgment locator;
- a constitutional locator is required when the query schedules a
  constitutional-research obligation;
- a plan may add judgment, constitutional, temporal, or counter-authority
  obligations even when the original query did not trigger them;
- keyword and TLR judgment recall are skipped when registered judgment
  locators are available;
- every client locator remains candidate-only until ALR-TW performs exact
  official lookup.

Missing required locators fail early with
`RESEARCH_PLAN_REQUIRED_LOCATOR_MISSING`. ALR-TW does not silently fall back to
a second discovery path because doing so would hide duplicate provider calls.

## Research plan proposal

The accepted input schema is `alr-tw.research-plan-proposal/v1`.

```json
{
  "plan_id": "plan-001",
  "issues": [
    {
      "issue_id": "issue-duty",
      "label": "法定義務",
      "proposition": "行為人是否負有法定義務？",
      "category": "constitutive_element",
      "importance": "core",
      "requires_conclusion": true
    }
  ],
  "authority_locators": [
    {
      "locator_id": "law-184",
      "material_type": "law",
      "citation": "民法第184條",
      "purpose": "primary_rule",
      "issue_ids": ["issue-duty"]
    }
  ]
}
```

The civil-law issue categories are:

- `claim_basis`
- `constitutive_element`
- `defense`
- `burden_of_proof`
- `procedural_prerequisite`
- `legal_effect`
- `temporal_applicability`
- `norm_hierarchy`
- `authority_weight`
- `counter_authority`
- `other`

Every core issue requiring a conclusion must be connected to at least one
authority locator. Parent/child issue cycles, unknown references, duplicate
identifiers, unknown fields, client evidence, and caller-supplied trust
decisions are rejected.

## Candidate-only registration

`submit_legal_research_plan` stores an immutable
`alr-tw.registered-research-plan/v1` record with:

- a server receipt timestamp;
- a deterministic SHA-256 proposal digest;
- `trust_status=untrusted_client_proposal`.

The client may submit a citation or identifier, but not source text,
`official=true`, evidence spans, content hashes, or final trust decisions.
For judgments, ALR-TW converts the locator into an untrusted typed candidate,
then performs the same Judicial Yuan identity and full-text verification used
for every other candidate.

## Civil-law analysis proposal

`alr-tw.civil-law-analysis/v1` is an optional public envelope for a client to
propose:

- claims and constitutive elements;
- the legal effect of each element or defense:
  `right_constituting`, `right_impeding`, `right_extinguishing`, `defense`,
  `liability_reduction`, or `remedy_calculation`;
- element-level burden type, bearer, presumption, shift, standard of proof,
  rebuttal status, and normative-source IDs;
- facts and evidence states from `alleged` through `proven`,
  `contradicted`, `inadmissible`, and `excluded`;
- defenses, bounded counter-authority coverage, and procedural posture.

The entire envelope remains `untrusted_client_proposal`. It contains only
references, never source bodies, official attestations, or content hashes.
`validate_civil_analysis` resolves every source, evidence, and fact ID against
server-owned run state. A `met` element requires a server-owned normative
source plus an eligible fact or evidence reference.

Temporal applicability, authority status, and legal validity come from the
provider-neutral `alr-tw.legal-context-result/v1` port. The public package
ships an explicit-allowlist synthetic fixture provider only. Unknown,
incomplete, stale, non-binding, or legally invalid normative context fails
closed.

`not_found_in_scope` counter-authority status can only produce a qualification;
the schema fixes `absence_established=false`. It never means that no opposing
view exists.

Civil-analysis validation checks structure and trust invariants. It does not
perform semantic entailment, decide whether difficult legal concepts are
satisfied, or authorize a final answer. Final answer validation remains a
separate server-owned gate.

## Final issue coverage

When a registered plan exists, each `validate_legal_answer.claim_bindings`
entry may include `issue_ids`. Every core issue requiring a conclusion must be
covered by at least one claim binding.

The validation response includes `alr-tw.issue-coverage/v1`:

```json
{
  "mode": "registered_plan",
  "required_core_issue_ids": ["issue-duty"],
  "bound_issue_ids": ["issue-duty"],
  "missing_core_issue_ids": [],
  "unknown_issue_ids": []
}
```

This is explicit issue-to-claim binding coverage, not semantic entailment.
The ordinary evidence, role, polarity, qualifier, time, privacy, and source
eligibility gates still apply. A missing core issue returns
`CORE_RESEARCH_ISSUE_UNBOUND`; an unknown issue reference returns
`CLAIM_BINDING_ISSUE_NOT_IN_PLAN`.

## Recommended universal flow

```text
get_legal_research_capabilities
  -> research_legal_question(discovery_mode=...)
  -> [client_assisted only] submit_legal_research_plan
  -> continue_legal_research until ready_for_draft
  -> [civil-analysis clients] validate_civil_analysis
  -> external client drafts and binds claims to evidence + issues
  -> validate_legal_answer
  -> render only validated / qualified; discard blocked draft
```

An adapter should choose exactly one discovery mode per run. It must not run a
full external recall workflow and a full ALR-TW server-managed workflow in
parallel, then merge their trust states client-side.
