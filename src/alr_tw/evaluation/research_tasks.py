"""Public-safe research-task evaluation helpers for ALR-TW.

The built-in task set is deliberately an authored, unreviewed work item.  It
contains research prompts and evaluation dimensions, never legal gold answers.
The module is self-contained so an installed wheel can export the default
manifest without relying on a checkout or a data-file package rule.

This module records and scores evaluation evidence; it does not invoke an LLM
or a paid provider.  A runner may export the gold-free task inputs, collect two
records per task, import a human review stream, and then produce a report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any, Final, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, model_validator


SCHEMA_MANIFEST: Final = "alr-tw.research-task-manifest/v1"
SCHEMA_AGENT_INPUT: Final = "alr-tw.research-agent-input/v1"
SCHEMA_RUN: Final = "alr-tw.research-eval-run/v1"
SCHEMA_REVIEW: Final = "alr-tw.expert-review/v1"
SCHEMA_REPORT: Final = "alr-tw.research-evaluation-report/v1"
SCHEMA_REVIEW_PROVENANCE: Final = "alr-tw.review-provenance/v1"
MANIFEST_ID: Final = "alr-tw-public-research-tasks-v1"
MANIFEST_AUTHORED_STATUS: Final = "authored_unreviewed"
BUILTIN_TASK_COUNT: Final = 36
_HASH_RE = r"^[0-9a-f]{64}$"
_MAX_TASKS = 200
_MAX_JSONL_BYTES = 32 * 1024 * 1024
_MAX_RESPONSE_CHARS = 2_000_000


class TaskType(str, Enum):
    """The six task families represented once per legal domain."""

    PRECISION_LOOKUP = "precision_lookup"
    QUICK_SIMILAR_CASES = "quick_similar_cases"
    DRAFT_CLAIM_AUDIT = "draft_claim_audit"
    HISTORICAL_AS_OF = "historical_as_of"
    COUNTER_AUTHORITY = "counter_authority"
    ROLE_RESTRICTION = "role_restriction"


class HarnessMode(str, Enum):
    """The only two populations eligible for a fair paired comparison."""

    WITH_HARNESS = "with_harness"
    WITHOUT_HARNESS = "without_harness"


class RunStatus(str, Enum):
    """Collection state for a model run."""

    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class ProvenanceStatus(str, Enum):
    """Declared provenance of an imported review; this is not authentication."""

    UNVERIFIED = "unverified"
    SELF_ATTESTED = "self_attested"
    EXTERNAL_IMPORTED = "external_imported"


class HumanConfirmationStatus(str, Enum):
    """Whether a human has explicitly confirmed an imported review."""

    UNREVIEWED = "unreviewed"
    PENDING = "pending"
    CONFIRMED = "confirmed"


class MetricName(str, Enum):
    """Review dimensions required by the task-evaluation contract."""

    CITATION_ERRORS = "citation_errors"
    MATERIAL_OMISSIONS = "material_omissions"
    FALSE_ACCEPTS = "false_accepts"
    FALSE_REFUSALS = "false_refusals"
    REVIEW_TIME_SECONDS = "review_time_seconds"


class PairStatus(str, Enum):
    """Why a task did or did not enter the paired population."""

    PAIRED = "paired"
    MISSING_WITH_HARNESS = "missing_with_harness"
    MISSING_WITHOUT_HARNESS = "missing_without_harness"
    MODEL_IDENTITY_MISMATCH = "model_identity_mismatch"
    MODEL_CONFIG_MISMATCH = "model_config_mismatch"
    FAILED_OR_CANCELED_RUN = "failed_or_canceled_run"


def _reject_non_finite(value: str) -> None:
    raise ValueError("JSON_NON_FINITE_NUMBER")


def _strict_json_loads(text: str) -> Any:
    """Parse JSON while rejecting duplicate keys and non-finite constants."""

    def object_pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"JSON_DUPLICATE_FIELD:{key}")
            result[key] = value
        return result

    return json.loads(
        text,
        object_pairs_hook=object_pairs_hook,
        parse_constant=_reject_non_finite,
    )


def _json_safe(value: Any, *, path: str = "value") -> None:
    """Reject non-JSON values and NaN/Infinity recursively."""

    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"JSON_NON_FINITE_NUMBER:{path}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _json_safe(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"JSON_OBJECT_KEY_INVALID:{path}")
            _json_safe(item, path=f"{path}.{key}")
        return
    raise ValueError(f"JSON_VALUE_INVALID:{path}")


def _validate_input_constraints(value: dict[str, Any]) -> None:
    """Only project a small typed control surface to the evaluated model.

    An open metadata dictionary could accidentally carry evaluator gold fields.
    Prose still needs human review; this is structural isolation, not a content
    classifier capable of recognizing answers hidden inside the prompt.
    """
    boolean_keys = {
        "public_safe", "official_verification_required",
        "candidate_only_is_not_final_evidence", "bounded_scope_must_be_reported",
        "semantic_entailment_is_not_claimed", "must_state_not_found_scope",
    }
    allowed = boolean_keys | {"task_label", "max_candidate_items", "as_of_date"}
    if set(value) - allowed:
        raise ValueError("RESEARCH_INPUT_CONSTRAINT_FIELD_FORBIDDEN")
    for key, item in value.items():
        if key in boolean_keys and type(item) is not bool:
            raise ValueError("RESEARCH_INPUT_CONSTRAINT_TYPE_INVALID")
        if key == "max_candidate_items" and (type(item) is not int or not 1 <= item <= 20):
            raise ValueError("RESEARCH_INPUT_CONSTRAINT_BUDGET_INVALID")
        if key == "task_label" and (not isinstance(item, str) or not 1 <= len(item) <= 200):
            raise ValueError("RESEARCH_INPUT_CONSTRAINT_LABEL_INVALID")
        if key == "as_of_date":
            if not isinstance(item, str) or len(item) != 10:
                raise ValueError("RESEARCH_INPUT_CONSTRAINT_DATE_INVALID")
            date.fromisoformat(item)


def _canonical_json(value: Any) -> str:
    _json_safe(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class ResearchTask(BaseModel):
    """One public-safe research prompt without a gold answer."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str = Field(min_length=1, max_length=64)
    domain: str = Field(min_length=1, max_length=80)
    task_type: TaskType
    prompt: str = Field(min_length=1, max_length=20_000)
    research_goal: str = Field(min_length=1, max_length=2_000)
    evaluation_focus: list[str] = Field(min_length=1, max_length=16)
    constraints: dict[str, Any] = Field(default_factory=dict)
    authored_status: Literal["authored_unreviewed"] = MANIFEST_AUTHORED_STATUS
    public_safe: Literal[True] = True

    @model_validator(mode="after")
    def validate_task(self) -> ResearchTask:
        if not self.task_id.strip() or not self.domain.strip():
            raise ValueError("RESEARCH_TASK_IDENTIFIER_REQUIRED")
        if not self.prompt.strip() or not self.research_goal.strip():
            raise ValueError("RESEARCH_TASK_TEXT_REQUIRED")
        if len(self.evaluation_focus) != len(set(self.evaluation_focus)):
            raise ValueError("RESEARCH_TASK_EVALUATION_FOCUS_DUPLICATE")
        if any(not item.strip() for item in self.evaluation_focus):
            raise ValueError("RESEARCH_TASK_EVALUATION_FOCUS_INVALID")
        _validate_input_constraints(self.constraints)
        return self

    @property
    def question_hash(self) -> str:
        """Stable digest of the exact prompt sent to a model."""

        return _sha256_text(self.prompt)


