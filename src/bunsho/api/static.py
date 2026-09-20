"""Serving the built frontend: hashed assets, the single-page-app shell and deep-link fallback."""

from __future__ import annotations

from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

INDEX = "index.html"
_IMMUTABLE = "public, max-age=31536000, immutable"
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


def _posix(path: str) -> str:
    """The mount-relative path with forward slashes (Starlette hands over OS separators)."""
    return path.replace("\\", "/")


def _is_client_route(path: str) -> bool:
    """Whether the single-page app should answer this path: not an API path, no file extension."""
    if path == "api" or path.startswith("api/"):
        return False
    return "." not in path.rsplit("/", 1)[-1]


def _decorate(response: Response, path: str) -> None:
    """Cache hashed assets forever, never cache the shell, and add the security headers."""
    response.headers["Cache-Control"] = _IMMUTABLE if path.startswith("assets/") else "no-cache"
    for name, value in _SECURITY_HEADERS.items():
        response.headers[name] = value


class SPAStaticFiles(StaticFiles):
    """``StaticFiles`` for a single-page app.

    An unknown path without a file extension gets ``index.html`` so a deep link such as
    ``/build`` survives a page reload; unknown API paths and missing files stay 404.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        """Serve ``path`` from the build folder, falling back to the app shell for client routes.

        Args:
            path: The path relative to the mount (``""`` for the root).
            scope: The ASGI scope.

        Returns:
            The file response with cache and security headers.

        Raises:
            HTTPException: 404 for unknown API paths and for missing files.
        """
        served = _posix(path)  # on Windows Starlette passes "api\nothing", not "api/nothing"
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or not _is_client_route(served):
                raise
            response = await super().get_response(INDEX, scope)
            served = INDEX
        _decorate(response, served)
        return response
