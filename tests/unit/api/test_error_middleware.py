import asyncio
import json
import logging
from typing import Any

import pytest
from starlette.types import Message, Receive, Scope, Send

from bunsho.api.error_middleware import UnhandledErrorMiddleware, unhandled_error_response

HTTP: Scope = {"type": "http", "path": "/api/v1/boom", "method": "GET", "headers": []}


async def _no_input() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


def _run(app: Any, scope: Scope) -> list[Message]:
    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    asyncio.run(UnhandledErrorMiddleware(app)(scope, _no_input, send))
    return sent


def _body(sent: list[Message]) -> Any:
    return json.loads(b"".join(m.get("body", b"") for m in sent))


async def _raises_before_responding(_scope: Scope, _receive: Receive, _send: Send) -> None:
    raise RuntimeError("secret /etc/passwd")


def test_an_exception_before_the_response_becomes_a_fixed_500() -> None:
    sent = _run(_raises_before_responding, HTTP)
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 500
    assert _body(sent) == {"detail": "internal error"}
    assert b"secret" not in b"".join(m.get("body", b"") for m in sent)


def test_the_error_is_logged_with_its_detail_server_side(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.ERROR, logger="bunsho"):
        _run(_raises_before_responding, HTTP)
    assert "unhandled_error path=/api/v1/boom" in caplog.text
    assert "secret /etc/passwd" in caplog.text


def test_a_response_that_already_started_cannot_be_replaced() -> None:
    async def fails_mid_response(_scope: Scope, _receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError("stream broke")

    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    with pytest.raises(RuntimeError, match="stream broke"):
        asyncio.run(UnhandledErrorMiddleware(fails_mid_response)(HTTP, _no_input, send))
    assert [m["type"] for m in sent] == ["http.response.start"]  # no second, corrupting response


def test_a_normal_response_passes_through_untouched() -> None:
    async def ok(_scope: Scope, _receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    sent = _run(ok, HTTP)
    assert [m["type"] for m in sent] == ["http.response.start", "http.response.body"]
    assert sent[0]["status"] == 204


@pytest.mark.parametrize("scope_type", ["websocket", "lifespan"])
def test_other_scopes_are_not_touched(scope_type: str) -> None:
    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    with pytest.raises(RuntimeError, match="secret"):
        asyncio.run(
            UnhandledErrorMiddleware(_raises_before_responding)(
                {"type": scope_type}, _no_input, send
            )
        )
    assert sent == []


def test_the_shared_response_is_the_fixed_json_500() -> None:
    response = unhandled_error_response("/x", RuntimeError("secret"))
    assert response.status_code == 500
    assert json.loads(bytes(response.body)) == {"detail": "internal error"}