class ResearchTaskManifest(BaseModel):
    """Manifest with deterministic identity and no evaluator gold fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.research-task-manifest/v1"] = SCHEMA_MANIFEST
    manifest_id: str = Field(min_length=1, max_length=128)
    authored_status: Literal["authored_unreviewed"] = MANIFEST_AUTHORED_STATUS
    public_safe: Literal[True] = True
    tasks: list[ResearchTask] = Field(min_length=1, max_length=_MAX_TASKS)
    manifest_hash: str | None = Field(default=None, pattern=_HASH_RE)

    @model_validator(mode="after")
    def validate_manifest(self) -> ResearchTaskManifest:
        task_ids = [task.task_id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("RESEARCH_TASK_DUPLICATE_TASK_ID")
        if len({task.authored_status for task in self.tasks}) != 1:
            raise ValueError("RESEARCH_TASK_AUTHORED_STATUS_INVALID")
        if any(not task.public_safe for task in self.tasks):
            raise ValueError("RESEARCH_TASK_PUBLIC_SAFE_REQUIRED")
        return self

    def content_payload(self) -> dict[str, Any]:
        """Return the hash input, excluding a supplied self-referential hash."""

        return self.model_dump(mode="json", exclude={"manifest_hash"}, exclude_none=True)

    def computed_hash(self) -> str:
        return _sha256_json(self.content_payload())

    def payload_with_hash(self) -> dict[str, Any]:
        payload = self.content_payload()
        payload["manifest_hash"] = self.computed_hash()
        return payload


class ResearchAgentInput(BaseModel):
    """Gold-free input that can be exported to an evaluated agent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.research-agent-input/v1"] = SCHEMA_AGENT_INPUT
    manifest_id: str = Field(min_length=1, max_length=128)
    manifest_hash: str = Field(pattern=_HASH_RE)
    task_id: str = Field(min_length=1, max_length=64)
    domain: str = Field(min_length=1, max_length=80)
    task_type: TaskType
    prompt: str = Field(min_length=1, max_length=20_000)
    constraints: dict[str, Any] = Field(default_factory=dict)
    public_safe: Literal[True] = True

    @model_validator(mode="after")
    def validate_input(self) -> ResearchAgentInput:
        _validate_input_constraints(self.constraints)
        return self


class ResearchRun(BaseModel):
    """One untrusted model collection record."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    schema_version: Literal["alr-tw.research-eval-run/v1"] = SCHEMA_RUN
    run_id: str = Field(min_length=1, max_length=160)
    manifest_hash: str = Field(pattern=_HASH_RE)
    task_id: str = Field(min_length=1, max_length=64)
    question_hash: str = Field(pattern=_HASH_RE)
    model_identity: str = Field(min_length=1, max_length=300)
    runtime_config: dict[str, Any] = Field(
        default_factory=dict,
        alias="model_config",
    )
    harness_mode: HarnessMode
    run_status: RunStatus = RunStatus.COMPLETED
    response_text: str | None = Field(default=None, max_length=_MAX_RESPONSE_CHARS)
    run_digest: str | None = Field(default=None, pattern=_HASH_RE)

    @model_validator(mode="after")
    def validate_run(self) -> ResearchRun:
        if not self.run_id.strip() or not self.model_identity.strip():
            raise ValueError("RESEARCH_RUN_IDENTIFIER_REQUIRED")
        _json_safe(self.runtime_config, path="model_config")
        if self.run_status is RunStatus.COMPLETED and self.response_text is None:
            raise ValueError("RESEARCH_RUN_RESPONSE_REQUIRED_FOR_COMPLETED")
        if self.run_digest is not None and self.run_digest != self.evaluated_digest():
            raise ValueError("RESEARCH_RUN_DIGEST_MISMATCH")
        return self

    def config_fingerprint(self) -> str:
        return _sha256_json(self.runtime_config)

    def evaluated_payload(self) -> dict[str, Any]:
        """Return all run content an imported review is allowed to bind."""

        return {
            "schema_version": self.schema_version,
            "manifest_hash": self.manifest_hash,
            "task_id": self.task_id,
            "question_hash": self.question_hash,
            "model_identity": self.model_identity,
            "model_config": self.runtime_config,
            "harness_mode": self.harness_mode.value,
            "run_status": self.run_status.value,
            "response_text": self.response_text,
            "run_id": self.run_id,
        }

    def evaluated_digest(self) -> str:
        """Digest that prevents applying a review to a replaced response."""

        return _sha256_json(self.evaluated_payload())


class ReviewProvenance(BaseModel):
    """Declared import metadata, never an identity or authentication proof."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.review-provenance/v1"] = SCHEMA_REVIEW_PROVENANCE
    provenance_status: ProvenanceStatus
    human_confirmation: HumanConfirmationStatus = HumanConfirmationStatus.UNREVIEWED
    source_ref: str | None = Field(default=None, max_length=2_000)
    reviewer_label: str | None = Field(default=None, max_length=300)

    @property
    def is_accepted_for_scoring(self) -> bool:
        """Use only explicit external+human state; never infer identity."""

        return (
            self.provenance_status is ProvenanceStatus.EXTERNAL_IMPORTED
            and self.human_confirmation is HumanConfirmationStatus.CONFIRMED
            and bool(self.source_ref and self.source_ref.strip())
            and bool(self.reviewer_label and self.reviewer_label.strip())
        )


