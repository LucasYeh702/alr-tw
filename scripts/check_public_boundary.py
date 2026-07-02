#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    from alr_tw.scripts.check_public_boundary import main as run_check

    return run_check()


if __name__ == "__main__":
    raise SystemExit(main())
