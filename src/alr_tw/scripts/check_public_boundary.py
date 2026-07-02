from __future__ import annotations

import re
from pathlib import Path

FORBIDDEN_DIR_PARTS = {
    ".cache",
    "cache",
    "verified_cache",
    "chroma",
}
FORBIDDEN_PATH_PREFIXES = (
    "data/legal_public",
    "data/legal_private",
)
FORBIDDEN_SUFFIXES = (".sqlite", ".db", ".jsonl.gz", ".rar", ".log")
FORBIDDEN_TEXT_PATTERNS = (
    (re.compile(r"api[_-]?key\s*[:=]", re.IGNORECASE), "api_key"),
    (re.compile(r"token\s*[:=]", re.IGNORECASE), "token"),
    (re.compile(r"secret\s*[:=]", re.IGNORECASE), "secret"),
    (re.compile(re.escape("/" + "Users" + "/")), "/" + "Users" + "/"),
)


def _is_ignored(path: Path) -> bool:
    return any(part in {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"} for part in path.parts)


def find_public_boundary_violations(root: Path) -> list[str]:
    violations: list[str] = []
    for path in sorted(root.rglob("*")):
        if _is_ignored(path) or not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        directory_parts = set(path.relative_to(root).parts[:-1])
        if directory_parts & FORBIDDEN_DIR_PARTS or any(
            relative == prefix or relative.startswith(prefix + "/")
            for prefix in FORBIDDEN_PATH_PREFIXES
        ):
            violations.append(f"forbidden path: {relative}")
        if path.suffix in FORBIDDEN_SUFFIXES or relative.endswith(FORBIDDEN_SUFFIXES):
            violations.append(f"forbidden file type: {relative}")
        if path.stat().st_size <= 1_000_000:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pattern, label in FORBIDDEN_TEXT_PATTERNS:
                if pattern.search(text):
                    violations.append(f"forbidden text {label}: {relative}")
    return violations


def main() -> int:
    violations = find_public_boundary_violations(Path.cwd())
    for item in violations:
        print(item)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
