from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    count = 0
    for path in sorted((root / "demo_data").glob("synthetic_*.jsonl")):
        with path.open("r", encoding="utf-8") as handle:
            count += sum(1 for line in handle if line.strip())
    print(json.dumps({"index": "in_memory_demo", "synthetic_documents": count}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
