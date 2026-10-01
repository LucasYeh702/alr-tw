"""Temporary, synthetic paths only; never exercise user-owned databases."""
from pathlib import Path
import stat
import os

import pytest

from alr_tw.storage.sqlite_store import SqliteStore


def test_storage_rejects_root_symlink_without_changing_target(tmp_path):
    target = tmp_path / "target"
    target.mkdir(mode=0o755)
    before = stat.S_IMODE(target.stat().st_mode)
    link = tmp_path / "state"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="STORAGE_PATH"):
        SqliteStore(link)
    assert stat.S_IMODE(target.stat().st_mode) == before
    assert list(target.iterdir()) == []


@pytest.mark.parametrize("suffix", ["", "-wal", "-shm", "-journal"])
def test_storage_rejects_linked_database_family(tmp_path, suffix):
    root = tmp_path / "state"
    root.mkdir()
    target = tmp_path / "target"
    target.write_bytes(b"synthetic sentinel")
    before = target.read_bytes(), target.stat().st_mode
    (root / f"alr_tw_storage.sqlite3{suffix}").symlink_to(target)
    with pytest.raises(ValueError, match="STORAGE_PATH"):
        SqliteStore(root)
    assert (target.read_bytes(), target.stat().st_mode) == before


def test_storage_rejects_replaced_root_before_purge(tmp_path):
    root = tmp_path / "state"
    store = SqliteStore(root)
    root.rename(tmp_path / "original")
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    sentinel = replacement / "alr_tw_storage.sqlite3"
    sentinel.write_text("keep")
    root.symlink_to(replacement, target_is_directory=True)
    with pytest.raises(ValueError, match="STORAGE_PATH"):
        store.purge_all()
    assert sentinel.read_text() == "keep"


def test_normal_storage_reopens_and_purges(tmp_path: Path):
    root = tmp_path / "state"
    SqliteStore(root)
    store = SqliteStore(root)
    assert store.cleanup_expired().expired_runs == 0
    assert store.purge_all().success
    assert not store.database_path.exists()


def test_linked_temporary_directory_is_rejected(tmp_path):
    root = tmp_path / "state"
    store = SqliteStore(root)
    target = tmp_path / "target"
    target.mkdir()
    (target / "keep").write_text("sentinel")
    store.temp_path.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="STORAGE_PATH"):
        store.purge_all()
    assert (target / "keep").read_text() == "sentinel"


def test_database_replaced_during_open_is_not_initialized(tmp_path, monkeypatch):
    import alr_tw.storage.sqlite_store as module

    root = tmp_path / "state"
    store = SqliteStore(root)
    real_connect = module.sqlite3.connect

    def replaced_connect(*args, **kwargs):
        store.database_path.rename(root / "old")
        store.database_path.write_bytes(b"")
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(module.sqlite3, "connect", replaced_connect)
    with pytest.raises(ValueError, match="STORAGE_PATH_CHANGED"):
        store.cleanup_expired()
    assert store.database_path.read_bytes() == b""


def test_hardlinked_database_is_rejected(tmp_path):
    root = tmp_path / "state"
    root.mkdir()
    target = tmp_path / "target"
    target.write_bytes(b"sentinel")
    os.link(target, root / "alr_tw_storage.sqlite3")
    with pytest.raises(ValueError, match="STORAGE_PATH"):
        SqliteStore(root)
    assert target.read_bytes() == b"sentinel"


def test_non_owner_is_rejected_before_chmod(tmp_path, monkeypatch):
    root = tmp_path / "state"
    root.mkdir(mode=0o755)
    before = root.stat().st_mode
    monkeypatch.setattr(os, "getuid", lambda: root.stat().st_uid + 1)
    with pytest.raises(ValueError, match="STORAGE_PATH"):
        SqliteStore(root)
    assert root.stat().st_mode == before


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO test")
def test_fifo_database_is_rejected_without_blocking(tmp_path):
    root = tmp_path / "state"
    root.mkdir()
    os.mkfifo(root / "alr_tw_storage.sqlite3")
    with pytest.raises(ValueError, match="STORAGE_PATH"):
        SqliteStore(root)


def test_purge_removes_real_temporary_files(tmp_path):
    store = SqliteStore(tmp_path / "state")
    store.temp_path.mkdir()
    (store.temp_path / "synthetic.txt").write_text("temporary")
    assert store.purge_all().success
    assert not store.temp_path.exists()


def test_database_replaced_between_path_check_and_open_is_not_adopted(tmp_path, monkeypatch):
    import alr_tw.storage.sqlite_store as module

    store = SqliteStore(tmp_path / "state")
    original = module.prepare_file

    def replace_before_open(path, **kwargs):
        path.rename(path.with_name("old-database"))
        path.write_bytes(b"")
        return original(path, **kwargs)

    monkeypatch.setattr(module, "prepare_file", replace_before_open)
    with pytest.raises(ValueError, match="STORAGE_PATH_CHANGED"):
        store.cleanup_expired()
    assert store.database_path.read_bytes() == b""


def test_dangling_temp_link_is_rejected_before_purge(tmp_path):
    store = SqliteStore(tmp_path / "state")
    store.temp_path.symlink_to(tmp_path / "missing", target_is_directory=True)
    with pytest.raises(ValueError, match="STORAGE_PATH_UNSAFE"):
        store.purge_all()
    assert store.database_path.exists()
