"""Focused tests for the public-safe research-task evaluation contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from alr_tw.evaluation.research_tasks import (
    BUILTIN_TASK_COUNT,
    HumanConfirmationStatus,
    HarnessMode,
    MetricName,
    PairStatus,
    ProvenanceStatus,
    ResearchRun,
    ResearchTask,
    ResearchTaskManifest,
    ReviewProvenance,
    ExpertReview,
    default_manifest,
    export_agent_inputs,
    load_jsonl,
    load_task_manifest,
    main,
    manifest_hash,
    pair_runs,
    score_evaluation,
)


def _manifest(task_count: int = 2) -> ResearchTaskManifest:
    builtin = default_manifest()
    return ResearchTaskManifest(
        manifest_id="test-research-tasks",
        tasks=builtin.tasks[:task_count],
    )


def _run(
    manifest: ResearchTaskManifest,
    task_index: int,
    mode: HarnessMode,
    *,
    run_id: str | None = None,
    model_identity: str = "test-model@pinned",
    model_config: dict[str, object] | None = None,
    response_text: str | None = "已完成公開安全研究紀錄。",
    run_status: str = "completed",
) -> ResearchRun:
    task = manifest.tasks[task_index]
    return ResearchRun.model_validate(
        {
            "run_id": run_id or f"run-{task_index}-{mode.value}",
            "manifest_hash": manifest_hash(manifest),
            "task_id": task.task_id,
            "question_hash": task.question_hash,
            "model_identity": model_identity,
            "model_config": model_config or {"temperature": 0, "seed": 7},
            "harness_mode": mode.value,
            "run_status": run_status,
            "response_text": response_text,
        }
    )


def _review(
    manifest: ResearchTaskManifest,
    run: ResearchRun,
    *,
    review_id: str | None = None,
    confirmed: bool = True,
    citation_errors: int | None = 1,
    material_omissions: int | None = 2,
    false_accepts: int | None = 0,
    false_refusals: int | None = 1,
    review_time_seconds: float | None = 12.5,
) -> ExpertReview:
    return ExpertReview(
        review_id=review_id or f"review-{run.run_id}",
        manifest_hash=manifest_hash(manifest),
        task_id=run.task_id,
        run_id=run.run_id,
        run_digest=run.evaluated_digest(),
        harness_mode=run.harness_mode,
        provenance=ReviewProvenance(
            provenance_status=(
                ProvenanceStatus.EXTERNAL_IMPORTED
                if confirmed
                else ProvenanceStatus.UNVERIFIED
            ),
            human_confirmation=(
                HumanConfirmationStatus.CONFIRMED
                if confirmed
                else HumanConfirmationStatus.UNREVIEWED
            ),
            source_ref="test-review-import",
            reviewer_label="reviewer-label-is-metadata-only",
        ),
        citation_errors=citation_errors,
        material_omissions=material_omissions,
        false_accepts=false_accepts,
        false_refusals=false_refusals,
        review_time_seconds=review_time_seconds,
    )


def _metric(report, mode: HarnessMode, metric: MetricName):
    return next(
        item for item in report.metrics_by_harness[mode.value] if item.metric is metric
    )


def test_builtin_manifest_has_36_authored_unreviewed_tasks() -> None:
    manifest = default_manifest()

    assert len(manifest.tasks) == BUILTIN_TASK_COUNT == 36
    assert len({task.domain for task in manifest.tasks}) == 6
    assert len({task.task_type for task in manifest.tasks}) == 6
    assert {task.task_type.value for task in manifest.tasks} == {
        "precision_lookup",
        "quick_similar_cases",
        "draft_claim_audit",
        "historical_as_of",
        "counter_authority",
        "role_restriction",
    }
    assert all(task.authored_status == "authored_unreviewed" for task in manifest.tasks)
    assert manifest.authored_status == "authored_unreviewed"
    assert len({task.task_id for task in manifest.tasks}) == 36


def test_builtin_manifest_is_one_task_per_domain_and_type() -> None:
    manifest = default_manifest()
    combinations = {(task.domain, task.task_type) for task in manifest.tasks}

    assert len(combinations) == 36
    assert manifest.computed_hash() == default_manifest().computed_hash()
    assert manifest.computed_hash() == manifest_hash(manifest)


def test_manifest_loader_checks_optional_hash_and_rejects_extra_fields(tmp_path: Path) -> None:
    manifest = _manifest(1)
    path = tmp_path / "tasks.json"
    path.write_text(
        json.dumps(manifest.payload_with_hash(), ensure_ascii=False),
        encoding="utf-8",
    )

    loaded = load_task_manifest(path)
    assert loaded.computed_hash() == manifest.computed_hash()

    malformed = manifest.payload_with_hash()
    malformed["unexpected"] = True
    path.write_text(json.dumps(malformed), encoding="utf-8")
    with pytest.raises(ValueError, match="EXTRA_FORBIDDEN|extra_forbidden|invalid"):
        load_task_manifest(path)


def test_agent_input_export_is_gold_free() -> None:
    manifest = default_manifest()
    inputs = export_agent_inputs(manifest)
    serialized = "\n".join(
        json.dumps(item.model_dump(mode="json"), ensure_ascii=False) for item in inputs
    )

    assert len(inputs) == 36
    assert all(set(item.model_dump()) == {
        "schema_version",
        "manifest_id",
        "manifest_hash",
        "task_id",
        "domain",
        "task_type",
        "prompt",
        "constraints",
        "public_safe",
    } for item in inputs)
    assert "gold" not in serialized.lower()
    assert "answer" not in serialized.lower()
    assert "expert" not in serialized.lower()


@pytest.mark.parametrize("extra", [
    {"gold_answer": "do-not-export"},
    {"nested": {"gold_answer": "do-not-export"}},
    {"task_label": {"answer": "do-not-export"}},
    {"max_candidate_items": True},
    {"as_of_date": "today"},
])
def test_agent_constraints_reject_hidden_metadata_and_invalid_controls(extra):
    payload = default_manifest().tasks[0].model_dump()
    payload["constraints"].update(extra)
    with pytest.raises(ValueError, match="RESEARCH_INPUT_CONSTRAINT"):
        ResearchTask.model_validate(payload)


def test_export_revalidates_mutated_nested_constraints():
    manifest = default_manifest()
    manifest.tasks[0].constraints["gold_answer"] = "do-not-export"
    with pytest.raises(ValueError, match="RESEARCH_INPUT_CONSTRAINT_FIELD_FORBIDDEN"):
        export_agent_inputs(manifest)


def test_pairing_requires_same_model_identity_and_config() -> None:
    manifest = _manifest(1)
    with_run = _run(manifest, 0, HarnessMode.WITH_HARNESS)
    without_identity = _run(
        manifest,
        0,
        HarnessMode.WITHOUT_HARNESS,
        model_identity="different-model@pinned",
    )
    result = pair_runs(manifest, [with_run, without_identity])

    assert result.pairs == []
    assert result.rejections[0].status is PairStatus.MODEL_IDENTITY_MISMATCH

    without_config = _run(
        manifest,
        0,
        HarnessMode.WITHOUT_HARNESS,
        model_config={"temperature": 1, "seed": 7},
    )
    result = pair_runs(manifest, [with_run, without_config])
    assert result.pairs == []
    assert result.rejections[0].status is PairStatus.MODEL_CONFIG_MISMATCH


def test_pairing_reports_missing_slots_and_exact_pair() -> None:
    manifest = _manifest(2)
    runs = [
        _run(manifest, 0, HarnessMode.WITH_HARNESS),
        _run(manifest, 0, HarnessMode.WITHOUT_HARNESS),
        _run(manifest, 1, HarnessMode.WITH_HARNESS),
    ]
    result = pair_runs(manifest, runs)

    assert len(result.pairs) == 1
    assert result.pairs[0].task_id == manifest.tasks[0].task_id
    assert result.rejections[0].status is PairStatus.MISSING_WITHOUT_HARNESS


def test_mismatched_case_manifest_or_question_fails_closed() -> None:
    manifest = _manifest(1)
    run = _run(manifest, 0, HarnessMode.WITH_HARNESS)

    with pytest.raises(ValueError, match="MANIFEST_HASH_MISMATCH"):
        pair_runs(
            manifest,
            [run.model_copy(update={"manifest_hash": "0" * 64})],
        )
    with pytest.raises(ValueError, match="UNKNOWN_TASK"):
        pair_runs(
            manifest,
            [run.model_copy(update={"task_id": "unknown-task"})],
        )
    with pytest.raises(ValueError, match="QUESTION_HASH_MISMATCH"):
        pair_runs(
            manifest,
            [run.model_copy(update={"question_hash": "0" * 64})],
        )


def test_review_binds_exact_evaluated_run_digest() -> None:
    manifest = _manifest(1)
    run = _run(manifest, 0, HarnessMode.WITH_HARNESS)
    review = _review(manifest, run)
    replaced = run.model_copy(update={"response_text": "被替換的另一份回覆"})

    with pytest.raises(ValueError, match="RUN_DIGEST_MISMATCH"):
        score_evaluation(manifest, [replaced], [review])

    with pytest.raises(ValidationError, match="RUN_DIGEST_MISMATCH"):
        ResearchRun.model_validate(
            {
                **run.model_dump(mode="json", by_alias=True),
                "run_digest": "0" * 64,
            }
        )


def test_duplicate_runs_and_reviews_fail_closed() -> None:
    manifest = _manifest(1)
    run = _run(manifest, 0, HarnessMode.WITH_HARNESS)

    with pytest.raises(ValueError, match="DUPLICATE_RUN_ID"):
        pair_runs(manifest, [run, run.model_copy(update={"harness_mode": "without_harness"})])

    duplicate_slot = run.model_copy(update={"run_id": "another-run"})
    with pytest.raises(ValueError, match="DUPLICATE_TASK_MODE"):
        pair_runs(manifest, [run, duplicate_slot])

    review = _review(manifest, run)
    with pytest.raises(ValueError, match="DUPLICATE_RUN_REVIEW"):
        score_evaluation(manifest, [run], [review, review.model_copy(update={"review_id": "other"})])


def test_unreviewed_or_missing_metrics_are_not_zero_errors() -> None:
    manifest = _manifest(1)
    with_run = _run(manifest, 0, HarnessMode.WITH_HARNESS)
    without_run = _run(manifest, 0, HarnessMode.WITHOUT_HARNESS)
    unreviewed = _review(manifest, with_run, confirmed=False)
    report = score_evaluation(manifest, [with_run, without_run], [unreviewed])

    citation = _metric(report, HarnessMode.WITH_HARNESS, MetricName.CITATION_ERRORS)
    assert citation.denominator == 1
    assert citation.run_present == 1
    assert citation.review_present == 1
    assert citation.unreviewed == 1
    assert citation.scorable == 0
    assert citation.coverage == 0.0
    assert citation.value_sum is None
    assert citation.mean_value is None
    assert citation.nonzero_rate is None

    without_citation = _metric(report, HarnessMode.WITHOUT_HARNESS, MetricName.CITATION_ERRORS)
    assert without_citation.review_missing == 1
    assert without_citation.unreviewed == 0
    assert without_citation.coverage == 0.0
    assert report.missing_run_count == 0
    assert report.paired_task_count == 1
    assert report.paired_metrics[0].comparable == 0
    assert report.paired_metrics[0].delta_without_minus_with is None


def test_confirmed_review_scores_required_metrics_and_paired_delta() -> None:
    manifest = _manifest(1)
    with_run = _run(manifest, 0, HarnessMode.WITH_HARNESS)
    without_run = _run(manifest, 0, HarnessMode.WITHOUT_HARNESS)
    reviews = [
        _review(
            manifest,
            with_run,
            citation_errors=2,
            material_omissions=1,
            false_accepts=1,
            false_refusals=0,
            review_time_seconds=20,
        ),
        _review(
            manifest,
            without_run,
            citation_errors=0,
            material_omissions=2,
            false_accepts=0,
            false_refusals=1,
            review_time_seconds=10,
        ),
    ]
    report = score_evaluation(manifest, [with_run, without_run], reviews)

    with_citations = _metric(report, HarnessMode.WITH_HARNESS, MetricName.CITATION_ERRORS)
    assert with_citations.scorable == 1
    assert with_citations.value_sum == 2
    assert with_citations.mean_value == 2
    assert with_citations.coverage == 1
    assert with_citations.nonzero_count == 1
    assert with_citations.nonzero_rate == 1

    paired = next(
        item for item in report.paired_metrics if item.metric is MetricName.CITATION_ERRORS
    )
    assert paired.denominator == 1
    assert paired.comparable == 1
    assert paired.with_harness_mean == 2
    assert paired.without_harness_mean == 0
    assert paired.delta_without_minus_with == -2

    review_time = _metric(report, HarnessMode.WITHOUT_HARNESS, MetricName.REVIEW_TIME_SECONDS)
    assert review_time.mean_value == 10
    assert review_time.value_sum == 10
    assert review_time.nonzero_count is None


def test_partial_confirmed_review_keeps_metric_missing_and_coverage() -> None:
    manifest = _manifest(1)
    run = _run(manifest, 0, HarnessMode.WITH_HARNESS)
    review = _review(
        manifest,
        run,
        citation_errors=None,
        material_omissions=0,
        false_accepts=None,
        false_refusals=None,
        review_time_seconds=None,
    )
    report = score_evaluation(manifest, [run], [review])

    citation = _metric(report, HarnessMode.WITH_HARNESS, MetricName.CITATION_ERRORS)
    assert citation.metric_missing == 1
    assert citation.scorable == 0
    assert citation.coverage == 0
    assert citation.value_sum is None
    omissions = _metric(report, HarnessMode.WITH_HARNESS, MetricName.MATERIAL_OMISSIONS)
    assert omissions.value_sum == 0
    assert omissions.coverage == 1


def test_negative_nan_and_extra_review_values_are_rejected(tmp_path: Path) -> None:
    manifest = _manifest(1)
    run = _run(manifest, 0, HarnessMode.WITH_HARNESS)
    with pytest.raises(ValidationError):
        _review(manifest, run, citation_errors=-1)
    with pytest.raises(ValidationError):
        _review(manifest, run, review_time_seconds=float("nan"))
    with pytest.raises(ValidationError):
        _review(manifest, run, citation_errors=True)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        _review(manifest, run, citation_errors="1")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        _review(manifest, run, review_time_seconds="12.5")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ExpertReview.model_validate({**_review(manifest, run).model_dump(), "unexpected": True})

    path = tmp_path / "reviews.jsonl"
    path.write_text(
        json.dumps(
            {
                **_review(manifest, run).model_dump(mode="json"),
                "review_time_seconds": "NaN",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="LINE_1"):
        load_jsonl(path, ExpertReview)


@pytest.mark.parametrize("missing_field", ["source_ref", "reviewer_label"])
def test_external_confirmed_review_without_ref_or_label_stays_unreviewed(
    missing_field: str,
) -> None:
    manifest = _manifest(1)
    run = _run(manifest, 0, HarnessMode.WITH_HARNESS)
    source_ref = None if missing_field == "source_ref" else "test-review-import"
    reviewer_label = None if missing_field == "reviewer_label" else "reviewer-label"
    review = _review(manifest, run).model_copy(
        update={
            "provenance": ReviewProvenance(
                provenance_status=ProvenanceStatus.EXTERNAL_IMPORTED,
                human_confirmation=HumanConfirmationStatus.CONFIRMED,
                source_ref=source_ref,
                reviewer_label=reviewer_label,
            )
        }
    )

    assert review.review_status == "unreviewed"
    report = score_evaluation(manifest, [run], [review])
    citation = _metric(report, HarnessMode.WITH_HARNESS, MetricName.CITATION_ERRORS)
    assert citation.unreviewed == 1
    assert citation.scorable == 0
    assert citation.value_sum is None
    assert citation.coverage == 0


def test_diagonal_pilot_selection_matches_the_current_builtin_manifest() -> None:
    selection_path = Path(__file__).parents[2] / "examples" / "research_eval" / "diagonal_pilot_tasks.json"
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    manifest = default_manifest()

    assert selection["manifest_hash"] == manifest.computed_hash()
    assert selection["status"] == "authored_unreviewed"
    assert selection["task_ids"] == [
        "RT-01-01",
        "RT-02-02",
        "RT-03-03",
        "RT-04-04",
        "RT-05-05",
        "RT-06-06",
    ]
    assert len({
        next(task for task in manifest.tasks if task.task_id == task_id).domain
        for task_id in selection["task_ids"]
    }) == 6


@pytest.mark.parametrize("run_status", ["failed", "canceled"])
def test_failed_or_canceled_runs_are_counted_but_excluded_from_completed_pairs(
    run_status: str,
) -> None:
    manifest = _manifest(1)
    with_run = _run(
        manifest,
        0,
        HarnessMode.WITH_HARNESS,
        response_text=None,
        run_status=run_status,
    )
    without_run = _run(manifest, 0, HarnessMode.WITHOUT_HARNESS)

    result = pair_runs(manifest, [with_run, without_run])
    assert result.pairs == []
    assert result.rejections[0].status is PairStatus.FAILED_OR_CANCELED_RUN

    report = score_evaluation(manifest, [with_run, without_run])
    assert report.failed_or_canceled_run_count == 1
    assert report.completed_run_count == 1
    assert report.paired_task_count == 0
    assert report.pair_coverage == 0


def test_cli_manifest_and_agent_export_are_deterministic(capsys) -> None:
    assert main(["manifest"]) == 0
    manifest_payload = json.loads(capsys.readouterr().out)
    assert manifest_payload["manifest_id"] == "alr-tw-public-research-tasks-v1"
    assert manifest_payload["manifest_hash"] == default_manifest().computed_hash()
    assert len(manifest_payload["tasks"]) == 36

    assert main(["export-agent-inputs"]) == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line]
    assert len(lines) == 36
    assert all("gold" not in line.lower() for line in lines)


def test_cli_score_emits_one_report_json(tmp_path: Path, capsys) -> None:
    manifest = _manifest(1)
    runs_path = tmp_path / "runs.jsonl"
    runs_path.write_text(
        json.dumps(
            _run(manifest, 0, HarnessMode.WITH_HARNESS).model_dump(
                mode="json", by_alias=True
            ),
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(json.dumps(manifest.payload_with_hash(), ensure_ascii=False), encoding="utf-8")

    assert main(["score", "--tasks", str(tasks_path), "--runs", str(runs_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "alr-tw.research-evaluation-report/v1"
    assert payload["missing_run_count"] == 1
    assert payload["metrics_by_harness"]["with_harness"][0]["coverage"] == 0
