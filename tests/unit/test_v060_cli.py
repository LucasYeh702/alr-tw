from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from alr_tw.cli import main
from alr_tw.contracts.providers import DataMode
from alr_tw.contracts.research import (
    CoverageState,
    PrivacyStatus,
    ResearchObligation,
    ResearchObligationKind,
    ResearchRun,
    ResearchState,
)
from alr_tw.storage import SqliteStore


def _run(run_id: str) -> ResearchRun:
    now = datetime.now(UTC)
    return ResearchRun(
        run_id=run_id,
        query="合成研究問題",
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=24),
        requested_mode=DataMode.SYNTHETIC,
        effective_mode=DataMode.SYNTHETIC,
        privacy_status=PrivacyStatus.NOT_REQUIRED,
        state=ResearchState.PLANNING,
        obligations=[ResearchObligation(kind=ResearchObligationKind.QUERY_UNDERSTANDING)],
        coverage=CoverageState(),
    )


def test_cli_purge_run_uses_managed_store(tmp_path: Path, capsys) -> None:
    root = tmp_path / "cache"
    store = SqliteStore(root)
    store.save_run(_run("run-cli"))

    exit_code = main(
        ["purge", "--run", "run-cli", "--confirm", "--storage-path", str(root)]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["data"]["success"] is True
    assert payload["data"]["deleted_runs"] == 1
    assert store.get_run("run-cli") is None


def test_cli_doctor_never_prints_secret_values(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("ALR_TW_TLR_API_KEY", "do-not-print-tlr-secret")

    exit_code = main(["doctor", "--storage-path", str(tmp_path / "cache")])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "do-not-print" not in output
    payload = json.loads(output)
    assert payload["data"]["tlr_api_key_configured"] is True
    assert payload["data"]["judicial_source"] == "public_website_html"


def test_cli_live_doctor_requires_explicit_live_mode(capsys, monkeypatch) -> None:
    monkeypatch.delenv("ALR_TW_DATA_MODE", raising=False)

    exit_code = main(["doctor", "--live"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert "CONFIG_MODE_REQUIRED" in payload["error"]
