# ALR-TW Agentic Workflow

ALR-TW is an AI-agent-driven, bounded agentic legal RAG harness. It demonstrates
how an AI agent can plan, retrieve, validate, and decide without bypassing source
and citation policy.

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
the trust gate; otherwise the harness refuses or requires human review.

## Scenarios

- `pass_official_source`: final citation exists and the trust gate allows answer.
- `fail_candidate_only`: external semantic recall remains candidate-only.
- `fail_synthetic_only`: synthetic data is demo-only and cannot become final law.
- `fail_verified_cache_incomplete`: verified cache missing required metadata is rejected.
- `fail_no_final_citation`: no final citation produces fail-closed refusal.
- `fail_low_coverage`: low legal coverage blocks final answer.
- `human_review_required_claim_support`: source exists, but claim support was not checked.
