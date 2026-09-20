"""In-memory sliding-window throttle for failed logins."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

_PRUNE_THRESHOLD = 1024


class LoginThrottle:
    """Blocks a client key after too many recent failures."""

    def __init__(
        self,
        *,
        max_failures: int = 5,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Create a throttle.

        Args:
            max_failures: Failures inside the window that trigger blocking.
            window_seconds: Length of the sliding window.
            clock: Monotonic time source in seconds.
        """
        self._max = max_failures
        self._window = window_seconds
        self._clock = clock
        self._failures: dict[str, deque[float]] = {}

    def _recent(self, key: str) -> deque[float]:
        failures = self._failures.get(key)
        if failures is None:
            return deque()
        horizon = self._clock() - self._window
        while failures and failures[0] <= horizon:
            failures.popleft()
        if not failures:
            del self._failures[key]
        return failures

    def retry_after(self, key: str) -> float | None:
        """Seconds until ``key`` may try again, or ``None`` when it is allowed now."""
        failures = self._recent(key)
        if len(failures) < self._max:
            return None
        return max(0.0, failures[0] + self._window - self._clock())

    def record_failure(self, key: str) -> None:
        """Record one failed attempt for ``key``."""
        if len(self._failures) > _PRUNE_THRESHOLD:
            for stale in list(self._failures):
                self._recent(stale)
        self._failures.setdefault(key, deque()).append(self._clock())

    def reset(self, key: str) -> None:
        """Forget ``key`` (after a successful login)."""
        self._failures.pop(key, None)
