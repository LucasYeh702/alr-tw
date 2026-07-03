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
- has_laws: present
- has_judgments: not_checked

## 9. Trust Gate Decision
- safe_to_present: True
- failure_reasons: none

## 10. Decision Trace
- {"candidate_count": 1, "final_citation_count": 1, "step": "citation_validation"}
- {"claim_count": 1, "failure_reasons": [], "semantic_safe_to_present": true, "step": "claim_support"}
- {"answer_present": true, "failure_reasons": [], "final_action": "answer", "safe_to_present": true, "step": "trust_gate"}

## 11. Answer Claims
- `claim-001` (court_view): 法院認為押金可否返還需依契約約定與事實情節判斷。

## 12. Claim Support Review
- `claim-001`: SupportStatus.SUPPORTED ([]) via `official-demo-law-184-seg-01`

## 13. Semantic Hallucination Risk
- semantic_safe_to_present: True
- supported_count: 1
- unsupported_count: 0
- overstated_count: 0
- role_error_count: 0
- needs_review_count: 0
- failure_reasons: none

## 14. Final Action
answer

## 15. Human Review Notes
- None
