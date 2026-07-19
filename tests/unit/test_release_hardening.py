from __future__ import annotations

import importlib
import importlib.util
import subprocess
import sys
from pathlib import Path

from alr_tw.scripts.check_public_boundary import find_public_boundary_violations

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK_NO_FORBIDDEN = REPO_ROOT / "scripts" / "check_no_forbidden_files.py"


def _load_forbidden_checker_module():
    spec = importlib.util.spec_from_file_location(
        "check_no_forbidden_files", CHECK_NO_FORBIDDEN
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_forbidden_check(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECK_NO_FORBIDDEN)],
        cwd=path,
        text=True,
        capture_output=True,
        check=False,
    )


def test_external_agent_boundary_is_explicit_in_public_docs():
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
    assert "本版不宣稱提供 LLM" in acceptance


def test_ranking_docs_and_modules_mark_demo_parameters_as_illustrative():
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


def test_threat_model_separates_field_presence_from_byte_verification():
    text = (REPO_ROOT / "docs/THREAT_MODEL.md").read_text(encoding="utf-8")

    assert "field presence" in text
    assert "promotion pipeline" in text
    assert "ARCHITECTURE_CONTRACT.md" in text


def test_ci_runs_history_secret_scan():
    text = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "gitleaks" in text or "trufflehog" in text


def test_ci_installs_live_provider_dependencies_before_provider_tests():
    text = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert ".[dev,live]" in text


def test_deployment_starting_points_are_documented_as_illustrative():
    text = (REPO_ROOT / "docs/DEPLOYMENT_STARTING_POINTS.md").read_text(encoding="utf-8")

    assert "illustrative" in text.lower()
    assert "not production" in text.lower()
    assert "measure" in text.lower()


def test_forbidden_checker_detects_large_text_secret_assignment(tmp_path: Path):
    candidate = tmp_path / "large_public_doc.txt"
    secret_assignment = "api" + "_key = 'synthetic'"
    candidate.write_text("x" * 1_100_000 + f"\n{secret_assignment}\n", encoding="utf-8")

    result = _run_forbidden_check(tmp_path)

    assert result.returncode == 1
    assert "api_key" in result.stderr


