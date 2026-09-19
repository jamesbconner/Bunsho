"""Single-user authentication: argon2 password check and JWT access/refresh tokens."""

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


class AuthService:
    """Verifies the single configured user and issues stateless JWTs."""

    def __init__(
        self, settings: AuthSettings, *, clock: Callable[[], datetime] | None = None
    ) -> None:
        """Create the service.

        Args:
            settings: Validated auth settings (argon2 hash, JWT secret, lifetimes).
            clock: Time source used for ``iat``/``exp`` (defaults to UTC now).
        """
        self._settings = settings
        self._clock = clock or (lambda: datetime.now(UTC))
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

    def _encode(self, username: str, token_type: TokenType, lifetime: timedelta) -> str:
        issued = self._clock()
        claims: dict[str, Any] = {
            "sub": username,
            "typ": token_type,
            "iat": issued,
            "exp": issued + lifetime,
            "jti": uuid.uuid4().hex,
        }
        return jwt.encode(claims, self._settings.jwt_secret, algorithm=_ALGORITHM)

    def issue_tokens(self, username: str) -> TokenPair:
        """Issue a new access and refresh token for ``username``."""
        access_ttl = timedelta(minutes=self._settings.access_ttl_minutes)
        refresh_ttl = timedelta(days=self._settings.refresh_ttl_days)
        return TokenPair(
            access_token=self._encode(username, "access", access_ttl),
            refresh_token=self._encode(username, "refresh", refresh_ttl),
            expires_in=int(access_ttl.total_seconds()),
        )

    def _decode(self, token: str, expected: TokenType) -> str:
        try:
            claims = jwt.decode(
                token,
                self._settings.jwt_secret,
                algorithms=[_ALGORITHM],
                options={"require": ["exp", "sub", "typ"]},
            )
        except jwt.InvalidTokenError as exc:
            raise AuthError("invalid or expired token") from exc
        if claims["typ"] != expected or claims["sub"] != self._settings.username:
            raise AuthError("wrong token type or subject")
        return str(claims["sub"])

    def authenticate(self, access_token: str) -> str:
        """Validate an access token.

        Returns:
            The authenticated username.

        Raises:
            AuthError: The token is invalid, expired, of the wrong type or for another user.
        """
        return self._decode(access_token, "access")

    def refresh(self, refresh_token: str) -> TokenPair:
        """Exchange a valid refresh token for a new token pair.

        Raises:
            AuthError: The token is invalid, expired, of the wrong type or for another user.
        """
        return self.issue_tokens(self._decode(refresh_token, "refresh"))
