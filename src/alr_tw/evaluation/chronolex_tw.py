"""ChronoLex-TW adapter with fail-closed historical-version scoring.

The adapter deliberately separates untrusted agent trajectories from server-owned
historical-law adjudications.  A model-supplied version date never satisfies
``version_correctness`` on its own.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any, Final, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from alr_tw.contracts.applicability import (
    ApplicabilityStatus,
    ApplicabilityValidationDecision,
    ApplicabilityValidationResult,
)
from alr_tw.contracts.historical_law import HistoricalLawValidationResult
from alr_tw.contracts.public_law import (
    PublicLawMaterialType,
    PublicLawSourceRecord,
    PublicLawSourceRole,
    PublicLawValidationDecision,
)


CHRONOLEX_TW_DATASET_ID: Final[Literal["lianghsun/chronolex-tw"]] = "lianghsun/chronolex-tw"
CHRONOLEX_TW_DATASET_REVISION: Final = "2c9e5e280579209522a23acef7fdeb4b4b61ce94"
CHRONOLEX_TW_SCHEMA: Final[Literal["alr-tw.chronolex-tw-report/v1"]] = (
    "alr-tw.chronolex-tw-report/v1"
)
_MAX_CASES = 10_000
_MAX_JSONL_LINE_BYTES = 2_000_000
_DATASET_FIELD_ORDER = (
    "id",
    "question",
    "A",
    "B",
    "C",
    "D",
    "answer",
    "choices",
    "legal_date",
    "year",
    "gold_law",
    "gold_article",
    "gold_version_date",
    "tau",
    "question_unmasked",
    "subject",
    "exam_level",
    "source_papers",
)
_LAW_ALIASES = {
    "中華民國刑法": "刑法",
    "刑法": "刑法",
}
_ARTICLE_RE = re.compile(
    r"^\s*第?\s*(?P<base>[0-9]+)(?:\s*條)?"
    r"(?P<suffix>(?:\s*(?:之|[-‐‑–—−])\s*[0-9]+)*)"
)
_ARTICLE_REMAINDER_RE = re.compile(r"^(?:第?\s*[0-9]+\s*(?:項|款|目)\s*)*$")


class ChronoLexTau(str, Enum):
    """ChronoLex-TW temporal stratum."""

    SHIFTED = "Shifted"
    STABLE = "Stable"


class ChronoLexAnswer(str, Enum):
    """Official multiple-choice answer labels."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"


class ChronoLexMetricName(str, Enum):
    """Primary metrics requested by the ChronoLex-TW adapter contract."""

    HISTORICAL_ARTICLE_HIT = "historical_article_hit"
    VERSION_CORRECTNESS = "version_correctness"
    FINAL_ANSWER_CORRECTNESS = "final_answer_correctness"


class ChronoLexMetricStatus(str, Enum):
    """Tri-state metric result preserving unavailable version evidence."""

    CORRECT = "correct"
    INCORRECT = "incorrect"
    NOT_SCOREABLE = "not_scoreable"


def normalize_law_name(value: str) -> str:
    """Normalize whitespace and the official/common Criminal Code alias."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError("CHRONOLEX_LAW_NAME_REQUIRED")
    normalized = unicodedata.normalize("NFKC", value)
    normalized = re.sub(r"\s+", "", normalized)
    return _LAW_ALIASES.get(normalized, normalized)


def normalize_article(value: str) -> str:
    """Normalize ``第185條之3`` and ``185-3`` to the dataset form ``185-3``."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError("CHRONOLEX_ARTICLE_REQUIRED")
    normalized = unicodedata.normalize("NFKC", value)
    match = _ARTICLE_RE.match(normalized)
    if match is None:
        raise ValueError("CHRONOLEX_ARTICLE_INVALID")
    remainder = normalized[match.end() :].strip()
    if remainder and _ARTICLE_REMAINDER_RE.fullmatch(remainder) is None:
        raise ValueError("CHRONOLEX_ARTICLE_INVALID")
    suffix = match.group("suffix")
    suffix_numbers = re.findall(r"[0-9]+", suffix)
    return "-".join([match.group("base"), *suffix_numbers])


