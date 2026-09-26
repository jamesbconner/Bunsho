import asyncio

import pytest
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bunsho.api.csp import DEFAULT_POLICY, DOCS_POLICY, NONCE_SCOPE_KEY, shell_policy
from bunsho.api.security_headers import BASELINE_HEADERS, SecurityHeadersMiddleware

BASELINE = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
}


def _scope(path: str = "/api/v1/health", kind: str = "http") -> Scope:
    return {"type": kind, "path": path, "method": "GET", "headers": []}


def _responding(
    headers: list[tuple[str, str]] | None = None, *, nonce: str | None = None
) -> ASGIApp:
    """An app that answers 200 with ``headers``; optionally leaves a nonce on the scope first."""

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        if nonce is not None:
            scope[NONCE_SCOPE_KEY] = nonce
        raw = [
            (k.lower().encode(), v.encode()) for k, v in headers or []
        ]  # ASGI names are lowercase
        await send({"type": "http.response.start", "status": 200, "headers": raw})
        await send({"type": "http.response.body", "body": b""})

    return app


def _headers(app: ASGIApp, scope: Scope, *, report_only: bool = False) -> dict[str, str]:
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request"}

    async def send(message: Message) -> None:
        sent.append(message)

    asyncio.run(SecurityHeadersMiddleware(app, report_only=report_only)(scope, receive, send))
    start = next(m for m in sent if m["type"] == "http.response.start")
    return {k.decode().lower(): v.decode() for k, v in start["headers"]}


def test_the_baseline_headers_are_a_documented_constant() -> None:
    assert {k.lower(): v for k, v in BASELINE_HEADERS.items()} == BASELINE


def test_a_plain_response_gets_the_baseline_and_the_default_policy() -> None:
    headers = _headers(_responding(), _scope())
    for name, value in BASELINE.items():
        assert headers[name] == value
    assert headers["content-security-policy"] == DEFAULT_POLICY


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/docs/oauth2-redirect"])
def test_the_docs_pages_get_the_docs_policy(path: str) -> None:
    assert _headers(_responding(), _scope(path))["content-security-policy"] == DOCS_POLICY


@pytest.mark.parametrize("path", ["/docs/", "/docsx", "/redoc/x", "/api/docs", "/", "/docs/other"])
def test_near_misses_do_not_get_the_loose_docs_policy(path: str) -> None:
    assert _headers(_responding(), _scope(path))["content-security-policy"] == DEFAULT_POLICY


def test_a_nonce_left_on_the_scope_selects_the_shell_policy() -> None:
    headers = _headers(_responding(nonce="YWJjZA=="), _scope("/build"))
    assert headers["content-security-policy"] == shell_policy("YWJjZA==")


def test_the_nonce_is_read_when_the_response_starts_not_when_the_request_arrives() -> None:
    # The inner app sets the nonce while handling the request; the middleware must still see it.
    headers = _headers(_responding(nonce="ZWZnaA=="), _scope("/"))
    assert "'nonce-ZWZnaA=='" in headers["content-security-policy"]


def test_the_shell_policy_wins_over_the_docs_path_rule() -> None:
    headers = _headers(_responding(nonce="YWJjZA=="), _scope("/docs"))
    assert headers["content-security-policy"] == shell_policy("YWJjZA==")


def test_report_only_sends_the_report_only_header_and_never_both() -> None:
    headers = _headers(_responding(), _scope(), report_only=True)
    assert headers["content-security-policy-report-only"] == DEFAULT_POLICY
    assert "content-security-policy" not in headers


def test_enforcing_mode_never_sends_the_report_only_header() -> None:
    assert "content-security-policy-report-only" not in _headers(_responding(), _scope())


def test_headers_the_inner_app_already_set_are_kept() -> None:
    inner = _responding(
        [("X-Frame-Options", "SAMEORIGIN"), ("Content-Security-Policy", "default-src 'self'")]
    )
    headers = _headers(inner, _scope())
    assert headers["x-frame-options"] == "SAMEORIGIN"
    assert headers["content-security-policy"] == "default-src 'self'"
    assert headers["x-content-type-options"] == "nosniff"  # the gaps are still filled


def test_a_response_start_without_a_headers_key_still_gets_them() -> None:
    async def bare(_scope: Scope, _receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 204})
        await send({"type": "http.response.body", "body": b""})

    headers = _headers(bare, _scope())
    assert headers["x-frame-options"] == "DENY"
    assert headers["content-security-policy"] == DEFAULT_POLICY


def test_body_messages_are_passed_through_untouched() -> None:
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request"}

    async def send(message: Message) -> None:
        sent.append(message)

    asyncio.run(SecurityHeadersMiddleware(_responding())(_scope(), receive, send))
    assert sent[1] == {"type": "http.response.body", "body": b""}


@pytest.mark.parametrize("kind", ["websocket", "lifespan"])
def test_other_scopes_pass_through_without_touching_messages(kind: str) -> None:
    sent: list[Message] = []

    async def app(_scope: Scope, _receive: Receive, send: Send) -> None:
        await send({"type": "websocket.accept", "headers": []})

    async def receive() -> Message:
        return {"type": "websocket.connect"}

    async def send(message: Message) -> None:
        sent.append(message)

    asyncio.run(SecurityHeadersMiddleware(app)(_scope(kind=kind), receive, send))
    assert sent == [{"type": "websocket.accept", "headers": []}]
