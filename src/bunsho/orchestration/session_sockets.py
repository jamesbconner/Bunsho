"""Which authenticated WebSockets belong to which login session."""

from __future__ import annotations

import logging
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

    async def close_session(
        self,
        sid: str,
        code: int = POLICY_VIOLATION,
        *,
        logger: logging.Logger | None = None,
    ) -> int:
        """Close every socket of session ``sid``, whatever happens to any one of them.

        A socket that is already closed or whose client vanished is skipped silently. Any
        other ``Exception`` from a close is logged as a warning (its type name only, never its
        text) and the loop carries on, so a failing socket never keeps the others open.
        Cancellation is not an ``Exception`` and still propagates.

        Args:
            sid: The session whose sockets to close.
            code: The WebSocket close code to send.
            logger: Receives ``session_socket_close_failed``; defaults to the ``bunsho`` logger.

        Returns:
            How many sockets it asked to close, including any whose close failed.
        """
        log = logger or logging.getLogger("bunsho")
        sockets = list(self._by_sid.get(sid, ()))
        for socket in sockets:
            try:
                with suppress(RuntimeError, WebSocketDisconnect):
                    await socket.close(code=code)
            except Exception as exc:
                log.warning("session_socket_close_failed error_type=%s", type(exc).__name__)
        return len(sockets)
