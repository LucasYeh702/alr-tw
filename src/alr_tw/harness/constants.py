from __future__ import annotations

from enum import StrEnum


class FinalAction(StrEnum):
    ANSWER = "answer"
    REFUSE = "refuse"
    HUMAN_REVIEW_REQUIRED = "human_review_required"


class ToolExecutionMode(StrEnum):
    HARNESS_RECORDED = "harness_recorded"
    ACTUAL_TOOL = "actual_tool"


class TrustFailureReason(StrEnum):
    NO_FINAL_CITATION = "NO_FINAL_CITATION"
    REJECTED_CITATION = "REJECTED_CITATION"
    UNVERIFIABLE_CITATION = "UNVERIFIABLE_CITATION"
    LAWS_COVERAGE_LOW = "LAWS_COVERAGE_LOW"
    JUDGMENTS_COVERAGE_LOW = "JUDGMENTS_COVERAGE_LOW"
    CLAIM_SUPPORT_NOT_CHECKED = "CLAIM_SUPPORT_NOT_CHECKED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
