from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from alr_tw.harness.orchestrator import run_agentic_demo
    from alr_tw.harness.report_builder import build_validation_report

    trace = run_agentic_demo(
        "民法第184條 押金",
        scenario="fail_candidate_only",
    )
    print(json.dumps(trace.model_dump(), ensure_ascii=False, indent=2))
    print()
    print(build_validation_report(trace))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