class ExpertReview(BaseModel):
    """One imported review whose metric values remain optional and auditable."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.expert-review/v1"] = SCHEMA_REVIEW
    review_id: str = Field(min_length=1, max_length=160)
    manifest_hash: str = Field(pattern=_HASH_RE)
    task_id: str = Field(min_length=1, max_length=64)
    run_id: str = Field(min_length=1, max_length=160)
    run_digest: str = Field(pattern=_HASH_RE)
    harness_mode: HarnessMode
    provenance: ReviewProvenance
    citation_errors: StrictInt | None = Field(default=None, ge=0)
    material_omissions: StrictInt | None = Field(default=None, ge=0)
    false_accepts: StrictInt | None = Field(default=None, ge=0)
    false_refusals: StrictInt | None = Field(default=None, ge=0)
    review_time_seconds: StrictFloat | StrictInt | None = Field(default=None, ge=0.0)

    @model_validator(mode="after")
    def validate_review(self) -> ExpertReview:
        if not self.review_id.strip() or not self.run_id.strip():
            raise ValueError("RESEARCH_REVIEW_IDENTIFIER_REQUIRED")
        if self.review_time_seconds is not None and not math.isfinite(self.review_time_seconds):
            raise ValueError("RESEARCH_REVIEW_TIME_NOT_FINITE")
        return self

    @property
    def review_status(self) -> Literal["reviewed", "unreviewed"]:
        return "reviewed" if self.provenance.is_accepted_for_scoring else "unreviewed"

    def metric_value(self, metric: MetricName) -> int | float | None:
        return getattr(self, metric.value)


class RunPair(BaseModel):
    """A model/config/task-identical pair eligible for comparison."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    task_id: str
    manifest_hash: str = Field(pattern=_HASH_RE)
    question_hash: str = Field(pattern=_HASH_RE)
    model_identity: str
    runtime_config: dict[str, Any] = Field(default_factory=dict, alias="model_config")
    with_harness_run_id: str
    without_harness_run_id: str


class PairRejection(BaseModel):
    """Per-task diagnostic retained when a fair pair cannot be formed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    status: PairStatus
    with_harness_run_id: str | None = None
    without_harness_run_id: str | None = None
    reason: str


class PairingResult(BaseModel):
    """Deterministic pairing result and explicit non-pairing diagnostics."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pairs: list[RunPair]
    rejections: list[PairRejection]


class MetricAggregate(BaseModel):
    """Metric summary with population, missingness, and scoreability exposed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: MetricName
    denominator: int = Field(ge=0)
    run_present: int = Field(ge=0)
    review_present: int = Field(ge=0)
    review_missing: int = Field(ge=0)
    unreviewed: int = Field(ge=0)
    metric_missing: int = Field(ge=0)
    scorable: int = Field(ge=0)
    coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    value_sum: float | None = Field(default=None, ge=0.0)
    mean_value: float | None = Field(default=None, ge=0.0)
    nonzero_count: int | None = Field(default=None, ge=0)
    nonzero_rate: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_aggregate(self) -> MetricAggregate:
        if self.run_present > self.denominator:
            raise ValueError("RESEARCH_METRIC_RUN_COUNT_INVALID")
        if self.review_present > self.run_present:
            raise ValueError("RESEARCH_METRIC_REVIEW_COUNT_INVALID")
        if self.review_missing + self.review_present != self.run_present:
            raise ValueError("RESEARCH_METRIC_REVIEW_COVERAGE_INVALID")
        if self.unreviewed > self.review_present:
            raise ValueError("RESEARCH_METRIC_UNREVIEWED_COUNT_INVALID")
        if self.metric_missing + self.scorable != self.review_present - self.unreviewed:
            raise ValueError("RESEARCH_METRIC_SCOREABILITY_INVALID")
        if self.coverage is not None and self.denominator == 0:
            raise ValueError("RESEARCH_METRIC_ZERO_DENOMINATOR_COVERAGE")
        if self.value_sum is not None and not math.isfinite(self.value_sum):
            raise ValueError("RESEARCH_METRIC_VALUE_NOT_FINITE")
        if self.mean_value is not None and not math.isfinite(self.mean_value):
            raise ValueError("RESEARCH_METRIC_MEAN_NOT_FINITE")
        return self


class PairedMetricComparison(BaseModel):
    """Metric comparison calculated only inside the strict paired population."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: MetricName
    denominator: int = Field(ge=0)
    comparable: int = Field(ge=0)
    missing_or_unreviewed: int = Field(ge=0)
    coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    with_harness_mean: float | None = Field(default=None, ge=0.0)
    without_harness_mean: float | None = Field(default=None, ge=0.0)
    delta_without_minus_with: float | None = None

    @model_validator(mode="after")
    def validate_comparison(self) -> PairedMetricComparison:
        if self.comparable + self.missing_or_unreviewed != self.denominator:
            raise ValueError("RESEARCH_PAIRED_COUNTS_INVALID")
        if self.coverage is not None and self.denominator == 0:
            raise ValueError("RESEARCH_PAIRED_ZERO_DENOMINATOR_COVERAGE")
        for value in (
            self.with_harness_mean,
            self.without_harness_mean,
            self.delta_without_minus_with,
        ):
            if value is not None and not math.isfinite(value):
                raise ValueError("RESEARCH_PAIRED_VALUE_NOT_FINITE")
        return self


class TaskCoverage(BaseModel):
    """Per-task availability and review state for audit output."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    with_harness_run_id: str | None = None
    without_harness_run_id: str | None = None
    with_harness_review_status: Literal["reviewed", "unreviewed", "missing"]
    without_harness_review_status: Literal["reviewed", "unreviewed", "missing"]
    pair_status: PairStatus


class ResearchEvaluationReport(BaseModel):
    """Report that never converts absent or unreviewed data into zero errors."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.research-evaluation-report/v1"] = SCHEMA_REPORT
    manifest_id: str
    manifest_hash: str = Field(pattern=_HASH_RE)
    task_count: int = Field(ge=1)
    expected_run_count: int = Field(ge=0)
    run_count: int = Field(ge=0)
    missing_run_count: int = Field(ge=0)
    failed_or_canceled_run_count: int = Field(ge=0)
    completed_run_count: int = Field(ge=0)
    paired_task_count: int = Field(ge=0)
    pair_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    unpaired_run_count: int = Field(ge=0)
    pairing: PairingResult
    task_coverage: list[TaskCoverage]
    metrics_by_harness: dict[str, list[MetricAggregate]]
    paired_metrics: list[PairedMetricComparison]
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_report(self) -> ResearchEvaluationReport:
        if self.expected_run_count != self.task_count * 2:
            raise ValueError("RESEARCH_REPORT_EXPECTED_RUN_COUNT_INVALID")
        if self.run_count + self.missing_run_count != self.expected_run_count:
            raise ValueError("RESEARCH_REPORT_RUN_COVERAGE_INVALID")
        if self.completed_run_count + self.failed_or_canceled_run_count != self.run_count:
            raise ValueError("RESEARCH_REPORT_RUN_STATUS_COUNTS_INVALID")
        if self.paired_task_count > self.task_count:
            raise ValueError("RESEARCH_REPORT_PAIR_COUNT_INVALID")
        if self.pair_coverage is not None and self.task_count == 0:
            raise ValueError("RESEARCH_REPORT_ZERO_TASK_DENOMINATOR")
        return self


