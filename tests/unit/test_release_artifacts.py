from __future__ import annotations

import importlib.util
import io
from pathlib import Path
import tarfile
import zipfile

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_release_artifacts.py"
SPEC = importlib.util.spec_from_file_location("release_artifacts", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)
METADATA = b"Name: alr-tw\nVersion: 0.12.0\n"


def _wheel(tmp_path: Path, name: str = "alr_tw/demo.py", data: bytes = b"# synthetic\n") -> Path:
    wheel = tmp_path / "alr_tw-0.12.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("alr_tw-0.12.0.dist-info/METADATA", METADATA)
        archive.writestr(name, data)
    return wheel


def test_release_artifact_checks_safe_wheel_and_sdist(tmp_path: Path):
    assert CHECKER.check_artifact(_wheel(tmp_path), "0.12.0")["boundary_checks"] == "passed"
    sdist = tmp_path / "alr_tw-0.12.0.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        member = tarfile.TarInfo("alr_tw-0.12.0/PKG-INFO")
        member.size = len(METADATA)
        archive.addfile(member, io.BytesIO(METADATA))
    assert CHECKER.check_artifact(sdist, "0.12.0")["boundary_checks"] == "passed"


@pytest.mark.parametrize("name", ["../escape", "/escape", ".git/hidden", "reviews/internal.md"])
def test_release_artifact_rejects_unsafe_or_private_paths(tmp_path: Path, name: str):
    with pytest.raises(ValueError):
        CHECKER.check_artifact(_wheel(tmp_path, name), "0.12.0")


def test_release_artifact_rejects_secret_and_wrong_version(tmp_path: Path):
    with pytest.raises(ValueError, match="token"):
        CHECKER.check_artifact(_wheel(tmp_path, data=b"to" + b"ken = 'synthetic'"), "0.12.0")
    with pytest.raises(ValueError, match="artifact name"):
        CHECKER.check_artifact(_wheel(tmp_path), "0.12.1")


def test_release_artifact_rejects_tar_link(tmp_path: Path):
    sdist = tmp_path / "alr_tw-0.12.0.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        member = tarfile.TarInfo("link")
        member.type = tarfile.SYMTYPE
        member.linkname = "/escape"
        archive.addfile(member)
    with pytest.raises(ValueError, match="non-regular"):
        CHECKER.check_artifact(sdist, "0.12.0")


@pytest.mark.parametrize("name", [
    "data/legal_public/demo.txt", "data/legal_private/demo.txt", "reviews/internal.md",
    "REVIEW_GOVERNANCE.md", "../outside.txt",
])
def test_sdist_boundaries_use_package_root(tmp_path: Path, name: str):
    sdist = tmp_path / "alr_tw-0.12.0.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        for relative, data in [("PKG-INFO", METADATA), (name, b"synthetic")]:
            member = tarfile.TarInfo(f"alr_tw-0.12.0/{relative}")
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    with pytest.raises(ValueError):
        CHECKER.check_artifact(sdist, "0.12.0")


def test_sdist_rejects_file_outside_named_package(tmp_path: Path):
    sdist = tmp_path / "alr_tw-0.12.0.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        for name, data in [("alr_tw-0.12.0/PKG-INFO", METADATA), ("outside.txt", b"synthetic")]:
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    with pytest.raises(ValueError):
        CHECKER.check_artifact(sdist, "0.12.0")
