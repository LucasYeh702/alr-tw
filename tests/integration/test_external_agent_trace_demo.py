from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_external_agent_trace_demo_prints_passing_and_refused_runs():
    result = subprocess.run(
        [sys.executable, "examples/external_agent_trace_demo.py"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "PASSING RUN" in result.stdout
    assert "REFUSED RUN" in result.stdout
    assert '"trace_kind": "externally_driven"' in result.stdout
    assert '"execution_mode": "actual_tool"' in result.stdout
    assert '"final_action": "answer"' in result.stdout
    assert '"final_action": "refuse"' in result.stdout
    assert '"answer": null' in result.stdout
