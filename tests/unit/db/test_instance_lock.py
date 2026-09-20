from pathlib import Path

import pytest

from bunsho.db.instance_lock import INSTANCE_LOCK_NAME, InstanceLock, InstanceLockedError


def test_the_lock_file_lives_in_the_data_folder(tmp_path: Path) -> None:
    lock = InstanceLock(tmp_path / "data")
    lock.acquire()
    try:
        assert lock.path == tmp_path / "data" / INSTANCE_LOCK_NAME
        assert lock.path.exists()
    finally:
        lock.release()


def test_a_second_lock_on_the_same_folder_is_refused_until_the_first_is_released(
    tmp_path: Path,
) -> None:
    first = InstanceLock(tmp_path)
    second = InstanceLock(tmp_path)
    first.acquire()
    try:
        with pytest.raises(InstanceLockedError, match="already using"):
            second.acquire()
    finally:
        first.release()
    second.acquire()
    second.release()


def test_release_is_idempotent(tmp_path: Path) -> None:
    lock = InstanceLock(tmp_path)
    lock.acquire()
    lock.release()
    lock.release()


def test_locks_on_different_folders_do_not_conflict(tmp_path: Path) -> None:
    one, two = InstanceLock(tmp_path / "a"), InstanceLock(tmp_path / "b")
    one.acquire()
    two.acquire()
    one.release()
    two.release()