def _task(
    task_id: str,
    domain: str,
    task_type: TaskType,
    prompt: str,
    goal: str,
    focus: Sequence[str],
    constraints: Mapping[str, Any],
) -> ResearchTask:
    return ResearchTask(
        task_id=task_id,
        domain=domain,
        task_type=task_type,
        prompt=prompt,
        research_goal=goal,
        evaluation_focus=list(focus),
        constraints=dict(constraints),
    )


_DOMAIN_TASKS: Final[tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...]] = (
    (
        "民法",
        (
            "精確法源核對",
            "有限類案搜尋",
            "合成草稿核查",
            "指定日期版本",
            "限制與反面材料",
            "合成角色辨認",
        ),
        (
            "核對現行民法第184條全文、條號及官方來源。只說明原文明示的規範內容；不得推論任何未提供事實的個案成立侵權責任。",
            "請找消費者定型化契約中免責條款效力的民事類案，最多三件。逐件確認正式案號、官方原文與法院理由，說明有限搜尋範圍。",
            "核查以下合成待核草稿（不是法律真值）：「依民法第184條，只要他人受有損害，行為人就一律負賠償責任，不必再檢查其他要件。」逐項核對法條與主張；缺少證據綁定時，不得授權呈現原草稿。",
            "以2000-01-01為法律適用日期，查核當時民法第184條的有效版本與版本依據。找不到已核實的歷史版本時，請明示限制，不得用現行條文補作歷史證據。",
            "就「契約自由是否足以使所有消費者定型化契約免責條款有效」，查找限制條件或不同法院見解的官方材料，最多三件；查無結果不得宣稱實務一致。",
            "以下均為合成角色測試材料、不是官方裁判：【當事人主張】被告稱免責條款有效。【本院理由】本院認為仍須審查條款內容。【主文】原告之訴駁回。請區分三段角色，指出哪些不能互相替代；不得由主文自行推導免責條款有效。",
        ),
    ),
    (
        "民事程序",
        (
            "精確法源核對",
            "有限類案搜尋",
            "合成草稿核查",
            "指定日期版本",
            "限制與反面材料",
            "合成角色辨認",
        ),
        (
            "核對現行民事訴訟法第277條全文與官方來源，區分原則及條文中的例外；不判斷未提供案情的舉證責任分配。",
            "請找涉及民事訴訟法第277條舉證責任分配的裁判，最多三件。核對正式案號、官方正文及法院自身理由，保留搜尋範圍限制。",
            "核查以下合成待核草稿（不是法律真值）：「依民事訴訟法第277條，原告在所有情況都負全部舉證責任，絕無例外。」核對官方條文，列出草稿待補的限定；未綁定證據不得放行。",
            "以2010-01-01為法律適用日期，查核當時民事訴訟法第277條版本及版本來源。缺少歷史版本證據時，只回報查證缺口。",
            "就「民事訴訟的舉證責任分配是否一概由原告負擔」，查找官方條文例外與不同適用情境的裁判，最多三件；不得把不同案情直接稱為法院見解衝突。",
            "以下均為合成角色測試材料：【上訴人主張】原審舉證責任分配錯誤。【本院理由】上訴未具體指摘違背法令。【主文】上訴駁回。請區分程序處理與實體見解；沒有官方來源時不得建立正式裁判證據。",
        ),
    ),
    (
        "刑法",
        (
            "精確法源核對",
            "有限類案搜尋",
            "合成草稿核查",
            "指定日期版本",
            "限制與反面材料",
            "合成角色辨認",
        ),
        (
            "核對現行刑法第19條全文與官方來源，區分條文各項及其條件；不得對沒有案情與證據的被告作責任能力判斷。",
            "請找討論刑法第19條責任能力的刑事裁判，最多三件。核對案號、官方原文與法院理由，不得將鑑定意見自動視為法院判斷。",
            "核查以下合成待核草稿（不是法律真值）：「依刑法第19條，只要有精神疾病診斷就一律不罰，不必檢查行為時的能力。」逐項核對官方條文與引用範圍，不對任何真實個案作結論。",
            "以2011-12-01為法律適用日期，查核當時刑法第185條之3的條文版本及施行依據；不得以今天的版本回答。無法核實時請列出缺口。",
            "就「精神疾病診斷是否足以單獨決定刑法第19條適用」，找官方條文與可取得裁判中的限制材料，最多三件，區分鑑定、當事人主張與法院理由。",
            "以下均為合成角色測試材料：【鑑定摘要】受鑑定人有精神疾病。【辯護人主張】應不罰。【本院理由】仍須判斷行為時之能力。請區分角色，不得把診斷或辯護主張當成本院已決定不罰。",
        ),
    ),
    (
        "刑事程序",
        (
            "精確法源核對",
            "有限類案搜尋",
            "合成草稿核查",
            "指定日期版本",
            "限制與反面材料",
            "合成角色辨認",
        ),
        (
            "核對現行刑事訴訟法第159條全文及官方來源，保留條文規則與例外；不判斷任何具體證據是否可採。",
            "請找討論刑事訴訟法第159條傳聞證據問題的裁判，最多三件；核對官方正文並區分檢察官主張與法院理由。",
            "核查以下合成待核草稿（不是法律真值）：「依刑事訴訟法第159條，所有被告以外之人於審判外的陳述永遠不得作為證據，沒有任何例外。」核對引用與限定，缺證據不得放行。",
            "以2010-01-01為法律適用日期，查核當時刑事訴訟法第159條版本及有效時點。找不到已驗證版本，不得拿現行版本替代。",
            "就「審判外陳述是否必然沒有證據能力」，查找官方規範及裁判中的例外或限制情境，最多三件；區分證據能力與證明力，並揭露未查完的範圍。",
            "以下均為合成角色測試材料：【檢察官主張】證人陳述可採。【辯護人主張】屬傳聞證據。【本院理由】應先釐清陳述形成方式。請區分主張與法院判斷；不得推論法院已承認證據能力。",
        ),
    ),
    (
        "行政法",
        (
            "精確法源核對",
            "有限類案搜尋",
            "合成草稿核查",
            "指定日期版本",
            "限制與反面材料",
            "合成角色辨認",
        ),
        (
            "核對現行行政程序法第117條全文及官方來源，區分撤銷權限與條文限制；不推論未提供案情的行政處分必須撤銷。",
            "請找討論行政程序法第117條違法行政處分撤銷的裁判，最多三件，核對正式案號與官方理由，說明個案適用範圍。",
            "核查以下合成待核草稿（不是法律真值）：「依行政程序法第117條，違法行政處分無論情況如何均必須撤銷，完全不須考慮條文限制。」核對官方條文與主張支持；不得將草稿自述當成證據。",
            "以2015-01-01為法律適用日期，查核當時行政程序法第117條版本及來源，分開公布與施行資訊。缺少時間證據時請明示。",
            "就「違法授益行政處分是否一律可以撤銷」，找官方條文與信賴保護限制的相關裁判，最多三件；不得只因結果不同就認定見解矛盾。",
            "以下均為合成角色測試材料：【機關答辯】處分合法。【原告主張】應撤銷處分。【本院理由】本件起訴逾期。【主文】原告之訴駁回。請說明角色及程序、實體的區別，不得推論法院已肯認處分實體合法。",
        ),
    ),
    (
        "憲法審查",
        (
            "精確法源核對",
            "有限類案搜尋",
            "合成草稿核查",
            "指定日期版本",
            "限制與反面材料",
            "合成角色辨認",
        ),
        (
            "核對中華民國憲法第7條全文及官方來源，保留條文字面範圍；不替未提供事實的差別待遇作合憲判斷。",
            "請找憲法法庭或司法院解釋中討論平等原則與差別待遇的資料，最多三件。核對官方識別碼，區分主文、多數理由及個別意見。",
            "核查以下合成待核草稿（不是法律真值）：「依憲法第7條，任何不同待遇都當然違憲；任一大法官不同意見都等同有拘束力的判決主文。」逐項核對官方來源與角色，不得以個別意見代替多數理由。",
            "以2020-01-01為法律適用日期，核對當時憲法第7條的版本及可核實的來源時點。沒有時點證據時請明示，不得以現行網頁時間作歷史版本證明。",
            "就「平等原則是否禁止所有差別待遇」，找官方憲法裁判或解釋中的限制、審查條件與不同意見材料，最多三件；保留多數與個別意見的角色差異。",
            "以下均為合成角色測試材料：【主文】聲請不受理。【不同意見】本席認為應受理並進行實體審查。【聲請人主張】系爭規定違憲。請逐段辨認角色，指出能否由這些材料宣稱法院已宣告違憲；合成文字不得冒充官方證據。",
        ),
    ),
)

