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
    (re.compile(r"\bapi[_-]?key\s*[:=]", re.IGNORECASE), "api_key"),
    (re.compile(r"\btoken\s*[:=]", re.IGNORECASE), "token"),
    (re.compile(r"\bsecret\s*[:=]", re.IGNORECASE), "secret"),
    (re.compile(r"(?<![A-Za-z0-9])[A-Z][12][0-9]{8}(?![0-9])"), "taiwan_id"),
    (re.compile(re.escape("/" + "Users" + "/")), "/" + "Users" + "/"),
)
JUDGMENT_IDENTIFIER_PATTERN = re.compile(
    r"(?<![A-Za-z0-9,])(?P<court>[A-Z]{3,5}),(?P<year>[0-9]{2,3}),"
    r"(?P<case_type>[^,\s]{1,6}),(?P<number>[0-9]+),"
    r"(?P<date>[0-9]{8}),(?P<sequence>[0-9]+)(?![0-9,])"
)


def _is_ignored(path: Path) -> bool:
    return any(part in {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"} for part in path.parts)


def _iter_files(root: Path) -> list[Path]:
    if (root / ".git").exists():
        try:
            output = subprocess.check_output(
                [
                    "git",
                    "-C",
                    str(root),
                    "ls-files",
                    "-z",
                    "--cached",
                    "--others",
                    "--exclude-standard",
                ],
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
        raw = path.read_bytes()
        text_variants, utf8_failed = _text_variants_from_bytes(raw)
        if utf8_failed:
            violations.append(f"non-utf-8 text file: {relative}")

        for text in text_variants:
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
