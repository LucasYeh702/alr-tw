from __future__ import annotations

import re
import sys
from pathlib import Path

FORBIDDEN_SUFFIXES = {
    ".sqlite",
    ".sqlite3",
    ".db",
    ".duckdb",
    ".parquet",
    ".arrow",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
}

FORBIDDEN_DIR_PARTS = {
    "cache",
    "logs",
    "archives",
    "raw_official",
    "official_cache",
    "tlr_cache",
    "hf_cache",
    "verified_archive",
    "vector_store",
    "chroma",
}

FORBIDDEN_FILENAMES = {
    ".env",
    "production_manifest.json",
    "rollback_manifest.json",
}

MACOS_USER_PATH_PREFIX = "/" + "Users/"

FORBIDDEN_CONTENT_MARKERS = {
    MACOS_USER_PATH_PREFIX,
    "LEGAL" + "_PRIVATE_",
}

FORBIDDEN_CONTENT_PATTERNS = {
    "local email address": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.local\b"),
    "local host name": re.compile(r"\b[A-Za-z0-9.-]+\.local\b"),
    "absolute macOS user path": re.compile(re.escape(MACOS_USER_PATH_PREFIX) + r"[^\s'\"`]+"),
    "private contract collection": re.compile(r"\b(?:private|legal)_contracts\b"),
}

SKIP_DIR_PARTS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache"}
MAX_FILE_SIZE = 5 * 1024 * 1024


def main() -> int:
    root = Path(".").resolve()
    violations: list[str] = []

    for path in root.rglob("*"):
        rel_parts = set(path.relative_to(root).parts)
        if rel_parts & SKIP_DIR_PARTS:
            continue
        if not path.is_file():
            continue

        rel = path.relative_to(root)

        if path.name in FORBIDDEN_FILENAMES:
            violations.append(f"forbidden filename: {rel}")

        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            violations.append(f"forbidden suffix: {rel}")

        if rel_parts & FORBIDDEN_DIR_PARTS:
            violations.append(f"forbidden directory: {rel}")

        if path.stat().st_size > MAX_FILE_SIZE:
            violations.append(f"file too large: {rel}")
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        for marker in FORBIDDEN_CONTENT_MARKERS:
            if marker in text:
                violations.append(f"forbidden content marker {marker!r}: {rel}")

        for label, pattern in FORBIDDEN_CONTENT_PATTERNS.items():
            if pattern.search(text):
                violations.append(f"forbidden content pattern {label}: {rel}")

    if violations:
        print("Forbidden files detected:", file=sys.stderr)
        for item in violations:
            print(f"- {item}", file=sys.stderr)
        return 1

    print("No forbidden files detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