_COMMON_CONSTRAINTS: Final[dict[str, Any]] = {
    "public_safe": True,
    "official_verification_required": True,
    "candidate_only_is_not_final_evidence": True,
    "bounded_scope_must_be_reported": True,
    "semantic_entailment_is_not_claimed": True,
}


def _build_builtin_tasks() -> tuple[ResearchTask, ...]:
    tasks: list[ResearchTask] = []
    for domain_index, (domain, labels, prompts) in enumerate(_DOMAIN_TASKS, start=1):
        for task_index, (label, task_type, prompt) in enumerate(
            zip(
                labels,
                tuple(TaskType),
                prompts,
                strict=True,
            ),
            start=1,
        ):
            focus: tuple[str, ...] = (
                "official_source_identity",
                "evidence_role_separation",
                "coverage_and_limitations",
            )
            if task_type is TaskType.PRECISION_LOOKUP:
                focus = (*focus, "exact_locator_check")
            elif task_type is TaskType.QUICK_SIMILAR_CASES:
                focus = (*focus, "bounded_candidate_recall")
            elif task_type is TaskType.DRAFT_CLAIM_AUDIT:
                focus = (*focus, "claim_level_audit")
            elif task_type is TaskType.HISTORICAL_AS_OF:
                focus = (*focus, "historical_version_check")
            elif task_type is TaskType.COUNTER_AUTHORITY:
                focus = (*focus, "counter_authority_scope")
            else:
                focus = (*focus, "judgment_role_check")
            constraints = dict(_COMMON_CONSTRAINTS)
            constraints.update(
                {
                    "task_label": label,
                    "max_candidate_items": 5 if task_type is not TaskType.PRECISION_LOOKUP else 8,
                    "must_state_not_found_scope": task_type
                    in {TaskType.QUICK_SIMILAR_CASES, TaskType.COUNTER_AUTHORITY},
                }
            )
            tasks.append(
                _task(
                    f"RT-{domain_index:02d}-{task_index:02d}",
                    domain,
                    task_type,
                    prompt,
                    f"以{domain}的公開安全研究情境，完成「{label}」並留下可供人工複核的來源與限制紀錄。",
                    focus,
                    constraints,
                )
            )
    return tuple(tasks)


_BUILTIN_TASKS: Final[tuple[ResearchTask, ...]] = _build_builtin_tasks()
_BUILTIN_MANIFEST: Final[ResearchTaskManifest] = ResearchTaskManifest(
    manifest_id=MANIFEST_ID,
    tasks=list(_BUILTIN_TASKS),
)


def default_manifest() -> ResearchTaskManifest:
    """Return a defensive copy of the installed 36-task authored manifest."""

    return _BUILTIN_MANIFEST.model_copy(deep=True)


def load_task_manifest(path: str | Path) -> ResearchTaskManifest:
    """Load an explicit manifest and verify an optional supplied hash."""

    manifest_path = Path(path).expanduser()
    if not manifest_path.is_file():
        raise ValueError("RESEARCH_TASK_MANIFEST_FILE_REQUIRED")
    if manifest_path.stat().st_size > _MAX_JSONL_BYTES:
        raise ValueError("RESEARCH_TASK_MANIFEST_TOO_LARGE")
    try:
        payload = _strict_json_loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"RESEARCH_TASK_MANIFEST_JSON_INVALID:{exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("RESEARCH_TASK_MANIFEST_OBJECT_REQUIRED")
    manifest = ResearchTaskManifest.model_validate(payload)
    if manifest.manifest_hash is not None and manifest.manifest_hash != manifest.computed_hash():
        raise ValueError("RESEARCH_TASK_MANIFEST_HASH_MISMATCH")
    return manifest


def manifest_hash(manifest: ResearchTaskManifest) -> str:
    """Return the deterministic identity used by runs and review imports."""

    return manifest.computed_hash()


def export_agent_inputs(manifest: ResearchTaskManifest) -> list[ResearchAgentInput]:
    """Project tasks to an input schema that contains no gold fields."""

    digest = manifest.computed_hash()
    return [
        ResearchAgentInput(
            manifest_id=manifest.manifest_id,
            manifest_hash=digest,
            task_id=task.task_id,
            domain=task.domain,
            task_type=task.task_type,
            prompt=task.prompt,
            constraints=task.constraints,
        )
        for task in manifest.tasks
    ]


