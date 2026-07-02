from alr_tw.harness.execution_graph import StepKind, graph_as_dict, graph_as_markdown


def test_execution_graph_is_bounded_and_deterministic():
    graph = graph_as_dict()
    expected_steps = [step.value for step in StepKind]

    assert graph["steps"] == expected_steps
    assert graph["transitions"] == [
        ("query_understanding", "source_plan"),
        ("source_plan", "retrieval"),
        ("retrieval", "source_classification"),
        ("source_classification", "citation_validation"),
        ("citation_validation", "coverage_gate"),
        ("coverage_gate", "trust_gate"),
        ("trust_gate", "final_decision"),
    ]
    assert len(set(graph["steps"])) == len(graph["steps"])


def test_execution_graph_can_render_markdown():
    rendered = graph_as_markdown()

    assert "QUERY_UNDERSTANDING -> SOURCE_PLAN" in rendered
    assert "TRUST_GATE -> FINAL_DECISION" in rendered

