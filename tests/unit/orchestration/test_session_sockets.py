import asyncio
import logging

import pytest
from starlette.websockets import WebSocketDisconnect

from bunsho.orchestration.session_sockets import SessionSockets


class FakeSocket:
    """Records the close codes it was given; can be made to fail like a vanished client."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.closed_with: list[int] = []
        self._error = error

    async def close(self, code: int = 1000) -> None:
        if self._error is not None:
            raise self._error
        self.closed_with.append(code)


def test_close_session_closes_only_that_sessions_sockets_with_1008() -> None:
    sockets = SessionSockets()
    mine, also_mine, other = FakeSocket(), FakeSocket(), FakeSocket()
    sockets.register("sid-a", mine)
    sockets.register("sid-a", also_mine)
    sockets.register("sid-b", other)
    assert asyncio.run(sockets.close_session("sid-a")) == 2
    assert mine.closed_with == [1008]
    assert also_mine.closed_with == [1008]
    assert other.closed_with == []


def test_close_session_for_an_unknown_session_does_nothing() -> None:
    assert asyncio.run(SessionSockets().close_session("nobody")) == 0


def test_a_socket_that_is_already_gone_does_not_stop_the_others() -> None:
    sockets = SessionSockets()
    gone = FakeSocket(error=RuntimeError("Cannot call send once a close message has been sent."))
    dropped = FakeSocket(error=WebSocketDisconnect(1006))
    alive = FakeSocket()
    for socket in (gone, dropped, alive):
        sockets.register("sid-a", socket)
    assert asyncio.run(sockets.close_session("sid-a")) == 3
    assert alive.closed_with == [1008]


def test_an_unexpected_close_error_is_logged_by_type_and_the_others_still_close(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sockets = SessionSockets()
    failing = FakeSocket(error=OSError("boom"))
    leaky = FakeSocket(error=ValueError("secret-detail"))
    healthy = FakeSocket()
    for socket in (failing, leaky, healthy):
        sockets.register("sid-a", socket)
    with caplog.at_level(logging.WARNING, logger="bunsho"):
        assert asyncio.run(sockets.close_session("sid-a")) == 3
    assert healthy.closed_with == [1008]
    assert "error_type=OSError" in caplog.text
    assert "error_type=ValueError" in caplog.text
    assert "secret-detail" not in caplog.text
    assert "boom" not in caplog.text


def test_cancellation_during_a_close_is_not_swallowed() -> None:
    sockets = SessionSockets()
    sockets.register("sid-a", FakeSocket(error=asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(sockets.close_session("sid-a"))


def test_unregister_forgets_a_socket_and_an_empty_session() -> None:
    sockets = SessionSockets()
    socket = FakeSocket()
    sockets.register("sid-a", socket)
    assert (sockets.count(), sockets.count("sid-a")) == (1, 1)
    sockets.unregister("sid-a", socket)
    assert (sockets.count(), sockets.count("sid-a")) == (0, 0)
    assert asyncio.run(sockets.close_session("sid-a")) == 0


def test_registering_twice_counts_once_and_unregistering_a_stranger_is_harmless() -> None:
    sockets = SessionSockets()
    socket = FakeSocket()
    sockets.register("sid-a", socket)
    sockets.register("sid-a", socket)
    assert sockets.count("sid-a") == 1
    sockets.unregister("sid-b", socket)
    sockets.unregister("sid-a", FakeSocket())
    assert sockets.count("sid-a") == 1
