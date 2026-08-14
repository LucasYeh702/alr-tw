# ALR-TW Agent-Neutral Interoperability Contract

本文件定義 v0.9.0 的前端無關接口。任何能呼叫 MCP tool 的法律
agent、prompt skill、workflow engine 或人工控制程式都可以使用同一套契約；
核心程式不依賴特定前端專案、模型或提示詞。

## Public scope

ALR-TW is a contract-first, public-safe, agent-neutral and provider-neutral
runtime. It contains public contracts, validators, synthetic fixtures and
trust-boundary tests only; it does not ship production corpus, private paths,
indexes, manifests, operational state, or private evaluation labels. A user
supplies a conforming provider through these public contracts.

The v0.9.0 public surface also includes structural applicability resolution,
authority/judgment-lineage records, public-law material contracts, and a
provider SDK. These are metadata-bound extension points: they describe explicit
source relationships, court/procedure lineage, and administrative or legislative
material roles, but they do not perform semantic entailment or opposition
classification. A deployment must supply the provider and server-owned binding.

The v0.9.0 surface adds an optional semantic-verifier sidecar. It can
return bounded `supports`, `contradicts`, `uncertain`, or `not_evaluated`
relations for server-selected targets, but its output remains advisory-only and
cannot promote evidence, mutate source trust, or authorize finalization or an
answer. The core runtime remains model-free.

The v0.9.0 provider boundary also exposes a common conformance validator and an
optional receipt-aware adapter. A deployer may provide a provider, model, or
corpus outside this repository, but the public package does not bundle them;
server-owned source/evidence promotion and run-bound snapshot receipts remain
the only path to ordinary eligibility.

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

This is the v0.9.0-compatible default. ALR-TW plans and executes its bounded
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

## Unified legal analysis proposal

`alr-tw.legal-analysis/v1` is a multi-branch envelope accepted by
`validate_legal_analysis`. Its `analyses` list may contain these profiles once
each:

| Profile | Structural focus |
|---|---|
| `civil_substantive` | claims, elements, defenses, legal effects and element-level burdens |
| `civil_procedure` | jurisdiction, party capacity, standing, claim subject, procedural prerequisites, burden, res judicata, appeal and provisional relief |
| `criminal_substantive` | offense elements, unlawfulness, culpability, intent or negligence, attempt, participation, concurrence, sentencing |
| `criminal_procedure` | proceeding stage, prosecution prerequisites, coercive measures, admissibility, probative weight, confession, hearsay, burden and remedies |
| `administrative` | `legality` and `remedy` tracks covering action legality and administrative remedies |
| `constitutional_review` | admissibility, protected right, interference, legal reservation, legitimate aim, proportionality, equality, due process and judgment effect |

Each branch declares `complete` or `issue_limited` scope. A `complete` proposal
must include the branch's core dimensions; `issue_limited` always returns a
qualification. Civil claims, elements and burdens preserve the civil-law legal
effect and burden taxonomy. Every normative assessment requires a server-owned
normative source. A determinate `met` or `not_met` assessment also requires a
server-owned fact or eligible evidence reference. Unknown, stale, non-binding,
temporally inapplicable, or legally invalid references fail closed.

The stateless validator accepts an optional `server_fact_states` mapping from a
server-owned fact provider. The bundled managed `ResearchService` does not
persist such fact records and reports
`managed_fact_state_store_available=false`; its MCP path therefore rejects
client-supplied fact IDs. Managed-run clients should bind eligible evidence IDs
unless their deployment integrates the validator with its own server-owned fact
store. Client fact labels can never populate this mapping.

The branch names are checklists for interoperable structure, not codified
legal conclusions. The validator does not determine evidence admissibility or
probative weight, criminal-law three-stage reasoning, administrative
discretion, constitutional proportionality, or any other substantive
subsumption. It always returns `authorizes_final_answer=false` and
`semantic_entailment_performed=false`.

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

## Research sufficiency and finalization

`ready_for_draft` is a workflow-stage marker only. The server recomputes
`ResearchSufficiencyAssessment` from run-owned obligations, Coverage v2 and
provider results; clients cannot provide a sufficiency or answer-mode claim.
Use `get_legal_research_finalization` to obtain the server-owned
`alr-tw.finalization/v1` contract, including `ordinary`, `conditional`, or
`refusal_only` posture, blockers, required qualifications, snapshot receipts,
and blocker/qualification fields. Structured refusal is returned by the answer
validation refusal path, not by this read-only getter. Coverage is bounded to the recorded query/time
scope and provider scope. A clean `not_found_in_scope` is not a global absence
claim. Counter-authority is lexical candidate discovery plus official
verification, not a semantic opposition classifier or a consensus proof.

Snapshot receipts are provider-neutral contracts, not a claim that the bundled
providers issue them. The built-in `ResearchService` does not currently inject
or persist live-provider generation receipts, so built-in live finalization is
at most `conditional`/`qualified`; `ordinary` requires a receipt-aware adapter
with a server-owned receipt binding for the same run. Finalization is
pre-draft (`safe_to_draft`) only; presentation still requires
`validate_legal_answer`.

Synthetic fixtures and legacy traces remain compatibility demonstrations only;
they cannot support a legal answer.

## Recommended universal flow

```text
get_legal_research_capabilities
  -> research_legal_question(discovery_mode=...)
  -> [client_assisted only] submit_legal_research_plan
  -> continue_legal_research until ready_for_draft
  -> get_legal_research_finalization
  -> [optional structured analysis] validate_legal_analysis
  -> external client drafts and binds claims to evidence + issues
  -> validate_legal_answer
  -> render only validated / qualified; discard blocked draft
```

An adapter should choose exactly one discovery mode per run. It must not run a
full external recall workflow and a full ALR-TW server-managed workflow in
parallel, then merge their trust states client-side.