def test_public_guards_scan_untracked_files_in_git_worktree(tmp_path: Path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    candidate = tmp_path / "untracked.env"
    secret_assignment = "api" + "_key = 'synthetic'"
    candidate.write_text(f"{secret_assignment}\n", encoding="utf-8")

    result = _run_forbidden_check(tmp_path)
    public_boundary_violations = find_public_boundary_violations(tmp_path)

    assert result.returncode == 1
    assert "api_key" in result.stderr
    assert any("api_key" in item for item in public_boundary_violations)


def test_public_boundary_scans_large_text_instead_of_silently_skipping(tmp_path: Path):
    candidate = tmp_path / "large_public_doc.txt"
    secret_assignment = "to" + "ken = 'synthetic'"
    candidate.write_text("x" * 1_100_000 + f"\n{secret_assignment}\n", encoding="utf-8")

    violations = find_public_boundary_violations(tmp_path)

    assert any("token" in item for item in violations)


def test_guard_size_caps_stay_aligned():
    forbidden_checker = _load_forbidden_checker_module()
    public_boundary = importlib.import_module("alr_tw.scripts.check_public_boundary")

    assert forbidden_checker.MAX_FILE_SIZE == public_boundary.MAX_TEXT_SCAN_BYTES


def test_over_cap_text_files_are_not_silently_skipped(tmp_path: Path):
    forbidden_checker = _load_forbidden_checker_module()
    candidate = tmp_path / "oversized_public_doc.txt"
    candidate.write_text(
        "x" * (forbidden_checker.MAX_FILE_SIZE + 1),
        encoding="utf-8",
    )

    result = _run_forbidden_check(tmp_path)
    public_boundary_violations = find_public_boundary_violations(tmp_path)

    assert result.returncode == 1
    assert "file too large" in result.stderr
    assert any("file too large" in item for item in public_boundary_violations)


def test_forbidden_checker_rejects_non_utf8_text_files(tmp_path: Path):
    candidate = tmp_path / "big5_fixture.txt"
    candidate.write_bytes("司法院公開資料".encode("big5"))

    result = _run_forbidden_check(tmp_path)
    public_boundary_violations = find_public_boundary_violations(tmp_path)

    assert result.returncode == 1
    assert "non-utf-8" in result.stderr.lower()
    assert any("non-utf-8" in item for item in public_boundary_violations)


def test_both_guards_reject_utf16_le_forbidden_markers(tmp_path: Path):
    candidate = tmp_path / "utf16_fixture.txt"
    marker = "/" + "Users" + "/" + "leak"
    candidate.write_bytes(marker.encode("utf-16-le"))

    result = _run_forbidden_check(tmp_path)
    public_boundary_violations = find_public_boundary_violations(tmp_path)

    assert result.returncode == 1
    assert "forbidden" in result.stderr.lower()
    assert any("/" + "Users" + "/" in item for item in public_boundary_violations)


def test_forbidden_checker_rejects_real_shaped_judgment_ids(tmp_path: Path):
    real_shaped_jid = ",".join(["TPDV", "112", "訴", "123", "20240101", "1"])
    candidate = tmp_path / "fixture.md"
    candidate.write_text(f"citation: {real_shaped_jid}\n", encoding="utf-8")

    result = _run_forbidden_check(tmp_path)

    assert result.returncode == 1
    assert "judgment identifier" in result.stderr


def test_forbidden_checker_rejects_taiwan_identity_numbers(tmp_path: Path):
    synthetic_sensitive_id = "A" + "123456789"
    candidate = tmp_path / "fixture.md"
    candidate.write_text(f"party id: {synthetic_sensitive_id}\n", encoding="utf-8")

    result = _run_forbidden_check(tmp_path)

    assert result.returncode == 1
    assert "taiwan id" in result.stderr.lower()


def test_both_guards_reject_cjk_adjacent_taiwan_identity_numbers(tmp_path: Path):
    synthetic_sensitive_id = "A" + "123456789"
    candidate = tmp_path / "fixture.md"
    candidate.write_text(f"身分證{synthetic_sensitive_id}號\n", encoding="utf-8")

    result = _run_forbidden_check(tmp_path)
    public_boundary_violations = find_public_boundary_violations(tmp_path)

    assert result.returncode == 1
    assert "taiwan id" in result.stderr.lower()
    assert any("taiwan_id" in item for item in public_boundary_violations)


def test_both_guards_reject_cjk_adjacent_judgment_identifiers(tmp_path: Path):
    real_shaped_jid = ",".join(["TPDV", "112", "訴", "123", "20240101", "1"])
    candidate = tmp_path / "fixture.md"
    candidate.write_text(f"裁判{real_shaped_jid}號\n", encoding="utf-8")

    result = _run_forbidden_check(tmp_path)
    public_boundary_violations = find_public_boundary_violations(tmp_path)

    assert result.returncode == 1
    assert "judgment identifier" in result.stderr
    assert any("judgment_identifier" in item for item in public_boundary_violations)


def test_both_guards_reject_non_conjunctive_synthetic_namespace(tmp_path: Path):
    outside_namespace_jid = ",".join(["TSTV", "112", "訴", "9", "19990101", "1"])
    candidate = tmp_path / "fixture.md"
    candidate.write_text(f"citation: {outside_namespace_jid}\n", encoding="utf-8")

    result = _run_forbidden_check(tmp_path)
    public_boundary_violations = find_public_boundary_violations(tmp_path)

    assert result.returncode == 1
    assert "judgment identifier" in result.stderr
    assert any("judgment_identifier" in item for item in public_boundary_violations)


def test_forbidden_checker_allows_synthetic_judgment_namespace(tmp_path: Path):
    synthetic_jid = ",".join(["DEMO", "113", "測", "1", "20990101", "1"])
    candidate = tmp_path / "fixture.md"
    candidate.write_text(f"citation: {synthetic_jid}\n", encoding="utf-8")

    result = _run_forbidden_check(tmp_path)

    assert result.returncode == 0, result.stderr


def test_current_public_tree_has_no_domain_guard_false_positives():
    forbidden_checker = _load_forbidden_checker_module()

    assert forbidden_checker.find_forbidden_file_violations(REPO_ROOT) == []
    assert find_public_boundary_violations(REPO_ROOT) == []


def test_public_readmes_share_v060_safety_claims():
    for relative in ("README.md", "README.zh-TW.md"):
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert "v0.6.0" in text
        assert "本 repo 不包含 LLM，也不包含 agent 實作。" in text
        assert "TLR" in text and "candidate" in text
        assert "blocked" in text and "answer body" in text