def _model_payload(model: BaseModel, *, by_alias: bool = False) -> dict[str, Any]:
    return model.model_dump(mode="json", by_alias=by_alias, exclude_none=True)


def _write_text_or_stdout(path: str | Path | None, text: str) -> None:
    if path is None or str(path) == "-":
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
        return
    try:
        Path(path).expanduser().write_text(text, encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"RESEARCH_EVALUATION_OUTPUT_WRITE_FAILED:{exc}") from exc


def _write_jsonl_or_stdout(path: str | Path | None, models: Iterable[BaseModel]) -> None:
    lines = [
        json.dumps(
            _model_payload(model, by_alias=True),
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )
        for model in models
    ]
    _write_text_or_stdout(path, "\n".join(lines) + ("\n" if lines else ""))


_ModelT = TypeVar("_ModelT", bound=BaseModel)


def load_jsonl(path: str | Path, model: type[_ModelT]) -> list[_ModelT]:
    """Load strict JSONL for runs or review imports."""

    input_path = Path(path).expanduser()
    if not input_path.is_file():
        raise ValueError("RESEARCH_EVALUATION_INPUT_FILE_REQUIRED")
    if input_path.stat().st_size > _MAX_JSONL_BYTES:
        raise ValueError("RESEARCH_EVALUATION_INPUT_TOO_LARGE")
    values: list[_ModelT] = []
    try:
        lines = input_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"RESEARCH_EVALUATION_INPUT_READ_FAILED:{exc}") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            payload = _strict_json_loads(line)
            if not isinstance(payload, dict):
                raise ValueError("JSON_OBJECT_REQUIRED")
            values.append(model.model_validate(payload))
        except Exception as exc:
            if isinstance(exc, ValueError) and str(exc).startswith("RESEARCH_"):
                raise ValueError(f"RESEARCH_EVALUATION_LINE_{line_number}:{exc}") from exc
            raise ValueError(f"RESEARCH_EVALUATION_LINE_{line_number}:INVALID:{exc}") from exc
    return values


def _task_map(manifest: ResearchTaskManifest) -> dict[str, ResearchTask]:
    return {task.task_id: task for task in manifest.tasks}


def _validate_runs(manifest: ResearchTaskManifest, runs: Sequence[ResearchRun]) -> None:
    expected_hash = manifest.computed_hash()
    tasks = _task_map(manifest)
    seen_ids: set[str] = set()
    seen_slots: set[tuple[str, HarnessMode]] = set()
    for run in runs:
        if run.run_id in seen_ids:
            raise ValueError(f"RESEARCH_RUN_DUPLICATE_RUN_ID:{run.run_id}")
        seen_ids.add(run.run_id)
        if run.manifest_hash != expected_hash:
            raise ValueError(f"RESEARCH_RUN_MANIFEST_HASH_MISMATCH:{run.run_id}")
        task = tasks.get(run.task_id)
        if task is None:
            raise ValueError(f"RESEARCH_RUN_UNKNOWN_TASK:{run.task_id}")
        if run.question_hash != task.question_hash:
            raise ValueError(f"RESEARCH_RUN_QUESTION_HASH_MISMATCH:{run.run_id}")
        slot = (run.task_id, run.harness_mode)
        if slot in seen_slots:
            raise ValueError(
                f"RESEARCH_RUN_DUPLICATE_TASK_MODE:{run.task_id}:{run.harness_mode.value}"
            )
        seen_slots.add(slot)


def _validate_reviews(
    manifest: ResearchTaskManifest,
    runs: Sequence[ResearchRun],
    reviews: Sequence[ExpertReview],
) -> dict[str, ExpertReview]:
    expected_hash = manifest.computed_hash()
    run_map = {run.run_id: run for run in runs}
    seen_review_ids: set[str] = set()
    seen_run_ids: set[str] = set()
    for review in reviews:
        if review.review_id in seen_review_ids:
            raise ValueError(f"RESEARCH_REVIEW_DUPLICATE_REVIEW_ID:{review.review_id}")
        seen_review_ids.add(review.review_id)
        if review.run_id in seen_run_ids:
            raise ValueError(f"RESEARCH_REVIEW_DUPLICATE_RUN_REVIEW:{review.run_id}")
        seen_run_ids.add(review.run_id)
        if review.manifest_hash != expected_hash:
            raise ValueError(f"RESEARCH_REVIEW_MANIFEST_HASH_MISMATCH:{review.review_id}")
        run = run_map.get(review.run_id)
        if run is None:
            raise ValueError(f"RESEARCH_REVIEW_UNKNOWN_RUN:{review.run_id}")
        if review.task_id != run.task_id or review.harness_mode is not run.harness_mode:
            raise ValueError(f"RESEARCH_REVIEW_CASE_MISMATCH:{review.review_id}")
        if review.run_digest != run.evaluated_digest():
            raise ValueError(f"RESEARCH_REVIEW_RUN_DIGEST_MISMATCH:{review.review_id}")
    return {review.run_id: review for review in reviews}


def pair_runs(manifest: ResearchTaskManifest, runs: Sequence[ResearchRun]) -> PairingResult:
    """Pair only exact task/manifest/question/model/config matches.

    A model identity or configuration mismatch remains an explicit rejection;
    it is never silently paired by task id alone.
    """

    _validate_runs(manifest, runs)
    by_slot = {(run.task_id, run.harness_mode): run for run in runs}
    pairs: list[RunPair] = []
    rejections: list[PairRejection] = []
    for task in manifest.tasks:
        with_run = by_slot.get((task.task_id, HarnessMode.WITH_HARNESS))
        without_run = by_slot.get((task.task_id, HarnessMode.WITHOUT_HARNESS))
        if with_run is None:
            rejections.append(
                PairRejection(
                    task_id=task.task_id,
                    status=PairStatus.MISSING_WITH_HARNESS,
                    without_harness_run_id=without_run.run_id if without_run else None,
                    reason="missing with_harness run",
                )
            )
            continue
        if without_run is None:
            rejections.append(
                PairRejection(
                    task_id=task.task_id,
                    status=PairStatus.MISSING_WITHOUT_HARNESS,
                    with_harness_run_id=with_run.run_id,
                    reason="missing without_harness run",
                )
            )
            continue
        if (
            with_run.run_status is not RunStatus.COMPLETED
            or without_run.run_status is not RunStatus.COMPLETED
        ):
            rejections.append(
                PairRejection(
                    task_id=task.task_id,
                    status=PairStatus.FAILED_OR_CANCELED_RUN,
                    with_harness_run_id=with_run.run_id,
                    without_harness_run_id=without_run.run_id,
                    reason="failed or canceled runs cannot enter completed paired accuracy",
                )
            )
            continue
        if with_run.model_identity != without_run.model_identity:
            rejections.append(
                PairRejection(
                    task_id=task.task_id,
                    status=PairStatus.MODEL_IDENTITY_MISMATCH,
                    with_harness_run_id=with_run.run_id,
                    without_harness_run_id=without_run.run_id,
                    reason="model identity must be identical for a pair",
                )
            )
            continue
        if with_run.config_fingerprint() != without_run.config_fingerprint():
            rejections.append(
                PairRejection(
                    task_id=task.task_id,
                    status=PairStatus.MODEL_CONFIG_MISMATCH,
                    with_harness_run_id=with_run.run_id,
                    without_harness_run_id=without_run.run_id,
                    reason="model configuration must be identical for a pair",
                )
            )
            continue
        pairs.append(
            RunPair(
                task_id=task.task_id,
                manifest_hash=with_run.manifest_hash,
                question_hash=with_run.question_hash,
                model_identity=with_run.model_identity,
                model_config=with_run.runtime_config,
                with_harness_run_id=with_run.run_id,
                without_harness_run_id=without_run.run_id,
            )
        )
    return PairingResult(pairs=pairs, rejections=rejections)


