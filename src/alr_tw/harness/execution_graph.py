from __future__ import annotations

from enum import Enum


class StepKind(str, Enum):
    QUERY_UNDERSTANDING = "query_understanding"
    SOURCE_PLAN = "source_plan"
    RETRIEVAL = "retrieval"
    SOURCE_CLASSIFICATION = "source_classification"
    CITATION_VALIDATION = "citation_validation"
    COVERAGE_GATE = "coverage_gate"
    TRUST_GATE = "trust_gate"
    FINAL_DECISION = "final_decision"


TRANSITIONS: tuple[tuple[StepKind, StepKind], ...] = (
    (StepKind.QUERY_UNDERSTANDING, StepKind.SOURCE_PLAN),
    (StepKind.SOURCE_PLAN, StepKind.RETRIEVAL),
    (StepKind.RETRIEVAL, StepKind.SOURCE_CLASSIFICATION),
    (StepKind.SOURCE_CLASSIFICATION, StepKind.CITATION_VALIDATION),
    (StepKind.CITATION_VALIDATION, StepKind.COVERAGE_GATE),
    (StepKind.COVERAGE_GATE, StepKind.TRUST_GATE),
    (StepKind.TRUST_GATE, StepKind.FINAL_DECISION),
)


def graph_as_dict() -> dict[str, object]:
    return {
        "schema_version": "alr-tw.execution_graph/v1",
        "steps": [step.value for step in StepKind],
        "transitions": [(source.value, target.value) for source, target in TRANSITIONS],
        "loop_policy": "bounded_no_unrestricted_retry",
    }


def graph_as_markdown() -> str:
    lines = ["# ALR-TW Execution Graph", "", "```text"]
    lines.extend(f"{source.name} -> {target.name}" for source, target in TRANSITIONS)
    lines.append("```")
    return "\n".join(lines)

