from pathlib import Path

from alr_tw.scripts.check_public_boundary import find_public_boundary_violations


def test_public_boundary_checker_flags_forbidden_paths_and_tokens(tmp_path: Path):
    secret_file = tmp_path / "logs" / "run.log"
    secret_file.parent.mkdir()
    secret_file.write_text("api_" + "key = 'not-real'\n", encoding="utf-8")

    violations = find_public_boundary_violations(tmp_path)

    assert any("logs/" in item for item in violations)
    assert any("api_key" in item for item in violations)


def test_public_boundary_checker_allows_demo_json(tmp_path: Path):
    demo = tmp_path / "demo_data" / "synthetic_laws.jsonl"
    demo.parent.mkdir()
    demo.write_text('{"source_tier":"synthetic"}\n', encoding="utf-8")

    assert find_public_boundary_violations(tmp_path) == []


def test_public_boundary_checker_flags_private_runtime_dependencies(tmp_path: Path):
    source = tmp_path / "src" / "adapter.py"
    source.parent.mkdir()
    source.write_text(
        "from " + "legal_" + "portal import Runtime\n",
        encoding="utf-8",
    )
    project = tmp_path / "pyproject.toml"
    project.write_text(
        '[project]\ndependencies = ["' + "taiwan-legal-" + 'portal>=1"]\n',
        encoding="utf-8",
    )

    violations = find_public_boundary_violations(tmp_path)

    assert any("private runtime import" in item for item in violations)
    assert any("private runtime dependency" in item for item in violations)


def test_public_boundary_checker_flags_production_state_artifacts(tmp_path: Path):
    manifest = tmp_path / "operator_attestation.json"
    manifest.write_text("{}\n", encoding="utf-8")
    calibration = tmp_path / "ranking_calibration" / "weights.json"
    calibration.parent.mkdir()
    calibration.write_text("{}\n", encoding="utf-8")

    violations = find_public_boundary_violations(tmp_path)

    assert any("operator_attestation.json" in item for item in violations)
    assert any("ranking_calibration" in item for item in violations)


def test_public_boundary_checker_allows_abstract_upstream_documentation(tmp_path: Path):
    document = tmp_path / "README.md"
    document.write_text(
        "This public-safe core is extracted from a private upstream incubator.\n",
        encoding="utf-8",
    )

    assert find_public_boundary_violations(tmp_path) == []
