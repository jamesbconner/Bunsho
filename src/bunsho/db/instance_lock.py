"""One running instance per data folder."""

from __future__ import annotations

from pathlib import Path

from filelock import FileLock, Timeout

INSTANCE_LOCK_NAME = ".bunsho.instance.lock"


class InstanceLockedError(RuntimeError):
    """Another process already holds the data folder."""


class InstanceLock:
    """An OS-level exclusive lock on the data folder, held for the process lifetime.

    Two instances on one volume would both start; the startup temp-file sweep of one could
    then delete the other's in-flight build file, and both would write ``progress.db``.
    """

    def __init__(self, data_dir: Path) -> None:
        """Create the lock (nothing is acquired yet).

        Args:
            data_dir: The data folder (created on ``acquire`` if missing).
        """
        self._path = data_dir / INSTANCE_LOCK_NAME
        # Process-wide, not per thread: acquire and release may run on different threads.
        self._lock = FileLock(str(self._path), thread_local=False)

    @property
    def path(self) -> Path:
        """The lock file."""
        return self._path

    def acquire(self) -> None:
        """Take the lock without waiting.

        Raises:
            InstanceLockedError: Another process holds it.
            OSError: The lock file cannot be created (for example a read-only folder).
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._lock.acquire(timeout=0)
        except Timeout as exc:
            raise InstanceLockedError(
                f"Another Bunshō instance is already using the data folder {self._path.parent} "
                f"(lock file {self._path}). Run one instance per data volume: stop the other "
                "instance, or point this one at a different folder."
            ) from exc

    def release(self) -> None:
        """Release the lock; safe to call when it is not held."""
        self._lock.release()