def _review_state(
    run: ResearchRun | None,
    review: ExpertReview | None,
) -> Literal["reviewed", "unreviewed", "missing"]:
    if run is None:
        return "missing"
    if review is None or review.review_status != "reviewed":
        return "unreviewed"
    return "reviewed"


def _aggregate_metric(
    metric: MetricName,
    task_count: int,
    runs: Sequence[ResearchRun],
    reviews: Mapping[str, ExpertReview],
) -> MetricAggregate:
    review_present = 0
    accepted_reviews: list[ExpertReview] = []
    metric_values: list[float] = []
    for run in runs:
        review = reviews.get(run.run_id)
        if review is None:
            continue
        review_present += 1
        if review.review_status == "reviewed":
            value = review.metric_value(metric)
            if value is not None:
                accepted_reviews.append(review)
                metric_values.append(float(value))
    run_present = len(runs)
    review_missing = run_present - review_present
    unreviewed = sum(
        1
        for run in runs
        if run.run_id in reviews and reviews[run.run_id].review_status != "reviewed"
    )
    scorable = len(metric_values)
    metric_missing = review_present - unreviewed - scorable
    value_sum = sum(metric_values) if metric_values else None
    mean_value = statistics.fmean(metric_values) if metric_values else None
    nonzero_count: int | None = None
    nonzero_rate: float | None = None
    if metric is not MetricName.REVIEW_TIME_SECONDS:
        nonzero_count = sum(1 for value in metric_values if value > 0)
        nonzero_rate = (nonzero_count / scorable) if scorable else None
    return MetricAggregate(
        metric=metric,
        denominator=task_count,
        run_present=run_present,
        review_present=review_present,
        review_missing=review_missing,
        unreviewed=unreviewed,
        metric_missing=metric_missing,
        scorable=scorable,
        coverage=(scorable / task_count) if task_count else None,
        value_sum=value_sum,
        mean_value=mean_value,
        nonzero_count=nonzero_count,
        nonzero_rate=nonzero_rate,
    )


def _paired_metric(
    metric: MetricName,
    pairs: Sequence[RunPair],
    reviews: Mapping[str, ExpertReview],
) -> PairedMetricComparison:
    with_values: list[float] = []
    without_values: list[float] = []
    for pair in pairs:
        with_review = reviews.get(pair.with_harness_run_id)
        without_review = reviews.get(pair.without_harness_run_id)
        if (
            with_review is None
            or without_review is None
            or with_review.review_status != "reviewed"
            or without_review.review_status != "reviewed"
        ):
            continue
        with_value = with_review.metric_value(metric)
        without_value = without_review.metric_value(metric)
        if with_value is None or without_value is None:
            continue
        with_values.append(float(with_value))
        without_values.append(float(without_value))
    comparable = len(with_values)
    denominator = len(pairs)
    with_mean = statistics.fmean(with_values) if with_values else None
    without_mean = statistics.fmean(without_values) if without_values else None
    delta = (
        (without_mean - with_mean) if with_mean is not None and without_mean is not None else None
    )
    return PairedMetricComparison(
        metric=metric,
        denominator=denominator,
        comparable=comparable,
        missing_or_unreviewed=denominator - comparable,
        coverage=(comparable / denominator) if denominator else None,
        with_harness_mean=with_mean,
        without_harness_mean=without_mean,
        delta_without_minus_with=delta,
    )


def score_evaluation(
    manifest: ResearchTaskManifest,
    runs: Sequence[ResearchRun],
    reviews: Sequence[ExpertReview] = (),
) -> ResearchEvaluationReport:
    """Score imported reviews with explicit missingness and paired coverage."""

    _validate_runs(manifest, runs)
    review_map = _validate_reviews(manifest, runs, reviews)
    pairing = pair_runs(manifest, runs)
    expected_run_count = len(manifest.tasks) * 2
    missing_run_count = expected_run_count - len(runs)
    failed_or_canceled_run_count = sum(run.run_status is not RunStatus.COMPLETED for run in runs)
    unpaired_run_ids = {
        run_id
        for rejection in pairing.rejections
        for run_id in (rejection.with_harness_run_id, rejection.without_harness_run_id)
        if run_id is not None
    }
    task_coverage: list[TaskCoverage] = []
    by_slot = {(run.task_id, run.harness_mode): run for run in runs}
    for task in manifest.tasks:
        with_run = by_slot.get((task.task_id, HarnessMode.WITH_HARNESS))
        without_run = by_slot.get((task.task_id, HarnessMode.WITHOUT_HARNESS))
        rejection = next(
            (item for item in pairing.rejections if item.task_id == task.task_id),
            None,
        )
        task_coverage.append(
            TaskCoverage(
                task_id=task.task_id,
                with_harness_run_id=with_run.run_id if with_run else None,
                without_harness_run_id=without_run.run_id if without_run else None,
                with_harness_review_status=_review_state(
                    with_run,
                    review_map.get(with_run.run_id) if with_run else None,
                ),
                without_harness_review_status=_review_state(
                    without_run,
                    review_map.get(without_run.run_id) if without_run else None,
                ),
                pair_status=PairStatus.PAIRED if rejection is None else rejection.status,
            )
        )
    metrics_by_harness = {
        mode.value: [
            _aggregate_metric(
                metric,
                len(manifest.tasks),
                [run for run in runs if run.harness_mode is mode],
                review_map,
            )
            for metric in MetricName
        ]
        for mode in HarnessMode
    }
    paired_metrics = [_paired_metric(metric, pairing.pairs, review_map) for metric in MetricName]
    warnings = [
        "RESEARCH_TASK_MANIFEST_AUTHORED_UNREVIEWED",
        "RESEARCH_METRICS_REQUIRE_EXTERNAL_HUMAN_CONFIRMATION",
        "RESEARCH_JSON_PROVENANCE_IS_NOT_IDENTITY_AUTHENTICATION",
        "RESEARCH_SCORER_DOES_NOT_EXECUTE_MODELS",
    ]
    if pairing.rejections:
        warnings.append("RESEARCH_UNPAIRED_RUNS_EXCLUDED_FROM_PAIRED_METRICS")
    if failed_or_canceled_run_count:
        warnings.append("RESEARCH_FAILED_RUNS_EXCLUDED_FROM_PAIRED_METRICS")
    return ResearchEvaluationReport(
        manifest_id=manifest.manifest_id,
        manifest_hash=manifest.computed_hash(),
        task_count=len(manifest.tasks),
        expected_run_count=expected_run_count,
        run_count=len(runs),
        missing_run_count=missing_run_count,
        failed_or_canceled_run_count=failed_or_canceled_run_count,
        completed_run_count=len(runs) - failed_or_canceled_run_count,
        paired_task_count=len(pairing.pairs),
        pair_coverage=(len(pairing.pairs) / len(manifest.tasks)) if manifest.tasks else None,
        unpaired_run_count=len(unpaired_run_ids),
        pairing=pairing,
        task_coverage=task_coverage,
        metrics_by_harness=metrics_by_harness,
        paired_metrics=paired_metrics,
        warnings=warnings,
    )


