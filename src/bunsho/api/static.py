"""Serving the built frontend: assets, the nonce-rendered app shell and the deep-link fallback."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from starlette.exceptions import HTTPException
from starlette.responses import HTMLResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from bunsho.api.csp import NONCE_SCOPE_KEY, generate_nonce
from bunsho.frontend_shell import CSP_NONCE_PLACEHOLDER, INDEX_FILE, read_shell

INDEX = INDEX_FILE
_IMMUTABLE = "public, max-age=31536000, immutable"
_SHELL_PATHS = frozenset({"", ".", INDEX})
"""How Starlette names the root and the index file (the root arrives as ``.``)."""
_READ_METHODS = frozenset({"GET", "HEAD"})
"""The only methods the shell answers; ``StaticFiles`` answers anything else with a 405."""


def _posix(path: str) -> str:
    """The mount-relative path with forward slashes (Starlette hands over OS separators)."""
    return path.replace("\\", "/")


def _is_client_route(path: str) -> bool:
    """Whether the single-page app should answer this path: not an API path, no file extension."""
    if path == "api" or path.startswith("api/"):
        return False
    return "." not in path.rsplit("/", 1)[-1]


def _set_cache_control(response: Response, path: str) -> None:
    """Cache hashed assets forever and never cache anything else."""
    response.headers["Cache-Control"] = _IMMUTABLE if path.startswith("assets/") else "no-cache"


class SPAStaticFiles(StaticFiles):
    """``StaticFiles`` for a single-page app.

    The app shell (the root, ``index.html`` and any unknown path without a file extension, so a
    deep link such as ``/build`` survives a reload) is rendered per request: the nonce
    placeholder in ``index.html`` is replaced by a fresh CSP nonce, which is also left on the ASGI
    scope for ``SecurityHeadersMiddleware``. Unknown API paths and missing files stay 404.
    """

    def __init__(
        self, *, directory: str | os.PathLike[str], html: bool = True, **kwargs: Any
    ) -> None:
        """Serve the build in ``directory``.

        Args:
            directory: The folder with the built UI.
            html: Serve ``index.html`` for directories, as ``StaticFiles`` does.
            **kwargs: Passed to ``StaticFiles``.

        Raises:
            StaleShellError: ``index.html`` has no ``CSP_NONCE_PLACEHOLDER`` (an older build).
        """
        super().__init__(directory=directory, html=html, **kwargs)
        self._shell = read_shell(Path(directory))

    @staticmethod
    def _shell_response(shell: str, scope: Scope) -> Response:
        """Render ``shell`` with a new nonce and record the nonce for the middleware."""
        nonce = generate_nonce()
        scope[NONCE_SCOPE_KEY] = nonce
        response = HTMLResponse(shell.replace(CSP_NONCE_PLACEHOLDER, nonce))
        response.headers["Cache-Control"] = "no-cache"
        return response

    async def get_response(self, path: str, scope: Scope) -> Response:
        """Serve ``path`` from the build folder, falling back to the app shell for client routes.

        Args:
            path: The path relative to the mount (``.`` for the root).
            scope: The ASGI scope.

        Returns:
            The file response with cache headers, or the shell rendered with a fresh nonce.

        Raises:
            HTTPException: 404 for unknown API paths and for missing files.
        """
        served = _posix(path)  # on Windows Starlette passes "api\nothing", not "api/nothing"
        shell = self._shell
        # The method check matters: StaticFiles.get_response raises 405 for a POST, and this early
        # return would otherwise answer a POST to "/" with the shell. Anything that is not
        # GET/HEAD falls through to super(), which refuses it (the fallback below is only
        # reached after super() raised a 404, which it does for GET/HEAD alone).
        if shell is not None and served in _SHELL_PATHS and scope["method"] in _READ_METHODS:
            return self._shell_response(shell, scope)
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or not _is_client_route(served):
                raise
            if shell is not None:
                return self._shell_response(shell, scope)
            response = await super().get_response(INDEX, scope)
            served = INDEX
        _set_cache_control(response, served)
        return response
