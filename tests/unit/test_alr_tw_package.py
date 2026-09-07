from pathlib import Path
import tomllib

PROJECT_FILE = Path(__file__).resolve().parents[2] / "pyproject.toml"

def test_alr_tw_package_exposes_public_version_and_harness():
    import alr_tw
    from alr_tw.harness.orchestrator import run_agentic_demo

    trace = run_agentic_demo("民法第184條 押金", scenario="pass_official_source")

    assert alr_tw.__version__ == "0.12.0"
    assert trace.schema_version == "alr-tw.agentic_trace/v1"
    assert trace.final_action == "answer"


def test_pyproject_and_runtime_versions_match():
    import alr_tw

    project = tomllib.loads(PROJECT_FILE.read_text(encoding="utf-8"))

    assert project["project"]["version"] == alr_tw.__version__


def test_each_https_extra_declares_system_truststore():
    project = tomllib.loads(PROJECT_FILE.read_text(encoding="utf-8"))
    extras = project["project"]["optional-dependencies"]

    for name in ("live", "tlr", "all"):
        assert any(item.startswith("truststore>=") for item in extras[name]), name
