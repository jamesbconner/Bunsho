"""Logout: end a login session on the server, then close its open sockets."""

from __future__ import annotations

import logging

from bunsho.orchestration.session_sockets import SessionSockets
from bunsho.services.auth import AuthError, AuthService


async def logout_session(
    auth: AuthService,
    sockets: SessionSockets,
    refresh_token: str,
    *,
    logger: logging.Logger,
    client: str,
) -> bool:
    """Revoke the session behind ``refresh_token`` and close its sockets.

    The session is revoked first, so a client that reconnects the moment its socket closes
    is already refused. A token that does not verify (garbage, expired, an access token,
    or an already revoked session) changes nothing; the caller answers the same either way,
    so the endpoint never reveals whether a token was valid.

    Args:
        auth: The service that owns token validity.
        sockets: The registry of open sockets.
        refresh_token: The refresh token the client is logging out with.
        logger: Receives ``logout`` (info) or ``logout_ignored`` (debug); never the token.
        client: The caller's address, for the log line.

    Returns:
        ``True`` when a session was revoked, ``False`` when the token was ignored.
    """
    try:
        sid = await auth.revoke(refresh_token)
    except AuthError:
        logger.debug("logout_ignored client=%s", client)
        return False
    closed = await sockets.close_session(sid, logger=logger)
    logger.info("logout sid=%s client=%s sockets_closed=%d", sid, client, closed)
    return True
