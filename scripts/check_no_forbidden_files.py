from __future__ import annotations

import re
import subprocess
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
    "api_key assignment": re.compile(r"\bapi[_-]?key\s*[:=]", re.IGNORECASE),
    "token assignment": re.compile(r"\btoken\s*[:=]", re.IGNORECASE),
    "secret assignment": re.compile(r"\bsecret\s*[:=]", re.IGNORECASE),
    "taiwan id": re.compile(r"(?<![A-Za-z0-9])[A-Z][12][0-9]{8}(?![0-9])"),
}

SKIP_DIR_PARTS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache"}
MAX_FILE_SIZE = 5 * 1024 * 1024
JUDGMENT_IDENTIFIER_PATTERN = re.compile(
    r"(?<![A-Za-z0-9,])(?P<court>[A-Z]{3,5}),(?P<year>[0-9]{2,3}),"
    r"(?P<case_type>[^,\s]{1,6}),(?P<number>[0-9]+),"
    r"(?P<date>[0-9]{8}),(?P<sequence>[0-9]+)(?![0-9,])"
)


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
    return match.group("court") in {"DEMO", "TSTV"} and (
        match.group("case_type") == "測" or match.group("date") >= "20990101"
    )


def _text_variants_from_bytes(raw: bytes) -> tuple[list[str], bool]:
    variants: list[str] = []
    utf8_failed = False

    def add_variant(text: str) -> None:
        if text and text not in variants:
            variants.append(text)
        stripped = text.replace("\x00", "")
        if stripped and stripped != text and stripped not in variants:
            variants.append(stripped)

    try:
        add_variant(raw.decode("utf-8"))
    except UnicodeDecodeError:
        utf8_failed = True
        add_variant(raw.decode("utf-8", errors="ignore"))

    if b"\x00" in raw or utf8_failed:
        for encoding in ("utf-16-le", "utf-16-be"):
            try:
                add_variant(raw.decode(encoding))
            except UnicodeDecodeError:
                continue

    return variants, utf8_failed


def _append_domain_violations(text: str, rel: Path, violations: list[str]) -> None:
    for match in JUDGMENT_IDENTIFIER_PATTERN.finditer(text):
        if not _is_allowed_synthetic_judgment_identifier(match):
            violations.append(f"forbidden judgment identifier: {rel}")


def find_forbidden_file_violations(root: Path) -> list[str]:
    root = root.resolve()
    violations: list[str] = []

    for path in _iter_files(root):
        if not path.exists() or not path.is_file():
            continue
        rel_parts = set(path.relative_to(root).parts)
        if rel_parts & SKIP_DIR_PARTS:
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

        raw = path.read_bytes()
        text_variants, utf8_failed = _text_variants_from_bytes(raw)
        if utf8_failed:
            violations.append(f"non-utf-8 text file: {rel}")

        for text in text_variants:
            for marker in FORBIDDEN_CONTENT_MARKERS:
                if marker in text:
                    violations.append(f"forbidden content marker {marker!r}: {rel}")

            for label, pattern in FORBIDDEN_CONTENT_PATTERNS.items():
                if pattern.search(text):
                    violations.append(f"forbidden content pattern {label}: {rel}")

            _append_domain_violations(text, rel, violations)

    return violations


def main() -> int:
    violations = find_forbidden_file_violations(Path("."))
    if violations:
        print("Forbidden files detected:", file=sys.stderr)
        for item in violations:
            print(f"- {item}", file=sys.stderr)
        return 1

    print("No forbidden files detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
