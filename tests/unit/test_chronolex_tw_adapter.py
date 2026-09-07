"""ChronoLex-TW adapter tests use synthetic rows and server receipts only."""

from __future__ import annotations

import csv
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from alr_tw.contracts import (
    ApplicabilityResolutionStatus,
    ApplicabilityStatus,
    ApplicabilityValidationDecision,
    ApplicabilityValidationResult,
)
from alr_tw.contracts.historical_law import HistoricalLawValidationResult
from alr_tw.contracts.public_law import (
    PublicLawMaterialType,
    PublicLawServerMetadata,
    PublicLawSourceRecord,
    PublicLawSourceRole,
    PublicLawValidationDecision,
)
from alr_tw.contracts.sources import EvidenceSpan, SourceTier, TrustStatus
from alr_tw.evaluation.chronolex_tw import (
    CHRONOLEX_TW_DATASET_REVISION,
    ChronoLexAdjudication,
    ChronoLexAgentRun,
    ChronoLexCase,
    ChronoLexMetricStatus,
    evaluate_chronolex,
    load_chronolex_csv,
    main,
    normalize_article,
    normalize_law_name,
)


FIELDS = (
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


def _row(
    *,
    source_id: str = "CLTW-2012-criminal-41",
    gold_law: str = "中華民國刑法",
    gold_article: str = "122",
    gold_version_date: str = "2011-11-30",
    legal_date: str = "2012-08-01",
    answer: str = "D",
    tau: str = "Shifted",
) -> dict[str, object]:
    options = ["選項甲", "選項乙", "選項丙", "選項丁"]
    return {
        "id": source_id,
        "question": "刑法受賄罪之程序處理，下列何者正確？",
        "A": options[0],
        "B": options[1],
        "C": options[2],
        "D": options[3],
        "answer": answer,
        "choices": json.dumps(options, ensure_ascii=False),
        "legal_date": legal_date,
        "year": int(legal_date[:4]),
        "gold_law": gold_law,
        "gold_article": gold_article,
        "gold_version_date": gold_version_date,
        "tau": tau,
        "question_unmasked": f"依{gold_law}第{gold_article}條，下列何者正確？",
        "subject": "criminal",
        "exam_level": "三等考試",
        "source_papers": "synthetic-paper",
    }


def _case(*, row_index: int = 0, **overrides: object) -> ChronoLexCase:
    return ChronoLexCase.from_dataset_row(_row(**overrides), row_index=row_index)


def _run(
    case: ChronoLexCase,
    *,
    law_name: str = "刑法",
    article: str = "122",
    as_of_date: date | None = None,
    answer: str | None = "D",
    terminated: bool = True,
) -> ChronoLexAgentRun:
    return ChronoLexAgentRun.model_validate(
        {
            "case_key": case.case_key,
            "tool_calls": [
                {
                    "law_name": law_name,
                    "article": article,
                    "as_of_date": (as_of_date or case.legal_date).isoformat(),
                    "lookup_status": "found",
                }
            ],
            "final_answer": answer,
            "terminated": terminated,
        }
    )


def _adjudication(
    case: ChronoLexCase,
    *,
    promulgated_on: date | None = None,
    accepted: bool = True,
    law_name: str = "刑法",
    article: str = "122",
    as_of_date: date | None = None,
) -> ChronoLexAdjudication:
    source_id = "source-history-1"
    historical = HistoricalLawValidationResult(
        provider_id="official-history",
        query_id="chronolex-query-1",
        decision=(
            PublicLawValidationDecision.ACCEPTED
            if accepted
            else PublicLawValidationDecision.QUALIFIED
        ),
        applicability_source_ids=[source_id] if accepted else [],
    )
    applicability = ApplicabilityValidationResult(
        decision=(
            ApplicabilityValidationDecision.ACCEPTED
            if accepted
            else ApplicabilityValidationDecision.BLOCKED
        ),
        resolution_status=(
            ApplicabilityResolutionStatus.RESOLVED
            if accepted
            else ApplicabilityResolutionStatus.BLOCKED
        ),
        status=(ApplicabilityStatus.APPLICABLE if accepted else ApplicabilityStatus.INDETERMINATE),
        selected_source_ids=[source_id] if accepted else [],
    )
    return ChronoLexAdjudication(
        case_key=case.case_key,
        call_index=1,
        law_name=law_name,
        article=article,
        as_of_date=as_of_date or case.legal_date,
        source_id=source_id,
        promulgated_on=promulgated_on or case.gold_version_date,
        material_type=PublicLawMaterialType.HISTORICAL_STATUTE,
        source_role=PublicLawSourceRole.NORMATIVE_RULE,
        historical_validation=historical,
        applicability_validation=applicability,
    )


def _server_source(case: ChronoLexCase, *, source_id: str) -> PublicLawSourceRecord:
    now = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
    metadata = PublicLawServerMetadata(
        provider_id="official-history",
        snapshot_id="chronolex-snapshot-1",
        generation="chronolex-generation-1",
        receipt_id="chronolex-receipt-1",
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )
    text = "合成歷史法規內容，僅供 adapter 契約測試。"
    digest = EvidenceSpan.hash_text(text)
    return PublicLawSourceRecord(
        source_id=source_id,
        source_key=f"chronolex:{source_id}",
        source_version_id=f"{source_id}:v1",
        material_type=PublicLawMaterialType.HISTORICAL_STATUTE,
        source_role=PublicLawSourceRole.NORMATIVE_RULE,
        provider_id=metadata.provider_id,
        source_tier=SourceTier.OFFICIAL,
        trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
        official_identifier=f"CHRONOLEX-{source_id}",
        official_url="https://example.test/chronolex/source",
        citation="合成歷史法規資料",
        issued_at=datetime.combine(case.gold_version_date, datetime.min.time(), tzinfo=UTC),
        fetched_at=now,
        verified_at=now,
        expires_at=now + timedelta(hours=1),
        content_hash=digest,
        normalized_content_hash=digest,
        normalized_text=text,
        server_metadata=metadata,
    )


def test_agent_input_hides_all_gold_and_disambiguates_duplicate_source_ids() -> None:
    first_row = _row(source_id="CLTW-duplicate")
    second_row = _row(source_id="CLTW-duplicate")
    second_row["question"] = "另一題 masked 題目"
    second_row["source_papers"] = "another-paper"
    first = ChronoLexCase.from_dataset_row(first_row, row_index=22)
    repeated = ChronoLexCase.from_dataset_row(first_row, row_index=99)
    second = ChronoLexCase.from_dataset_row(second_row, row_index=24)

    payload = first.agent_input().model_dump(mode="json")

    assert first.case_key.startswith("CLTW-duplicate#")
    assert first.case_key == repeated.case_key
    assert first.case_key != second.case_key
    assert set(payload) == {
        "schema_version",
        "dataset_id",
        "dataset_revision",
        "case_key",
        "source_id",
        "question",
        "choices",
        "legal_date",
    }
    assert "gold" not in json.dumps(payload, ensure_ascii=False)
    assert "question_unmasked" not in payload
    assert payload["dataset_revision"] == CHRONOLEX_TW_DATASET_REVISION


def test_dataset_row_rejects_choices_or_schema_drift() -> None:
    mismatched = _row()
    mismatched["choices"] = json.dumps(["不一致"] * 4, ensure_ascii=False)
    with pytest.raises(ValueError, match="CHOICES_MISMATCH"):
        ChronoLexCase.from_dataset_row(mismatched, row_index=0)

    missing = _row()
    missing.pop("question_unmasked")
    with pytest.raises(ValueError, match="DATASET_SCHEMA_MISMATCH"):
        ChronoLexCase.from_dataset_row(missing, row_index=0)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("185-3", "185-3"),
        ("第185條之3", "185-3"),
        ("第 185 條之 3 第 1 項", "185-3"),
        ("122條", "122"),
    ],
)
def test_article_normalization(raw: str, expected: str) -> None:
    assert normalize_article(raw) == expected


