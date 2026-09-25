import asyncio
import logging

import pytest

from bunsho.orchestration.session_logout import logout_session
from bunsho.orchestration.session_sockets import SessionSockets
from bunsho.services.auth import AuthError, AuthService
from bunsho.services.session_revocations import MemorySessionRevocations
from tests.base import make_auth_settings

LOGGER = logging.getLogger("bunsho.tests")


class RecordingSocket:
    def __init__(self, on_close=None) -> None:  # type: ignore[no-untyped-def]
        self.closed_with: list[int] = []
        self._on_close = on_close

    async def close(self, code: int = 1000) -> None:
        if self._on_close is not None:
            self._on_close()
        self.closed_with.append(code)


def _auth() -> AuthService:
    return AuthService(make_auth_settings(), revocations=MemorySessionRevocations())


def test_logout_revokes_the_session_and_closes_its_sockets() -> None:
    auth, sockets = _auth(), SessionSockets()
    tokens = auth.issue_tokens("james")
    sid = auth.authenticate_session(tokens.access_token).sid
    socket = RecordingSocket()
    sockets.register(sid, socket)
    assert asyncio.run(
        logout_session(auth, sockets, tokens.refresh_token, logger=LOGGER, client="10.0.0.1")
    )
    assert socket.closed_with == [1008]
    with pytest.raises(AuthError):
        auth.authenticate(tokens.access_token)


def test_the_session_is_revoked_before_its_sockets_are_closed() -> None:
    """A client that reconnects the instant its socket closes must already be refused."""
    auth, sockets = _auth(), SessionSockets()
    tokens = auth.issue_tokens("james")
    sid = auth.authenticate_session(tokens.access_token).sid

    def assert_already_revoked() -> None:
        with pytest.raises(AuthError):
            auth.authenticate(tokens.access_token)

    socket = RecordingSocket(on_close=assert_already_revoked)
    sockets.register(sid, socket)
    asyncio.run(
        logout_session(auth, sockets, tokens.refresh_token, logger=LOGGER, client="10.0.0.1")
    )
    # The assertion above lives in the close callback, so prove the close really ran.
    assert socket.closed_with == [1008]


@pytest.mark.parametrize("token", ["garbage", "not.a.jwt"])
def test_a_token_that_does_not_verify_changes_nothing(token: str) -> None:
    auth, sockets = _auth(), SessionSockets()
    tokens = auth.issue_tokens("james")
    sid = auth.authenticate_session(tokens.access_token).sid
    socket = RecordingSocket()
    sockets.register(sid, socket)
    assert not asyncio.run(logout_session(auth, sockets, token, logger=LOGGER, client="x"))
    assert socket.closed_with == []
    assert auth.authenticate(tokens.access_token) == "james"


def test_logging_out_twice_is_harmless() -> None:
    auth, sockets = _auth(), SessionSockets()
    tokens = auth.issue_tokens("james")
    first = asyncio.run(
        logout_session(auth, sockets, tokens.refresh_token, logger=LOGGER, client="x")
    )
    second = asyncio.run(
        logout_session(auth, sockets, tokens.refresh_token, logger=LOGGER, client="x")
    )
    assert (first, second) == (True, False)


def test_the_log_line_never_contains_a_token(caplog: pytest.LogCaptureFixture) -> None:
    auth, sockets = _auth(), SessionSockets()
    tokens = auth.issue_tokens("james")
    logger = logging.getLogger("bunsho.tests.logout")
    with caplog.at_level(logging.DEBUG, logger=logger.name):
        asyncio.run(
            logout_session(auth, sockets, tokens.refresh_token, logger=logger, client="10.0.0.1")
        )
        asyncio.run(
            logout_session(auth, sockets, "secret-garbage", logger=logger, client="10.0.0.1")
        )
    assert "logout sid=" in caplog.text
    assert "logout_ignored" in caplog.text
    assert tokens.refresh_token not in caplog.text
    assert "secret-garbage" not in caplog.text
