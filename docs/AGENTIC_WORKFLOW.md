# ALR-TW Agentic Workflow

ALR-TW is a bounded agentic legal RAG harness that constrains an external agent.
This repository does not ship an LLM or agent implementation. Planning, tool
selection, and natural-language reasoning are supplied by the caller, such as an
external MCP client or LLM runtime; ALR-TW provides tool interfaces,
deterministic gate graphs, traces, and report contracts that constrain that
external agent.

```text
Query
  -> Query Understanding
  -> Source Plan
  -> Retrieval
  -> Source Classification
  -> Citation Validation
  -> Coverage Gate
  -> Trust Gate
  -> Final Decision
```

The graph is deterministic. ALR-TW does not implement an unrestricted autonomous
legal agent loop, and it is not an agent that practices law or independently
completes legal judgment. Every final answer must pass citation validation and
the trust gate; otherwise the harness refuses or requires human review. The
trust-gate decision is made by the deterministic harness, not asserted by the
external agent.

Public example traces are deterministic harness traces. Their `tool_calls` use
`execution_mode: "harness_recorded"` and should not be read as live external
tool execution logs.

Clients should render answer content only when `trust_gate.safe_to_present` is
true and `final_action` is `answer`.

## Scenarios

- `pass_official_source`: final citation exists and the trust gate allows answer.
- `fail_candidate_only`: external semantic recall remains candidate-only.
- `fail_synthetic_only`: synthetic data is demo-only and cannot become final law.
- `fail_verified_cache_incomplete`: verified cache missing required metadata is rejected.
- `fail_no_final_citation`: no final citation produces fail-closed refusal.
- `fail_low_coverage`: low legal coverage blocks final answer.
- `human_review_required_claim_support`: source exists, but claim support was not checked.
- `pass_claim_supported`: source exists and claim is supported by legal segments.
- `fail_party_argument_as_court_view`: party-argument segment is misread as court-view.
- `fail_overstated_case_specific_rule`: claim over-generalized a case-specific finding.
- `fail_unsupported_paraphrase`: claim paraphrase does not match supporting segments.
- `human_review_claim_unchecked`: source exists, but claim support was intentionally unchecked.
