"""Scan actual release distributions, not just the checkout used to build them."""
from __future__ import annotations

import argparse
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import sys
import tarfile
import tempfile
import zipfile

MAX_MEMBER_BYTES = 5 * 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024
MAX_MEMBERS = 10000
HIDDEN_SCAN_PATHS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache"}


def _target(root: Path, name: str) -> Path:
    path = PurePosixPath(name)
    if (
        not name or "\\" in name or path.is_absolute()
        or any(part in {"..", "."} for part in name.rstrip("/").split("/"))
        or set(path.parts) & HIDDEN_SCAN_PATHS
    ):
        raise ValueError(f"unsafe or scan-excluded archive path: {name}")
    return root.joinpath(*path.parts)


def check_artifact(artifact: Path, version: str) -> dict[str, object]:
    # Import the same checkout's guards, regardless of an installed package.
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo / "src"))
    sys.path.insert(0, str(repo / "scripts"))
    from alr_tw.scripts.check_public_boundary import find_public_boundary_violations
    from check_no_forbidden_files import find_forbidden_file_violations

    expected_wheel = f"alr_tw-{version}-py3-none-any.whl"
    expected_sdist = f"alr_tw-{version}.tar.gz"
    if artifact.name not in {expected_wheel, expected_sdist}:
        raise ValueError(f"unexpected artifact name: {artifact.name}")
    if artifact.stat().st_size > MAX_TOTAL_BYTES:
        raise ValueError("compressed artifact too large")

    count = 0
    total = 0
    seen: set[str] = set()
    with tempfile.TemporaryDirectory(prefix="alr-tw-artifact-") as temp:
        root = Path(temp)

        def accept(name: str, size: int, is_directory: bool) -> Path:
            nonlocal count, total
            target = _target(root, name)
            key = target.relative_to(root).as_posix().casefold()
            if key in seen:
                raise ValueError(f"duplicate archive path: {name}")
            seen.add(key)
            count += 1
            total += size
            if size < 0 or size > MAX_MEMBER_BYTES or total > MAX_TOTAL_BYTES or count > MAX_MEMBERS:
                raise ValueError("archive exceeds scan budget")
            if is_directory:
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
            return target

        if artifact.name == expected_wheel:
            scan_root = root
            with zipfile.ZipFile(artifact) as archive:
                for member in archive.infolist():
                    mode = member.external_attr >> 16
                    if stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}:
                        raise ValueError(f"non-regular archive member: {member.filename}")
                    target = accept(member.filename, member.file_size, member.is_dir())
                    if not member.is_dir():
                        with archive.open(member) as stream:
                            payload = stream.read(MAX_MEMBER_BYTES + 1)
                        if len(payload) != member.file_size:
                            raise ValueError("archive member size mismatch")
                        target.write_bytes(payload)
            metadata = root / f"alr_tw-{version}.dist-info" / "METADATA"
        else:
            scan_root = root / f"alr_tw-{version}"
            with tarfile.open(artifact, "r:gz") as archive:
                for member in archive:
                    if not (member.isfile() or member.isdir()):
                        raise ValueError(f"non-regular archive member: {member.name}")
                    if PurePosixPath(member.name).parts[:1] != (f"alr_tw-{version}",):
                        raise ValueError("sdist member outside the named package root")
                    target = accept(member.name, member.size, member.isdir())
                    if member.isfile():
                        stream = archive.extractfile(member)
                        if stream is None:
                            raise ValueError("unreadable archive member")
                        with stream:
                            payload = stream.read(MAX_MEMBER_BYTES + 1)
                        if len(payload) != member.size:
                            raise ValueError("archive member size mismatch")
                        target.write_bytes(payload)
            metadata = root / f"alr_tw-{version}" / "PKG-INFO"

        fields = BytesParser().parsebytes(metadata.read_bytes())
        if fields.get_all("Name") != ["alr-tw"] or fields.get_all("Version") != [version]:
            raise ValueError("distribution metadata identity mismatch")
        violations = find_forbidden_file_violations(scan_root) + find_public_boundary_violations(scan_root)
        if violations:
            raise ValueError("; ".join(violations))
    return {
        "artifact": artifact.name, "version": version, "members": count,
        "expanded_bytes": total, "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "boundary_checks": "passed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("artifacts", nargs=2, type=Path)
    args = parser.parse_args()
    if len({item.name for item in args.artifacts}) != 2:
        parser.error("provide exactly one wheel and one sdist")
    try:
        results = [check_artifact(item, args.version) for item in args.artifacts]
    except (OSError, ValueError, EOFError, RuntimeError, tarfile.TarError, zipfile.BadZipFile) as exc:
        print(f"Artifact check failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
