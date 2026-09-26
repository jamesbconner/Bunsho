"""Single-user authentication: argon2 password check and JWT access/refresh tokens.

Every login gets a session id (``sid``) that all of its tokens share. Revoking the sid
(``AuthService.revoke``) ends the login's refresh token and every access token issued for it.
"""

from __future__ import annotations

import hmac
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from bunsho.config.service import AuthSettings
from bunsho.services.protocols import SessionRevocations
from bunsho.services.session_revocations import MemorySessionRevocations

_ALGORITHM = "HS256"
TokenType = Literal["access", "refresh"]


class AuthError(Exception):
    """Raised when credentials or a token are invalid."""


@dataclass(frozen=True, slots=True)
class TokenPair:
    """An access token and a refresh token."""

    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"  # noqa: S105 - OAuth2 scheme name, not a secret


@dataclass(frozen=True, slots=True)
class SessionClaims:
    """Who a valid token belongs to and which login session it is part of."""

    username: str
    sid: str


class AuthService:
    """Verifies the single configured user and issues JWTs tied to revocable sessions."""

    def __init__(
        self,
        settings: AuthSettings,
        *,
        clock: Callable[[], datetime] | None = None,
        revocations: SessionRevocations | None = None,
    ) -> None:
        """Create the service.

        Args:
            settings: Validated auth settings (argon2 hash, JWT secret, lifetimes).
            clock: Time source used for ``iat``/``exp`` (defaults to UTC now).
            revocations: Where revoked sessions are remembered (defaults to an in-memory set
                that forgets them when the process ends).
        """
        self._settings = settings
        self._clock = clock or (lambda: datetime.now(UTC))
        self._revocations: SessionRevocations = (
            revocations if revocations is not None else MemorySessionRevocations()
        )
        self._hasher = PasswordHash.recommended()
        # Checked when the username is wrong so a bad username costs as much as a bad password.
        self._dummy_hash = self._hasher.hash(uuid.uuid4().hex)

    def verify_credentials(self, username: str, password: str) -> bool:
        """Check a username and password in constant time.

        Returns:
            ``True`` only when both match the configured user.
        """
        user_ok = hmac.compare_digest(username.encode(), self._settings.username.encode())
        candidate = self._settings.password_hash if user_ok else self._dummy_hash
        try:
            password_ok = self._hasher.verify(password, candidate)
        except UnknownHashError:
            password_ok = False
        return user_ok and password_ok

    def _encode(self, username: str, sid: str, token_type: TokenType, lifetime: timedelta) -> str:
        issued = self._clock()
        claims: dict[str, Any] = {
            "sub": username,
            "sid": sid,
            "typ": token_type,
            "iat": issued,
            "exp": issued + lifetime,
            "jti": uuid.uuid4().hex,
        }
        return jwt.encode(claims, self._settings.jwt_secret, algorithm=_ALGORITHM)

    def issue_tokens(self, username: str, sid: str | None = None) -> TokenPair:
        """Issue an access and a refresh token for ``username``.

        Args:
            username: The user the tokens are for.
            sid: The session the tokens belong to. ``None`` starts a new login session;
                a refresh passes the session of the token it exchanged.
        """
        session_id = sid or uuid.uuid4().hex
        access_ttl = timedelta(minutes=self._settings.access_ttl_minutes)
        refresh_ttl = timedelta(days=self._settings.refresh_ttl_days)
        return TokenPair(
            access_token=self._encode(username, session_id, "access", access_ttl),
            refresh_token=self._encode(username, session_id, "refresh", refresh_ttl),
            expires_in=int(access_ttl.total_seconds()),
        )

    def _decode(self, token: str, expected: TokenType) -> SessionClaims:
        try:
            claims = jwt.decode(
                token,
                self._settings.jwt_secret,
                algorithms=[_ALGORITHM],
                options={"require": ["exp", "sub", "typ", "sid"]},
            )
        except jwt.InvalidTokenError as exc:
            raise AuthError("invalid or expired token") from exc
        if claims["typ"] != expected or claims["sub"] != self._settings.username:
            raise AuthError("wrong token type or subject")
        sid = str(claims["sid"])
        if self._revocations.is_revoked(sid):
            raise AuthError("session revoked")
        return SessionClaims(username=str(claims["sub"]), sid=sid)

    def authenticate(self, access_token: str) -> str:
        """Validate an access token.

        Returns:
            The authenticated username.

        Raises:
            AuthError: The token is invalid, expired, of the wrong type, for another user,
                without a session id, or its session was revoked.
        """
        return self._decode(access_token, "access").username

    def authenticate_session(self, access_token: str) -> SessionClaims:
        """Validate an access token and return its username and session id.

        Raises:
            AuthError: As for ``authenticate``.
        """
        return self._decode(access_token, "access")

    def refresh(self, refresh_token: str) -> TokenPair:
        """Exchange a valid refresh token for a new token pair of the same session.

        Raises:
            AuthError: The token is invalid, expired, of the wrong type, for another user,
                without a session id, or its session was revoked.
        """
        claims = self._decode(refresh_token, "refresh")
        return self.issue_tokens(claims.username, claims.sid)

    async def revoke(self, refresh_token: str) -> str:
        """End the login session behind ``refresh_token``.

        The session stays revoked for a full refresh lifetime from now: any token of it,
        including a newer refresh token held by another browser tab, expires within that time.

        Returns:
            The revoked session id.

        Raises:
            AuthError: The token does not verify, is expired, is not a refresh token, or its
                session was already revoked.
        """
        claims = self._decode(refresh_token, "refresh")
        lifetime = timedelta(days=self._settings.refresh_ttl_days)
        await self._revocations.revoke(claims.sid, self._clock() + lifetime)
        return claims.sid