def _load_manifest_arg(path_value: str | None) -> ResearchTaskManifest:
    return load_task_manifest(path_value) if path_value else default_manifest()


def _manifest_command(args: argparse.Namespace) -> dict[str, Any]:
    manifest = _load_manifest_arg(args.tasks)
    payload = manifest.payload_with_hash()
    _write_text_or_stdout(
        args.output, json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    )
    return {
        "manifest_id": manifest.manifest_id,
        "manifest_hash": manifest.computed_hash(),
        "task_count": len(manifest.tasks),
        "authored_status": manifest.authored_status,
    }


def _export_inputs_command(args: argparse.Namespace) -> dict[str, Any]:
    manifest = _load_manifest_arg(args.tasks)
    inputs = export_agent_inputs(manifest)
    _write_jsonl_or_stdout(args.output, inputs)
    return {"manifest_hash": manifest.computed_hash(), "task_count": len(inputs)}


def _validate_runs_command(args: argparse.Namespace) -> dict[str, Any]:
    manifest = _load_manifest_arg(args.tasks)
    runs = load_jsonl(args.runs, ResearchRun)
    _validate_runs(manifest, runs)
    return {
        "manifest_hash": manifest.computed_hash(),
        "run_count": len(runs),
        "with_harness": sum(run.harness_mode is HarnessMode.WITH_HARNESS for run in runs),
        "without_harness": sum(run.harness_mode is HarnessMode.WITHOUT_HARNESS for run in runs),
    }


def _review_template_command(args: argparse.Namespace) -> dict[str, Any]:
    manifest = _load_manifest_arg(args.tasks)
    runs = load_jsonl(args.runs, ResearchRun)
    _validate_runs(manifest, runs)
    templates = [
        ExpertReview(
            review_id=f"review-{run.run_id}",
            manifest_hash=manifest.computed_hash(),
            task_id=run.task_id,
            run_id=run.run_id,
            run_digest=run.evaluated_digest(),
            harness_mode=run.harness_mode,
            provenance=ReviewProvenance(
                provenance_status=ProvenanceStatus.UNVERIFIED,
                human_confirmation=HumanConfirmationStatus.UNREVIEWED,
            ),
        )
        for run in runs
    ]
    _write_jsonl_or_stdout(args.output, templates)
    return {"manifest_hash": manifest.computed_hash(), "review_template_count": len(templates)}


def _score_command(args: argparse.Namespace) -> dict[str, Any]:
    manifest = _load_manifest_arg(args.tasks)
    runs = load_jsonl(args.runs, ResearchRun)
    reviews = load_jsonl(args.reviews, ExpertReview) if args.reviews else []
    report = score_evaluation(manifest, runs, reviews)
    payload = _model_payload(report)
    _write_text_or_stdout(
        args.output, json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    )
    return {
        "manifest_hash": report.manifest_hash,
        "task_count": report.task_count,
        "run_count": report.run_count,
        "paired_task_count": report.paired_task_count,
        "missing_run_count": report.missing_run_count,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m alr_tw.evaluation.research_tasks",
        description="Export and score public-safe ALR-TW research-task evaluation records.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    manifest = subcommands.add_parser(
        "manifest", help="Show the built-in or explicit task manifest"
    )
    manifest.add_argument("--tasks", help="Explicit manifest JSON path")
    manifest.add_argument("--output", help="Manifest JSON output path, or - for stdout")

    export_inputs = subcommands.add_parser(
        "export-agent-inputs",
        help="Export gold-free JSONL inputs for a model runner",
    )
    export_inputs.add_argument("--tasks", help="Explicit manifest JSON path")
    export_inputs.add_argument("--output", help="JSONL output path, or - for stdout")

    validate_runs = subcommands.add_parser("validate-runs", help="Validate collected run JSONL")
    validate_runs.add_argument("--tasks", help="Explicit manifest JSON path")
    validate_runs.add_argument("--runs", required=True, help="Collected run JSONL path")

    review_template = subcommands.add_parser(
        "export-review-template",
        help="Create unreviewed expert-review JSONL placeholders",
    )
    review_template.add_argument("--tasks", help="Explicit manifest JSON path")
    review_template.add_argument("--runs", required=True, help="Collected run JSONL path")
    review_template.add_argument("--output", help="JSONL output path, or - for stdout")

    score = subcommands.add_parser("score", help="Score imported expert reviews")
    score.add_argument("--tasks", help="Explicit manifest JSON path")
    score.add_argument("--runs", required=True, help="Collected run JSONL path")
    score.add_argument("--reviews", help="Imported expert-review JSONL path")
    score.add_argument("--output", help="Report JSON output path, or - for stdout")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "manifest":
            summary = _manifest_command(args)
        elif args.command == "export-agent-inputs":
            summary = _export_inputs_command(args)
        elif args.command == "validate-runs":
            summary = _validate_runs_command(args)
        elif args.command == "export-review-template":
            summary = _review_template_command(args)
        else:
            summary = _score_command(args)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 2
    if args.command == "validate-runs":
        print(json.dumps({"ok": True, "data": summary}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
