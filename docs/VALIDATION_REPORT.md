# ALR-TW Validation Report

`build_validation_report()` converts an `AgenticRunTrace` into Markdown for review.

Required sections:

1. Query
2. Normalized Query
3. Tool Plan
4. Retrieved Sources
5. Final Citations
6. Candidate-only Sources
7. Rejected / Unverifiable Sources
8. Coverage
9. Trust Gate Decision
10. Decision Trace
11. Answer Claims
12. Claim Support Review
13. Semantic Hallucination Risk
14. Final Action
15. Human Review Notes

The tool plan must show `execution_mode` so reviewers can distinguish a
deterministic harness record from a live external tool execution log.

Reports are explanatory artifacts. They do not provide legal advice.