class ChronoLexAgentInput(BaseModel):
    """Gold-free payload that may be sent to an evaluated agent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.chronolex-agent-input/v1"] = "alr-tw.chronolex-agent-input/v1"
    dataset_id: Literal["lianghsun/chronolex-tw"] = CHRONOLEX_TW_DATASET_ID
    dataset_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    case_key: str = Field(min_length=1, max_length=256)
    source_id: str = Field(min_length=1, max_length=128)
    question: str = Field(min_length=1, max_length=20_000)
    choices: dict[ChronoLexAnswer, str]
    legal_date: date

    @model_validator(mode="after")
    def validate_choices(self) -> ChronoLexAgentInput:
        if set(self.choices) != set(ChronoLexAnswer):
            raise ValueError("CHRONOLEX_CHOICES_INCOMPLETE")
        return self


class ChronoLexCase(BaseModel):
    """One pinned dataset row, including evaluator-only gold fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    row_index: int = Field(ge=0)
    source_id: str = Field(min_length=1, max_length=128)
    question: str = Field(min_length=1, max_length=20_000)
    choices: dict[ChronoLexAnswer, str]
    answer: ChronoLexAnswer
    legal_date: date
    year: int = Field(ge=1900, le=2200)
    gold_law: str = Field(min_length=1, max_length=300)
    gold_article: str = Field(min_length=1, max_length=64)
    gold_version_date: date
    tau: ChronoLexTau
    subject: str = Field(min_length=1, max_length=128)
    exam_level: str = Field(min_length=1, max_length=128)
    source_papers: str = Field(min_length=1, max_length=2000)

    @property
    def case_key(self) -> str:
        """Stable gold-free key; dataset ``id`` is not unique."""

        payload = {
            "source_id": self.source_id,
            "question": self.question,
            "choices": {label.value: self.choices[label] for label in ChronoLexAnswer},
            "legal_date": self.legal_date.isoformat(),
            "year": self.year,
            "subject": self.subject,
            "exam_level": self.exam_level,
            "source_papers": self.source_papers,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"{self.source_id}#{hashlib.sha256(encoded).hexdigest()[:16]}"

    @model_validator(mode="after")
    def validate_case(self) -> ChronoLexCase:
        if set(self.choices) != set(ChronoLexAnswer):
            raise ValueError("CHRONOLEX_CHOICES_INCOMPLETE")
        if self.year != self.legal_date.year:
            raise ValueError("CHRONOLEX_YEAR_DATE_MISMATCH")
        if self.gold_version_date > self.legal_date:
            raise ValueError("CHRONOLEX_GOLD_VERSION_AFTER_LEGAL_DATE")
        normalize_law_name(self.gold_law)
        normalize_article(self.gold_article)
        return self

    @classmethod
    def from_dataset_row(
        cls,
        row: Mapping[str, Any],
        *,
        row_index: int,
    ) -> ChronoLexCase:
        """Parse one exact pinned-revision CSV or Dataset Viewer row."""

        fields = tuple(row)
        if set(fields) != set(_DATASET_FIELD_ORDER):
            missing = sorted(set(_DATASET_FIELD_ORDER) - set(fields))
            extra = sorted(set(fields) - set(_DATASET_FIELD_ORDER))
            raise ValueError(f"CHRONOLEX_DATASET_SCHEMA_MISMATCH:missing={missing};extra={extra}")
        choices_value = row["choices"]
        if isinstance(choices_value, str):
            try:
                parsed_choices = json.loads(choices_value)
            except json.JSONDecodeError as exc:
                raise ValueError("CHRONOLEX_CHOICES_JSON_INVALID") from exc
        else:
            parsed_choices = choices_value
        ordered_choices = [row[label.value] for label in ChronoLexAnswer]
        if not isinstance(parsed_choices, list) or parsed_choices != ordered_choices:
            raise ValueError("CHRONOLEX_CHOICES_MISMATCH")
        if not isinstance(row["question_unmasked"], str) or not row["question_unmasked"]:
            raise ValueError("CHRONOLEX_UNMASKED_REFERENCE_INVALID")
        return cls.model_validate(
            {
                "row_index": row_index,
                "source_id": row["id"],
                "question": row["question"],
                "choices": {label: str(row[label.value]) for label in ChronoLexAnswer},
                "answer": row["answer"],
                "legal_date": row["legal_date"],
                "year": row["year"],
                "gold_law": row["gold_law"],
                "gold_article": row["gold_article"],
                "gold_version_date": row["gold_version_date"],
                "tau": row["tau"],
                "subject": row["subject"],
                "exam_level": row["exam_level"],
                "source_papers": row["source_papers"],
            }
        )

    def agent_input(
        self,
        *,
        dataset_revision: str = CHRONOLEX_TW_DATASET_REVISION,
    ) -> ChronoLexAgentInput:
        """Project a case without gold labels or the unmasked question."""

        return ChronoLexAgentInput(
            dataset_revision=dataset_revision,
            case_key=self.case_key,
            source_id=self.source_id,
            question=self.question,
            choices=dict(self.choices),
            legal_date=self.legal_date,
        )


class ChronoLexToolCall(BaseModel):
    """One untrusted historical-statute lookup in an agent trajectory."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_name: str = Field(default="historical_law_lookup", min_length=1, max_length=128)
    law_name: str = Field(min_length=1, max_length=300)
    article: str = Field(min_length=1, max_length=64)
    as_of_date: date
    lookup_status: str = Field(min_length=1, max_length=128)
    query_text: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_locator(self) -> ChronoLexToolCall:
        normalize_law_name(self.law_name)
        normalize_article(self.article)
        return self


class ChronoLexAgentRun(BaseModel):
    """Untrusted model output and tool-call trajectory for one unique case key."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.chronolex-agent-run/v1"] = "alr-tw.chronolex-agent-run/v1"
    case_key: str = Field(min_length=1, max_length=256)
    tool_calls: list[ChronoLexToolCall] = Field(default_factory=list, max_length=64)
    final_answer: ChronoLexAnswer | None = None
    terminated: bool = True


