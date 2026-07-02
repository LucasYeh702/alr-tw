# Legal Research Validation Report

## 1. Query
民法第184條 押金

## 2. Normalized Query
民法第184條 擔保金

## 3. Tool Plan
- query_understanding: success, execution_mode=harness_recorded, trace_kind=deterministic_harness_step
- source_plan: success, execution_mode=harness_recorded, trace_kind=deterministic_harness_step
- retrieval: success, execution_mode=harness_recorded, trace_kind=deterministic_harness_step
- source_classification: success, execution_mode=harness_recorded, trace_kind=deterministic_harness_step
- citation_validation: success, execution_mode=harness_recorded, trace_kind=deterministic_harness_step
- coverage_gate: success, execution_mode=harness_recorded, trace_kind=deterministic_harness_step
- trust_gate: success, execution_mode=harness_recorded, trace_kind=deterministic_harness_step
- final_decision: success, execution_mode=harness_recorded, trace_kind=deterministic_harness_step

## 4. Retrieved Sources
- `official-demo-law-184` (official, allow_final)

## 5. Final Citations
- `official-demo-law-184` (official, exists): Synthetic Civil Code Article 184

## 6. Candidate-only Sources
- None

## 7. Rejected / Unverifiable Sources
- None

## 8. Coverage
- has_laws: low_confidence
- has_judgments: not_checked

## 9. Trust Gate Decision
- safe_to_present: False
- failure_reasons: LAWS_COVERAGE_LOW

## 10. Decision Trace
- {"candidate_count": 1, "final_citation_count": 1, "step": "citation_validation"}
- {"answer_present": false, "failure_reasons": ["LAWS_COVERAGE_LOW"], "final_action": "refuse", "safe_to_present": false, "step": "trust_gate"}

## 11. Final Action
refuse

## 12. Human Review Notes
- None
