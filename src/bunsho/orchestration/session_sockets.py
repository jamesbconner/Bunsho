"""Which authenticated WebSockets belong to which login session."""

from __future__ import annotations

from contextlib import suppress
from typing import Protocol

from starlette.websockets import WebSocketDisconnect

POLICY_VIOLATION = 1008
"""The close code the task stream already uses for authentication failures."""


class ClosableSocket(Protocol):
    """The slice of a WebSocket this registry uses."""

    async def close(self, code: int = 1000) -> None:
        """Close the connection with ``code``."""
        ...


class SessionSockets:
    """A registry of open, authenticated sockets keyed by session id.

    Used only from the event loop, so it needs no locking. Sockets are registered after
    they authenticate and unregistered when their handler ends.
    """

    def __init__(self) -> None:
        """Create an empty registry."""
        self._by_sid: dict[str, set[ClosableSocket]] = {}

    def register(self, sid: str, socket: ClosableSocket) -> None:
        """Remember ``socket`` as belonging to session ``sid``."""
        self._by_sid.setdefault(sid, set()).add(socket)

    def unregister(self, sid: str, socket: ClosableSocket) -> None:
        """Forget ``socket``; unknown sockets and sessions are ignored."""
        sockets = self._by_sid.get(sid)
        if sockets is None:
            return
        sockets.discard(socket)
        if not sockets:
            del self._by_sid[sid]

    def count(self, sid: str | None = None) -> int:
        """Return how many sockets are registered, for one session or for all."""
        if sid is not None:
            return len(self._by_sid.get(sid, ()))
        return sum(len(sockets) for sockets in self._by_sid.values())

    async def close_session(self, sid: str, code: int = POLICY_VIOLATION) -> int:
        """Close every socket of session ``sid``.

        A socket that is already closed or whose client vanished is skipped silently, so one
        dead socket never keeps the others open.

        Returns:
            How many sockets it asked to close.
        """
        sockets = list(self._by_sid.get(sid, ()))
        for socket in sockets:
            with suppress(RuntimeError, WebSocketDisconnect):
                await socket.close(code=code)
        return len(sockets)
