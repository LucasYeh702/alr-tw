from __future__ import annotations

import re
import subprocess
from pathlib import Path

MAX_TEXT_SCAN_BYTES = 5 * 1024 * 1024
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
    (re.compile(r"\b[A-Z][12][0-9]{8}\b"), "taiwan_id"),
    (re.compile(re.escape("/" + "Users" + "/")), "/" + "Users" + "/"),
)
JUDGMENT_IDENTIFIER_PATTERN = re.compile(
    r"\b(?P<court>[A-Z]{3,5}),(?P<year>[0-9]{2,3}),(?P<case_type>[^,\s]{1,6}),"
    r"(?P<number>[0-9]+),(?P<date>[0-9]{8}),(?P<sequence>[0-9]+)\b"
)


def _is_ignored(path: Path) -> bool:
    return any(part in {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"} for part in path.parts)


def _iter_files(root: Path) -> list[Path]:
    if (root / ".git").exists():
        try:
            output = subprocess.check_output(
                ["git", "-C", str(root), "ls-files", "-z"],
                text=False,
            )
        except (OSError, subprocess.CalledProcessError):
            pass
        else:
            return [root / raw.decode("utf-8") for raw in output.split(b"\0") if raw]
    return [path for path in root.rglob("*") if path.is_file()]


def _is_allowed_synthetic_judgment_identifier(match: re.Match[str]) -> bool:
    return match.group("court") in {"DEMO", "TSTV"} or match.group("case_type") == "測"


def find_public_boundary_violations(root: Path) -> list[str]:
    violations: list[str] = []
    root = root.resolve()
    for path in sorted(_iter_files(root)):
        if not path.exists():
            continue
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
        if path.stat().st_size > MAX_TEXT_SCAN_BYTES:
            violations.append(f"file too large: {relative}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            violations.append(f"non-utf-8 text file: {relative}")
            continue
        for pattern, label in FORBIDDEN_TEXT_PATTERNS:
            if pattern.search(text):
                violations.append(f"forbidden text {label}: {relative}")
        for match in JUDGMENT_IDENTIFIER_PATTERN.finditer(text):
            if not _is_allowed_synthetic_judgment_identifier(match):
                violations.append(f"forbidden text judgment_identifier: {relative}")
    return violations


def main() -> int:
    violations = find_public_boundary_violations(Path.cwd())
    for item in violations:
        print(item)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