def test_law_name_normalization_accepts_official_criminal_code_alias() -> None:
    assert normalize_law_name("中華民國刑法") == "刑法"
    assert normalize_law_name(" 刑 法 ") == "刑法"


def test_correct_answer_does_not_hide_article_or_version_failure() -> None:
    case = _case()
    run = _run(case, law_name="刑事訴訟法", article="228", answer="D")

    score = evaluate_chronolex([case], [run]).case_scores[0]

    assert score.historical_article_hit.status is ChronoLexMetricStatus.INCORRECT
    assert score.version_correctness.status is ChronoLexMetricStatus.NOT_SCOREABLE
    assert score.final_answer_correctness.status is ChronoLexMetricStatus.CORRECT


def test_version_is_scored_only_after_both_server_validations_accept() -> None:
    case = _case()
    run = _run(case)

    missing = evaluate_chronolex([case], [run]).case_scores[0]
    blocked = evaluate_chronolex(
        [case],
        [run],
        [_adjudication(case, accepted=False)],
    ).case_scores[0]
    accepted = evaluate_chronolex(
        [case],
        [run],
        [_adjudication(case)],
    ).case_scores[0]

    assert missing.version_correctness.status is ChronoLexMetricStatus.NOT_SCOREABLE
    assert blocked.version_correctness.status is ChronoLexMetricStatus.NOT_SCOREABLE
    assert accepted.version_correctness.status is ChronoLexMetricStatus.CORRECT


