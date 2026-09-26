"""Security headers on every HTTP response, and the Content-Security-Policy for each kind."""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bunsho.api.csp import (
    DEFAULT_POLICY,
    DOCS_PATHS,
    DOCS_POLICY,
    NONCE_SCOPE_KEY,
    header_name,
    shell_policy,
)

BASELINE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


class SecurityHeadersMiddleware:
    """Add the baseline headers and a CSP to every HTTP response.

    Add it last in ``create_app`` so it is the outermost user middleware: it then covers static
    files, API responses, the docs pages, CORS preflights and the JSON 500. It only fills gaps: a
    header the inner app already set keeps its value. WebSocket and lifespan scopes are not
    touched.

    Which CSP a response gets: the strict shell policy when the static layer left a nonce on the
    scope while serving the app shell, the docs policy on the docs paths, else default-deny.
    """

    def __init__(self, app: ASGIApp, *, report_only: bool = False) -> None:
        """Wrap ``app``.

        Args:
            app: The ASGI application to wrap.
            report_only: Send ``Content-Security-Policy-Report-Only`` instead of the enforcing
                header (never both).
        """
        self._app = app
        self._csp_header = header_name(report_only)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Run the wrapped app, adding the headers when the response starts."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        async def add_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                headers = MutableHeaders(scope=message)
                for name, value in BASELINE_HEADERS.items():
                    headers.setdefault(name, value)
                headers.setdefault(self._csp_header, self._policy_for(scope))
            await send(message)

        await self._app(scope, receive, add_headers)

    @staticmethod
    def _policy_for(scope: Scope) -> str:
        """Pick the CSP for this request; read at response start, when the nonce is known."""
        nonce = scope.get(NONCE_SCOPE_KEY)
        if nonce:
            return shell_policy(nonce)
        if scope.get("path") in DOCS_PATHS:
            return DOCS_POLICY
        return DEFAULT_POLICY
