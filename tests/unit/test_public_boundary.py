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