class ChronoLexAdjudication(BaseModel):
    """Server-side projection tying one selected version to ALR trust gates.

    This object must be built from server results, never copied from the model's
    response.  The evaluator requires both accepted historical-source validation
    and accepted applicability validation before a version date becomes scoreable.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.chronolex-adjudication/v1"] = "alr-tw.chronolex-adjudication/v1"
    case_key: str = Field(min_length=1, max_length=256)
    call_index: int = Field(ge=1, le=64)
    law_name: str = Field(min_length=1, max_length=300)
    article: str = Field(min_length=1, max_length=64)
    as_of_date: date
    source_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    promulgated_on: date
    material_type: PublicLawMaterialType
    source_role: PublicLawSourceRole
    historical_validation: HistoricalLawValidationResult | None = None
    applicability_validation: ApplicabilityValidationResult | None = None

    @model_validator(mode="after")
    def validate_locator(self) -> ChronoLexAdjudication:
        normalize_law_name(self.law_name)
        normalize_article(self.article)
        return self

    @classmethod
    def from_server_results(
        cls,
        *,
        case_key: str,
        call_index: int,
        law_name: str,
        article: str,
        as_of_date: date,
        source: PublicLawSourceRecord,
        historical_validation: HistoricalLawValidationResult,
        applicability_validation: ApplicabilityValidationResult,
    ) -> ChronoLexAdjudication:
        """Create the minimal evaluation projection without copying source text."""

        if source.issued_at is None:
            raise ValueError("CHRONOLEX_SOURCE_PROMULGATION_DATE_REQUIRED")
        return cls(
            case_key=case_key,
            call_index=call_index,
            law_name=law_name,
            article=article,
            as_of_date=as_of_date,
            source_id=source.source_id,
            promulgated_on=source.issued_at.date(),
            material_type=source.material_type,
            source_role=source.source_role,
            historical_validation=historical_validation,
            applicability_validation=applicability_validation,
        )


class ChronoLexMetricOutcome(BaseModel):
    """One auditable metric outcome."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ChronoLexMetricStatus
    value: bool | None
    reason_codes: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_value(self) -> ChronoLexMetricOutcome:
        expected = {
            ChronoLexMetricStatus.CORRECT: True,
            ChronoLexMetricStatus.INCORRECT: False,
            ChronoLexMetricStatus.NOT_SCOREABLE: None,
        }[self.status]
        if self.value is not expected:
            raise ValueError("CHRONOLEX_METRIC_VALUE_STATUS_MISMATCH")
        return self


