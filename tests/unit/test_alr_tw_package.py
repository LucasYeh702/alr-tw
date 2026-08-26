from pathlib import Path
import tomllib


def test_alr_tw_package_exposes_public_version_and_harness():
    import alr_tw
    from alr_tw.harness.orchestrator import run_agentic_demo

    trace = run_agentic_demo("民法第184條 押金", scenario="pass_official_source")

    assert alr_tw.__version__ == "0.10.1"
    assert trace.schema_version == "alr-tw.agentic_trace/v1"
    assert trace.final_action == "answer"


def test_pyproject_and_runtime_versions_match():
    import alr_tw

    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert project["project"]["version"] == alr_tw.__version__
