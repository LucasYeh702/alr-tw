from alr_tw.harness.orchestrator import run_agentic_demo
from alr_tw.harness.report_builder import build_validation_report


def test_validation_report_contains_required_sections_for_fail_case():
    report = build_validation_report(run_agentic_demo("民法第184條 押金", scenario="fail_candidate_only"))

    for heading in (
        "1. Query",
        "2. Normalized Query",
        "3. Tool Plan",
        "4. Retrieved Sources",
        "5. Final Citations",
        "6. Candidate-only Sources",
        "7. Rejected / Unverifiable Sources",
        "8. Coverage",
        "9. Trust Gate Decision",
        "10. Decision Trace",
        "11. Answer Claims",
        "12. Claim Support Review",
        "13. Semantic Hallucination Risk",
        "14. Final Action",
        "15. Human Review Notes",
    ):
        assert heading in report
    assert "refuse" in report
    assert "NO_FINAL_CITATION" in report
    assert "harness_recorded" in report
    assert "deterministic_harness_step" in report
