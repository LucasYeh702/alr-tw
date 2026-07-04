from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

from alr_tw.scripts.check_public_boundary import find_public_boundary_violations

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK_NO_FORBIDDEN = REPO_ROOT / "scripts" / "check_no_forbidden_files.py"


def _run_forbidden_check(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECK_NO_FORBIDDEN)],
        cwd=path,
        text=True,
        capture_output=True,
        check=False,
    )


def test_g2_external_agent_boundary_is_explicit_in_public_docs():
    expected = {
        "README.md": "本 repo 不包含 LLM，也不包含 agent 實作。",
        "README.zh-TW.md": "本 repo 不包含 LLM，也不包含 agent 實作。",
        "README.en.md": "This repository does not ship an LLM or agent implementation.",
        "docs/AGENTIC_WORKFLOW.md": (
            "This repository does not ship an LLM or agent implementation."
        ),
    }

    for relative, marker in expected.items():
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert marker in text, relative

    acceptance = (REPO_ROOT / "docs/AGENTIC_HARNESS_ACCEPTANCE.md").read_text(
        encoding="utf-8"
    )
    assert "an LLM or agent implementation shipped in this repo" in acceptance


def test_g3_ranking_docs_and_modules_mark_demo_parameters_as_illustrative():
    for relative in (
        "README.md",
        "README.zh-TW.md",
        "README.en.md",
        "DATA_POLICY.md",
        "docs/ARCHITECTURE_CONTRACT.md",
    ):
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert "production ranking" in text or "生產 ranking" in text, relative
        assert "demo ranking" in text or "示範 ranking" in text, relative

    for module_name in (
        "tw_legal_rag_mcp.retrieval.judgment_ranking",
        "tw_legal_rag_mcp.retrieval.authority_ranker",
        "tw_legal_rag_mcp.retrieval.rrf",
    ):
        module = importlib.import_module(module_name)
        doc = module.__doc__ or ""
        assert "demo" in doc.lower(), module_name
        assert "not production" in doc.lower(), module_name


def test_g4_threat_model_separates_field_presence_from_byte_verification():
    text = (REPO_ROOT / "docs/THREAT_MODEL.md").read_text(encoding="utf-8")

    assert "field presence" in text
    assert "promotion pipeline" in text
    assert "ARCHITECTURE_CONTRACT.md" in text


def test_g9_ci_runs_history_secret_scan():
    text = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "gitleaks" in text or "trufflehog" in text


def test_g8_deployment_starting_points_are_documented_as_illustrative():
    text = (REPO_ROOT / "docs/DEPLOYMENT_STARTING_POINTS.md").read_text(encoding="utf-8")

    assert "illustrative" in text.lower()
    assert "not production" in text.lower()
    assert "measure" in text.lower()


def test_g5_forbidden_checker_detects_large_text_secret_assignment(tmp_path: Path):
    candidate = tmp_path / "large_public_doc.txt"
    secret_assignment = "api" + "_key = 'synthetic'"
    candidate.write_text("x" * 1_100_000 + f"\n{secret_assignment}\n", encoding="utf-8")

    result = _run_forbidden_check(tmp_path)

    assert result.returncode == 1
    assert "api_key" in result.stderr


def test_g5_public_boundary_scans_large_text_instead_of_silently_skipping(tmp_path: Path):
    candidate = tmp_path / "large_public_doc.txt"
    secret_assignment = "to" + "ken = 'synthetic'"
    candidate.write_text("x" * 1_100_000 + f"\n{secret_assignment}\n", encoding="utf-8")

    violations = find_public_boundary_violations(tmp_path)

    assert any("token" in item for item in violations)


def test_g6_forbidden_checker_rejects_non_utf8_text_files(tmp_path: Path):
    candidate = tmp_path / "big5_fixture.txt"
    candidate.write_bytes("司法院公開資料".encode("big5"))

    result = _run_forbidden_check(tmp_path)

    assert result.returncode == 1
    assert "non-utf-8" in result.stderr.lower()


def test_g7_forbidden_checker_rejects_real_shaped_judgment_ids(tmp_path: Path):
    real_shaped_jid = ",".join(["TPDV", "112", "訴", "123", "20240101", "1"])
    candidate = tmp_path / "fixture.md"
    candidate.write_text(f"citation: {real_shaped_jid}\n", encoding="utf-8")

    result = _run_forbidden_check(tmp_path)

    assert result.returncode == 1
    assert "judgment identifier" in result.stderr


def test_g7_forbidden_checker_rejects_taiwan_identity_numbers(tmp_path: Path):
    synthetic_sensitive_id = "A" + "123456789"
    candidate = tmp_path / "fixture.md"
    candidate.write_text(f"party id: {synthetic_sensitive_id}\n", encoding="utf-8")

    result = _run_forbidden_check(tmp_path)

    assert result.returncode == 1
    assert "taiwan id" in result.stderr.lower()


def test_g7_forbidden_checker_allows_synthetic_judgment_namespace(tmp_path: Path):
    synthetic_jid = ",".join(["DEMO", "113", "測", "1", "20990101", "1"])
    candidate = tmp_path / "fixture.md"
    candidate.write_text(f"citation: {synthetic_jid}\n", encoding="utf-8")

    result = _run_forbidden_check(tmp_path)

    assert result.returncode == 0, result.stderr
