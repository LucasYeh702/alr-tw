from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_identifier_backed_demo_reports_all_trust_gate_outcomes():
    repo_root = Path(__file__).resolve().parents[2]
    demo_path = repo_root / "examples" / "identifier_backed_demo.py"

    result = subprocess.run(
        [sys.executable, str(demo_path)],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "opt-in + resolver hash match -> allow_final" in result.stdout
    assert "opt-in + fabricated hash -> rejected with IDENTIFIER_HASH_MISMATCH" in result.stdout
    assert (
        "default config (no opt-in) -> rejected with IDENTIFIER_BACKED_DISABLED"
        in result.stdout
    )
