"""Login and token refresh."""

from __future__ import annotations

import asyncio
import math

from fastapi import APIRouter, HTTPException, Request, status

from bunsho.api.deps import ServicesDep
from bunsho.api.schemas import LoginRequest, RefreshRequest, TokenResponse
from bunsho.services.auth import AuthError, TokenPair

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(tokens: TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, services: ServicesDep) -> TokenResponse:
    """Exchange the configured username and password for tokens.

    Raises:
        HTTPException: 429 while the client address is throttled, 401 for bad credentials.
    """
    client = request.client.host if request.client else "unknown"
    wait = services.throttle.retry_after(client)
    if wait is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many failed logins; try again later",
            headers={"Retry-After": str(math.ceil(wait))},
        )
    # Reserve the attempt before awaiting, so concurrent requests cannot all pass the
    # check above while the slow argon2 verification runs. A success clears it again.
    services.throttle.record_failure(client)
    valid = await asyncio.to_thread(services.auth.verify_credentials, body.username, body.password)
    if not valid:
        services.ctx.logger.warning("login_failed client=%s", client)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    services.throttle.reset(client)
    return _token_response(services.auth.issue_tokens(services.config.auth.username))


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, services: ServicesDep) -> TokenResponse:
    """Exchange a refresh token for a new token pair.

    Raises:
        HTTPException: 401 when the token is invalid, expired or not a refresh token.
    """
    try:
        return _token_response(services.auth.refresh(body.refresh_token))
    except AuthError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
