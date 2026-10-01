"""Local single-user path checks; not a sandbox against hostile same-UID code."""
from __future__ import annotations

import os
from pathlib import Path
import stat


def identity(path: Path, *, directory: bool = False) -> tuple[int, int]:
    metadata = path.lstat()
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(metadata.st_mode) or (
        hasattr(os, "getuid") and metadata.st_uid != os.getuid()
    ) or (not directory and metadata.st_nlink != 1):
        raise ValueError("STORAGE_PATH_UNSAFE")
    return metadata.st_dev, metadata.st_ino


def prepare_file(
    path: Path, *, directory_fd: int, expected_identity: tuple[int, int] | None,
) -> tuple[int, int]:
    """Create without following links and change permissions on the checked fd."""
    if not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("STORAGE_PATH_PLATFORM_UNSUPPORTED")
    flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        expected = identity(path)
        if expected_identity is not None and expected != expected_identity:
            raise ValueError("STORAGE_PATH_CHANGED")
    except FileNotFoundError:
        if expected_identity is not None:
            raise ValueError("STORAGE_PATH_CHANGED") from None
        expected = None
        flags |= os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(path.name, flags, 0o600, dir_fd=directory_fd)
    except OSError as exc:
        raise ValueError("STORAGE_PATH_UNSAFE") from exc
    try:
        opened = os.fstat(descriptor)
        current = (opened.st_dev, opened.st_ino)
        if current != identity(path) or (expected is not None and current != expected):
            raise ValueError("STORAGE_PATH_CHANGED")
        os.fchmod(descriptor, 0o600)
        return current
    finally:
        os.close(descriptor)


def prepare_directory(path: Path, expected: tuple[int, int] | None) -> tuple[int, int]:
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise ValueError("STORAGE_PATH_PLATFORM_UNSUPPORTED")
    try:
        if expected is None:
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
        current = identity(path, directory=True)
        if expected is not None and current != expected:
            raise ValueError("STORAGE_PATH_CHANGED")
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise ValueError("STORAGE_PATH_UNSAFE") from exc
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != current:
            raise ValueError("STORAGE_PATH_CHANGED")
        os.fchmod(descriptor, 0o700)
    finally:
        os.close(descriptor)
    return current
