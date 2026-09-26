"""Turn an unhandled error into the fixed JSON 500 from inside the CORS layer.

Starlette serves ``add_exception_handler(Exception, ...)`` from its outermost middleware,
which is outside ``CORSMiddleware``, so that 500 never gets CORS headers and a cross-origin
browser sees a network failure instead of the server's answer. Catching the error here, one
layer inside CORS, lets the CORS middleware decorate the 500 like any other response.
"""

from __future__ import annotations

import logging

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

INTERNAL_ERROR_DETAIL = "internal error"
"""The only text a client ever sees about a server-side failure."""


def unhandled_error_response(path: str, exc: BaseException) -> JSONResponse:
    """Log ``exc`` server side and build the fixed 500 answer.

    Args:
        path: The request path, for the log line.
        exc: The unhandled exception; its text is logged and never returned.

    Returns:
        A 500 response whose body is ``{"detail": "internal error"}``.
    """
    logging.getLogger("bunsho").exception("unhandled_error path=%s", path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": INTERNAL_ERROR_DETAIL})


class UnhandledErrorMiddleware:
    """Answer an exception raised while handling an HTTP request with the fixed JSON 500.

    Add it before ``CORSMiddleware`` so it sits inside it. WebSocket and lifespan scopes pass
    straight through, and so does an exception raised after the response has started (a fresh
    500 cannot follow a status line already sent, so the error propagates and the connection
    is cut, as it would without this middleware).
    """

    def __init__(self, app: ASGIApp) -> None:
        """Wrap ``app``.

        Args:
            app: The ASGI application to protect.
        """
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Run the wrapped app, replacing an unhandled error with the fixed 500."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        started = False

        async def track_start(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self._app(scope, receive, track_start)
        except Exception as exc:
            if started:
                raise
            response = unhandled_error_response(scope.get("path", ""), exc)
            await response(scope, receive, send)
