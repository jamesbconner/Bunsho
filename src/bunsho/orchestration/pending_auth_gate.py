"""A cap on WebSockets that are connected but have not authenticated yet."""

from __future__ import annotations

MAX_PENDING_AUTH = 16
"""Most unauthenticated sockets allowed at once; a real client authenticates in milliseconds."""


class PendingAuthGate:
    """Counts the sockets in the authentication window and refuses entry past a limit.

    A socket takes a slot with ``try_enter`` before it is accepted and gives it back with
    ``leave`` as soon as authentication resolves (success, failure, timeout or disconnect), so
    an authenticated stream never holds one. Used only from the event loop, so it needs no
    locking.
    """

    def __init__(self, limit: int = MAX_PENDING_AUTH) -> None:
        """Create a gate that admits at most ``limit`` sockets at a time.

        Args:
            limit: Most sockets allowed in the authentication window at once.

        Raises:
            ValueError: ``limit`` is below 1.
        """
        if limit < 1:
            raise ValueError(f"limit must be at least 1, got {limit}")
        self._limit = limit
        self._pending = 0

    @property
    def pending(self) -> int:
        """How many sockets currently hold a slot."""
        return self._pending

    def try_enter(self) -> bool:
        """Take a slot if one is free.

        Returns:
            ``True`` if the caller now holds a slot and must call ``leave``; ``False`` if the
            gate is full and nothing was taken.
        """
        if self._pending >= self._limit:
            return False
        self._pending += 1
        return True

    def leave(self) -> None:
        """Give a slot back; a call with no slot held is ignored."""
        self._pending = max(0, self._pending - 1)