class ChronoLexCaseScore(BaseModel):
    """Post-run score for one case; it contains no question or answer text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_key: str
    source_id: str
    tau: ChronoLexTau
    historical_article_hit: ChronoLexMetricOutcome
    version_correctness: ChronoLexMetricOutcome
    final_answer_correctness: ChronoLexMetricOutcome
    first_historical_article_hit_call: int | None = Field(default=None, ge=1)
    tool_call_count: int = Field(ge=0, le=64)
    terminated: bool


class ChronoLexMetricSummary(BaseModel):
    """Aggregate score with explicit coverage for tri-state version results."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: ChronoLexMetricName
    total: int = Field(ge=0)
    correct: int = Field(ge=0)
    incorrect: int = Field(ge=0)
    not_scoreable: int = Field(ge=0)
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    scorable_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    coverage: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_counts(self) -> ChronoLexMetricSummary:
        if self.correct + self.incorrect + self.not_scoreable != self.total:
            raise ValueError("CHRONOLEX_METRIC_COUNTS_INVALID")
        return self


class ChronoLexBenchmarkReport(BaseModel):
    """Deterministic report for the three primary ChronoLex-TW metrics."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.chronolex-tw-report/v1"] = CHRONOLEX_TW_SCHEMA
    dataset_id: Literal["lianghsun/chronolex-tw"] = CHRONOLEX_TW_DATASET_ID
    dataset_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    case_count: int = Field(ge=1, le=_MAX_CASES)
    unique_source_id_count: int = Field(ge=1)
    duplicate_source_id_groups: int = Field(ge=0)
    duplicate_source_id_rows: int = Field(ge=0)
    strata_counts: dict[str, int]
    metrics: dict[str, ChronoLexMetricSummary]
    by_tau: dict[str, dict[str, ChronoLexMetricSummary]]
    case_scores: list[ChronoLexCaseScore]
    warnings: list[str] = Field(default_factory=list)


def _outcome(
    status: ChronoLexMetricStatus,
    *reason_codes: str,
) -> ChronoLexMetricOutcome:
    value = {
        ChronoLexMetricStatus.CORRECT: True,
        ChronoLexMetricStatus.INCORRECT: False,
        ChronoLexMetricStatus.NOT_SCOREABLE: None,
    }[status]
    return ChronoLexMetricOutcome(
        status=status,
        value=value,
        reason_codes=list(dict.fromkeys(reason_codes)),
    )


def _same_locator(call: ChronoLexToolCall, case: ChronoLexCase) -> bool:
    return normalize_law_name(call.law_name) == normalize_law_name(
        case.gold_law
    ) and normalize_article(call.article) == normalize_article(case.gold_article)


def _score_article(
    case: ChronoLexCase,
    run: ChronoLexAgentRun | None,
) -> tuple[ChronoLexMetricOutcome, int | None]:
    if run is None:
        return _outcome(ChronoLexMetricStatus.INCORRECT, "CHRONOLEX_RUN_MISSING"), None
    saw_locator_with_wrong_date = False
    for index, call in enumerate(run.tool_calls, start=1):
        if not _same_locator(call, case):
            continue
        if call.as_of_date == case.legal_date:
            return _outcome(ChronoLexMetricStatus.CORRECT), index
        saw_locator_with_wrong_date = True
    reason = (
        "CHRONOLEX_LEGAL_DATE_MISMATCH"
        if saw_locator_with_wrong_date
        else "CHRONOLEX_GOLD_ARTICLE_NOT_QUERIED"
    )
    return _outcome(ChronoLexMetricStatus.INCORRECT, reason), None


def _adjudication_trust_errors(adjudication: ChronoLexAdjudication) -> list[str]:
    errors: list[str] = []
    historical = adjudication.historical_validation
    applicability = adjudication.applicability_validation
    if historical is None:
        errors.append("CHRONOLEX_HISTORICAL_VALIDATION_MISSING")
    elif historical.decision is not PublicLawValidationDecision.ACCEPTED:
        errors.append("CHRONOLEX_HISTORICAL_VALIDATION_NOT_ACCEPTED")
    elif adjudication.source_id not in historical.applicability_source_ids:
        errors.append("CHRONOLEX_SOURCE_NOT_IN_HISTORICAL_VALIDATION")
    if applicability is None:
        errors.append("CHRONOLEX_APPLICABILITY_VALIDATION_MISSING")
    elif (
        applicability.decision is not ApplicabilityValidationDecision.ACCEPTED
        or applicability.status is not ApplicabilityStatus.APPLICABLE
    ):
        errors.append("CHRONOLEX_APPLICABILITY_VALIDATION_NOT_ACCEPTED")
    elif adjudication.source_id not in applicability.selected_source_ids:
        errors.append("CHRONOLEX_SOURCE_NOT_SELECTED_BY_APPLICABILITY")
    if adjudication.material_type is not PublicLawMaterialType.HISTORICAL_STATUTE:
        errors.append("CHRONOLEX_SOURCE_NOT_HISTORICAL_STATUTE")
    if adjudication.source_role is not PublicLawSourceRole.NORMATIVE_RULE:
        errors.append("CHRONOLEX_SOURCE_NOT_NORMATIVE_RULE")
    if adjudication.promulgated_on > adjudication.as_of_date:
        errors.append("CHRONOLEX_PROMULGATION_AFTER_LEGAL_DATE")
    return errors


def _score_version(
    case: ChronoLexCase,
    run: ChronoLexAgentRun | None,
    adjudication: ChronoLexAdjudication | None,
) -> ChronoLexMetricOutcome:
    if run is None:
        return _outcome(ChronoLexMetricStatus.NOT_SCOREABLE, "CHRONOLEX_RUN_MISSING")
    if adjudication is None:
        return _outcome(
            ChronoLexMetricStatus.NOT_SCOREABLE,
            "CHRONOLEX_VERSION_ADJUDICATION_MISSING",
        )
    errors = _adjudication_trust_errors(adjudication)
    if errors:
        return _outcome(ChronoLexMetricStatus.NOT_SCOREABLE, *errors)
    if adjudication.call_index > len(run.tool_calls):
        return _outcome(
            ChronoLexMetricStatus.NOT_SCOREABLE,
            "CHRONOLEX_ADJUDICATION_CALL_MISSING",
        )
    call = run.tool_calls[adjudication.call_index - 1]
    if (
        normalize_law_name(call.law_name) != normalize_law_name(adjudication.law_name)
        or normalize_article(call.article) != normalize_article(adjudication.article)
        or call.as_of_date != adjudication.as_of_date
    ):
        return _outcome(
            ChronoLexMetricStatus.NOT_SCOREABLE,
            "CHRONOLEX_ADJUDICATION_CALL_MISMATCH",
        )
    if not _same_locator(call, case) or adjudication.as_of_date != case.legal_date:
        return _outcome(
            ChronoLexMetricStatus.INCORRECT,
            "CHRONOLEX_VERSION_SCOPE_MISMATCH",
        )
    if adjudication.promulgated_on != case.gold_version_date:
        return _outcome(
            ChronoLexMetricStatus.INCORRECT,
            "CHRONOLEX_VERSION_DATE_MISMATCH",
        )
    return _outcome(ChronoLexMetricStatus.CORRECT)


def _score_answer(
    case: ChronoLexCase,
    run: ChronoLexAgentRun | None,
) -> ChronoLexMetricOutcome:
    if run is None:
        return _outcome(ChronoLexMetricStatus.INCORRECT, "CHRONOLEX_RUN_MISSING")
    if not run.terminated:
        return _outcome(ChronoLexMetricStatus.INCORRECT, "CHRONOLEX_RUN_NOT_TERMINATED")
    if run.final_answer is None:
        return _outcome(ChronoLexMetricStatus.INCORRECT, "CHRONOLEX_FINAL_ANSWER_MISSING")
    if run.final_answer is not case.answer:
        return _outcome(ChronoLexMetricStatus.INCORRECT, "CHRONOLEX_FINAL_ANSWER_MISMATCH")
    return _outcome(ChronoLexMetricStatus.CORRECT)


def _index_unique(values: Sequence[Any], *, label: str) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for value in values:
        key = value.case_key
        if key in output:
            raise ValueError(f"CHRONOLEX_DUPLICATE_{label}:{key}")
        output[key] = value
    return output


def _metric_summary(
    metric: ChronoLexMetricName,
    outcomes: Sequence[ChronoLexMetricOutcome],
) -> ChronoLexMetricSummary:
    counts = Counter(item.status for item in outcomes)
    total = len(outcomes)
    correct = counts[ChronoLexMetricStatus.CORRECT]
    incorrect = counts[ChronoLexMetricStatus.INCORRECT]
    not_scoreable = counts[ChronoLexMetricStatus.NOT_SCOREABLE]
    scorable = correct + incorrect
    return ChronoLexMetricSummary(
        metric=metric,
        total=total,
        correct=correct,
        incorrect=incorrect,
        not_scoreable=not_scoreable,
        score=(correct / total) if total else None,
        scorable_accuracy=(correct / scorable) if scorable else None,
        coverage=(scorable / total) if total else None,
    )


def _summaries(scores: Sequence[ChronoLexCaseScore]) -> dict[str, ChronoLexMetricSummary]:
    fields = {
        ChronoLexMetricName.HISTORICAL_ARTICLE_HIT: "historical_article_hit",
        ChronoLexMetricName.VERSION_CORRECTNESS: "version_correctness",
        ChronoLexMetricName.FINAL_ANSWER_CORRECTNESS: "final_answer_correctness",
    }
    return {
        metric.value: _metric_summary(metric, [getattr(score, field) for score in scores])
        for metric, field in fields.items()
    }


def evaluate_chronolex(
    cases: Sequence[ChronoLexCase],
    runs: Sequence[ChronoLexAgentRun],
    adjudications: Sequence[ChronoLexAdjudication] = (),
    *,
    dataset_revision: str = CHRONOLEX_TW_DATASET_REVISION,
) -> ChronoLexBenchmarkReport:
    """Evaluate one pinned case set without trusting model-supplied version dates."""

    if not cases or len(cases) > _MAX_CASES:
        raise ValueError("CHRONOLEX_CASE_COUNT_INVALID")
    ChronoLexAgentInput(
        dataset_revision=dataset_revision,
        case_key=cases[0].case_key,
        source_id=cases[0].source_id,
        question=cases[0].question,
        choices=dict(cases[0].choices),
        legal_date=cases[0].legal_date,
    )
    case_map = _index_unique(cases, label="CASE_KEY")
    run_map = _index_unique(runs, label="RUN")
    adjudication_map = _index_unique(adjudications, label="ADJUDICATION")
    unknown_runs = sorted(set(run_map) - set(case_map))
    unknown_adjudications = sorted(set(adjudication_map) - set(case_map))
    if unknown_runs:
        raise ValueError(f"CHRONOLEX_UNKNOWN_RUN_CASE:{unknown_runs[0]}")
    if unknown_adjudications:
        raise ValueError(f"CHRONOLEX_UNKNOWN_ADJUDICATION_CASE:{unknown_adjudications[0]}")

    scores: list[ChronoLexCaseScore] = []
    for case in cases:
        run = run_map.get(case.case_key)
        adjudication = adjudication_map.get(case.case_key)
        article, first_hit = _score_article(case, run)
        scores.append(
            ChronoLexCaseScore(
                case_key=case.case_key,
                source_id=case.source_id,
                tau=case.tau,
                historical_article_hit=article,
                version_correctness=_score_version(case, run, adjudication),
                final_answer_correctness=_score_answer(case, run),
                first_historical_article_hit_call=first_hit,
                tool_call_count=len(run.tool_calls) if run is not None else 0,
                terminated=run.terminated if run is not None else False,
            )
        )

    source_counts = Counter(case.source_id for case in cases)
    duplicate_groups = sum(count > 1 for count in source_counts.values())
    duplicate_rows = sum(count - 1 for count in source_counts.values() if count > 1)
    strata_counts = Counter(case.tau.value for case in cases)
    by_tau = {
        tau.value: _summaries([score for score in scores if score.tau is tau])
        for tau in ChronoLexTau
        if strata_counts[tau.value]
    }
    warnings = [
        "CHRONOLEX_LEGAL_DATE_IS_AUGUST_1_PROXY",
        "CHRONOLEX_VERSION_REQUIRES_ACCEPTED_HISTORICAL_AND_APPLICABILITY_VALIDATION",
    ]
    if duplicate_groups:
        warnings.append("CHRONOLEX_DUPLICATE_SOURCE_IDS_DISAMBIGUATED_BY_ROW_FINGERPRINT")
    return ChronoLexBenchmarkReport(
        dataset_revision=dataset_revision,
        case_count=len(cases),
        unique_source_id_count=len(source_counts),
        duplicate_source_id_groups=duplicate_groups,
        duplicate_source_id_rows=duplicate_rows,
        strata_counts=dict(sorted(strata_counts.items())),
        metrics=_summaries(scores),
        by_tau=by_tau,
        case_scores=scores,
        warnings=warnings,
    )


def load_chronolex_csv(path: str | Path) -> list[ChronoLexCase]:
    """Load the exact 18-column ChronoLex-TW CSV without fetching the network."""

    dataset_path = Path(path)
    cases: list[ChronoLexCase] = []
    with dataset_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != _DATASET_FIELD_ORDER:
            raise ValueError("CHRONOLEX_DATASET_SCHEMA_MISMATCH")
        for row_index, row in enumerate(reader):
            if row_index >= _MAX_CASES:
                raise ValueError("CHRONOLEX_CASE_COUNT_INVALID")
            cases.append(ChronoLexCase.from_dataset_row(row, row_index=row_index))
    if not cases:
        raise ValueError("CHRONOLEX_CASE_COUNT_INVALID")
    return cases


_ModelT = TypeVar("_ModelT", bound=BaseModel)


def _load_jsonl(path: str | Path, model: type[_ModelT]) -> list[_ModelT]:
    values: list[_ModelT] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            if len(line.encode("utf-8")) > _MAX_JSONL_LINE_BYTES:
                raise ValueError(f"CHRONOLEX_JSONL_LINE_TOO_LARGE:{line_number}")
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"CHRONOLEX_JSONL_INVALID:{line_number}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"CHRONOLEX_JSONL_OBJECT_REQUIRED:{line_number}")
            values.append(model.model_validate(payload))
            if len(values) > _MAX_CASES:
                raise ValueError("CHRONOLEX_CASE_COUNT_INVALID")
    return values


def load_agent_runs_jsonl(path: str | Path) -> list[ChronoLexAgentRun]:
    """Load untrusted agent trajectories from JSONL."""

    return _load_jsonl(path, ChronoLexAgentRun)


def load_adjudications_jsonl(path: str | Path) -> list[ChronoLexAdjudication]:
    """Load an evaluator-owned server stream; schema parsing is not authentication."""

    return _load_jsonl(path, ChronoLexAdjudication)


class ChronoLexTWAdapter:
    """Small orchestration facade for preparing and scoring ChronoLex-TW."""

    dataset_id = CHRONOLEX_TW_DATASET_ID

    def __init__(self, *, dataset_revision: str = CHRONOLEX_TW_DATASET_REVISION) -> None:
        if re.fullmatch(r"[0-9a-f]{40}", dataset_revision) is None:
            raise ValueError("CHRONOLEX_DATASET_REVISION_INVALID")
        self.dataset_revision = dataset_revision

    def load_cases(self, path: str | Path) -> list[ChronoLexCase]:
        return load_chronolex_csv(path)

    def agent_inputs(
        self,
        cases: Sequence[ChronoLexCase],
    ) -> list[ChronoLexAgentInput]:
        return [case.agent_input(dataset_revision=self.dataset_revision) for case in cases]

    def evaluate(
        self,
        cases: Sequence[ChronoLexCase],
        runs: Sequence[ChronoLexAgentRun],
        adjudications: Sequence[ChronoLexAdjudication] = (),
    ) -> ChronoLexBenchmarkReport:
        return evaluate_chronolex(
            cases,
            runs,
            adjudications,
            dataset_revision=self.dataset_revision,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="alr-tw-chronolex")
    parser.add_argument(
        "--dataset-revision",
        default=CHRONOLEX_TW_DATASET_REVISION,
        help="Pinned 40-character Hugging Face dataset commit",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Emit gold-free agent inputs as JSONL")
    prepare.add_argument("--dataset", required=True)
    score = commands.add_parser("score", help="Score agent runs and server adjudications")
    score.add_argument("--dataset", required=True)
    score.add_argument("--runs", required=True)
    score.add_argument("--adjudications")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        adapter = ChronoLexTWAdapter(dataset_revision=args.dataset_revision)
        cases = adapter.load_cases(args.dataset)
        if args.command == "prepare":
            for item in adapter.agent_inputs(cases):
                print(item.model_dump_json())
            return 0
        runs = load_agent_runs_jsonl(args.runs)
        adjudications = (
            load_adjudications_jsonl(args.adjudications) if args.adjudications is not None else []
        )
        report = adapter.evaluate(cases, runs, adjudications)
    except (OSError, ValueError, ValidationError, csv.Error) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the entry point
    raise SystemExit(main())


__all__ = [
    "CHRONOLEX_TW_DATASET_ID",
    "CHRONOLEX_TW_DATASET_REVISION",
    "ChronoLexAdjudication",
    "ChronoLexAnswer",
    "ChronoLexAgentInput",
    "ChronoLexAgentRun",
    "ChronoLexBenchmarkReport",
    "ChronoLexCase",
    "ChronoLexCaseScore",
    "ChronoLexMetricOutcome",
    "ChronoLexMetricName",
    "ChronoLexMetricSummary",
    "ChronoLexMetricStatus",
    "ChronoLexTWAdapter",
    "ChronoLexTau",
    "ChronoLexToolCall",
    "evaluate_chronolex",
    "load_adjudications_jsonl",
    "load_agent_runs_jsonl",
    "load_chronolex_csv",
    "main",
    "normalize_article",
    "normalize_law_name",
]