def test_server_result_projection_supplies_the_trusted_version_date() -> None:
    case = _case()
    run = _run(case)
    accepted = _adjudication(case)
    assert accepted.historical_validation is not None
    assert accepted.applicability_validation is not None
    source = _server_source(case, source_id=accepted.source_id)

    projected = ChronoLexAdjudication.from_server_results(
        case_key=case.case_key,
        call_index=1,
        law_name="刑法",
        article="122",
        as_of_date=case.legal_date,
        source=source,
        historical_validation=accepted.historical_validation,
        applicability_validation=accepted.applicability_validation,
    )
    score = evaluate_chronolex([case], [run], [projected]).case_scores[0]

    assert projected.promulgated_on == case.gold_version_date
    assert score.version_correctness.status is ChronoLexMetricStatus.CORRECT


def test_wrong_accepted_version_date_is_incorrect_not_unscoreable() -> None:
    case = _case()
    run = _run(case)
    report = evaluate_chronolex(
        [case],
        [run],
        [_adjudication(case, promulgated_on=date(2010, 1, 1))],
    )

    outcome = report.case_scores[0].version_correctness
    assert outcome.status is ChronoLexMetricStatus.INCORRECT
    assert outcome.reason_codes == ["CHRONOLEX_VERSION_DATE_MISMATCH"]


def test_historical_article_hit_requires_exact_legal_date() -> None:
    case = _case()
    run = _run(case, as_of_date=date(2026, 9, 1))

    score = evaluate_chronolex([case], [run]).case_scores[0]

    assert score.historical_article_hit.status is ChronoLexMetricStatus.INCORRECT
    assert score.historical_article_hit.reason_codes == ["CHRONOLEX_LEGAL_DATE_MISMATCH"]


def test_report_keeps_shifted_stable_and_duplicate_id_accounting_separate() -> None:
    shifted = _case(row_index=0, source_id="CLTW-duplicate")
    stable = _case(
        row_index=1,
        source_id="CLTW-duplicate",
        gold_law="行政罰法",
        gold_article="4",
        gold_version_date="2012-11-28",
        legal_date="2013-08-01",
        answer="A",
        tau="Stable",
    )
    report = evaluate_chronolex([shifted, stable], [_run(shifted)])

    assert report.case_count == 2
    assert report.unique_source_id_count == 1
    assert report.duplicate_source_id_groups == 1
    assert report.duplicate_source_id_rows == 1
    assert report.strata_counts == {"Shifted": 1, "Stable": 1}
    assert report.metrics["historical_article_hit"].correct == 1
    assert report.metrics["historical_article_hit"].incorrect == 1
    assert report.metrics["version_correctness"].coverage == 0.0
    assert set(report.by_tau) == {"Shifted", "Stable"}


def test_loader_and_cli_prepare_never_emit_gold(tmp_path: Path, capsys) -> None:
    dataset = tmp_path / "chronolex.csv"
    with dataset.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerow(_row())

    cases = load_chronolex_csv(dataset)
    exit_code = main(["prepare", "--dataset", str(dataset)])
    output = capsys.readouterr().out

    assert len(cases) == 1
    assert exit_code == 0
    payload = json.loads(output)
    assert payload["case_key"] == cases[0].case_key
    assert "gold" not in output
    assert "question_unmasked" not in output


def test_cli_score_reports_unscoreable_version_without_server_stream(
    tmp_path: Path,
    capsys,
) -> None:
    dataset = tmp_path / "chronolex.csv"
    runs = tmp_path / "runs.jsonl"
    with dataset.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerow(_row())
    case = load_chronolex_csv(dataset)[0]
    runs.write_text(_run(case).model_dump_json() + "\n", encoding="utf-8")

    exit_code = main(["score", "--dataset", str(dataset), "--runs", str(runs)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["metrics"]["historical_article_hit"]["correct"] == 1
    assert payload["metrics"]["version_correctness"]["not_scoreable"] == 1
    assert payload["metrics"]["version_correctness"]["scorable_accuracy"] is None
    assert payload["metrics"]["final_answer_correctness"]["correct"] == 1


def test_invalid_agent_answer_is_rejected_before_scoring() -> None:
    case = _case()
    with pytest.raises(ValidationError):
        _run(case, answer="E")
