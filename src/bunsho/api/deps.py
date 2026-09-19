"""FastAPI dependencies: shared services and the authenticated user."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.requests import HTTPConnection

from bunsho.api.services import Services
from bunsho.services.auth import AuthError

_bearer = HTTPBearer(auto_error=False)


def get_services(connection: HTTPConnection) -> Services:
    """Return the service container (works for HTTP requests and WebSockets)."""
    services: Services = connection.app.state.services
    return services


ServicesDep = Annotated[Services, Depends(get_services)]


def require_user(
    services: ServicesDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    """Validate the bearer access token and return the username.

    For HTTP routes only. WebSocket routes authenticate with a first-message token
    (see the ws router), because ``HTTPBearer`` needs a ``Request``.

    Raises:
        HTTPException: 401 when the token is missing, invalid or expired.
    """
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        return services.auth.authenticate(credentials.credentials)
    except AuthError as exc:
        raise unauthorized from exc


CurrentUser = Annotated[str, Depends(require_user)]
