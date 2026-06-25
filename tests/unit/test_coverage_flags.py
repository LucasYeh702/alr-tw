from tw_legal_rag_mcp.retrieval.coverage import CoverageState, build_coverage_report


def test_coverage_states_are_strings_not_booleans():
    report = build_coverage_report(
        laws=CoverageState.PRESENT,
        judgments=CoverageState.ABSENT,
        constitutional=CoverageState.NOT_CHECKED,
        administrative=CoverageState.LOW_CONFIDENCE,
    )

    assert all(isinstance(value, str) for value in report.values())
    assert all(not isinstance(value, bool) for value in report.values())


def test_not_checked_is_distinct_from_absent_and_low_confidence_allowed():
    assert CoverageState.NOT_CHECKED != CoverageState.ABSENT
    assert CoverageState.LOW_CONFIDENCE.value == "low_confidence"
