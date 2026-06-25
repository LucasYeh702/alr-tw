from __future__ import annotations

from enum import Enum


class CoverageState(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    NOT_CHECKED = "not_checked"
    LOW_CONFIDENCE = "low_confidence"


def _coerce_state(value: CoverageState | str) -> CoverageState:
    if isinstance(value, CoverageState):
        return value
    return CoverageState(value)


def build_coverage_report(
    *,
    laws: CoverageState | str = CoverageState.NOT_CHECKED,
    judgments: CoverageState | str = CoverageState.NOT_CHECKED,
    constitutional: CoverageState | str = CoverageState.NOT_CHECKED,
    administrative: CoverageState | str = CoverageState.NOT_CHECKED,
    opposing_view: CoverageState | str = CoverageState.NOT_CHECKED,
) -> dict[str, str]:
    return {
        "has_laws": _coerce_state(laws).value,
        "has_judgments": _coerce_state(judgments).value,
        "has_constitutional": _coerce_state(constitutional).value,
        "has_administrative": _coerce_state(administrative).value,
        "has_opposing_view": _coerce_state(opposing_view).value,
    }


def build_stateful_coverage_report(
    *,
    laws: tuple[CoverageState | str, str, int] = (CoverageState.NOT_CHECKED, "", 0),
    judgments: tuple[CoverageState | str, str, int] = (CoverageState.NOT_CHECKED, "", 0),
    constitutional: tuple[CoverageState | str, str, int] = (CoverageState.NOT_CHECKED, "", 0),
    administrative: tuple[CoverageState | str, str, int] = (CoverageState.NOT_CHECKED, "", 0),
    opposing_view: tuple[CoverageState | str, str, int] = (CoverageState.NOT_CHECKED, "", 0),
) -> dict[str, dict[str, str | int]]:
    def item(value: tuple[CoverageState | str, str, int]) -> dict[str, str | int]:
        state, reason, evidence_count = value
        return {
            "state": _coerce_state(state).value,
            "reason": reason,
            "evidence_count": evidence_count,
        }

    return {
        "has_laws": item(laws),
        "has_judgments": item(judgments),
        "has_constitutional": item(constitutional),
        "has_administrative": item(administrative),
        "has_opposing_view": item(opposing_view),
    }
