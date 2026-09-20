"""WebSocket stream of build events.

Browsers cannot set an ``Authorization`` header on a WebSocket and a token in the URL
ends up in logs, so the client authenticates with its first message. Nothing sent to the
client, used as a close reason or logged ever contains exception text, the token or the
offending message: only the outcome and the client host are logged.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from contextlib import suppress
from typing import Any, Literal

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from bunsho.api.deps import ServicesDep
from bunsho.api.schemas import (
    WsAuthMessage,
    WsEvent,
    WsReady,
    WsSnapshot,
    build_event,
    build_status,
)
from bunsho.orchestration.build_tasks import BuildEvent
from bunsho.services.auth import AuthError

router = APIRouter(tags=["ws"])

AUTH_TIMEOUT_SECONDS = 5.0
"""How long a client has to send its authentication message."""

MAX_AUTH_MESSAGE_CHARS = 8192
"""Largest first message accepted; a JWT plus its envelope is far smaller."""

POLICY_VIOLATION = 1008
INTERNAL_ERROR = 1011

_AuthOutcome = Literal[
    "ok", "disconnected", "timeout", "not_text", "oversized", "malformed", "invalid_token"
]


def _client_host(websocket: WebSocket) -> str:
    return websocket.client.host if websocket.client else "unknown"


def _check_first_message(message: Mapping[str, Any], services: ServicesDep) -> _AuthOutcome:
    """Classify the first frame the client sent."""
    if message["type"] == "websocket.disconnect":
        return "disconnected"
    text = message.get("text")
    if text is None:
        return "not_text"
    if len(text) > MAX_AUTH_MESSAGE_CHARS:
        return "oversized"
    try:
        auth = WsAuthMessage.model_validate(json.loads(text))
    except (ValueError, RecursionError, ValidationError):
        return "malformed"
    try:
        services.auth.authenticate(auth.token)
    except AuthError:
        return "invalid_token"
    return "ok"


async def _authenticate(websocket: WebSocket, services: ServicesDep) -> bool:
    """Read the first message and validate the access token.

    Closes the socket with 1008 on any failure and never raises for client misbehaviour.

    Returns:
        ``True`` when the client authenticated.
    """
    try:
        message = await asyncio.wait_for(websocket.receive(), AUTH_TIMEOUT_SECONDS)
    except TimeoutError:
        outcome: _AuthOutcome = "timeout"
    else:
        outcome = _check_first_message(message, services)
    client = _client_host(websocket)
    if outcome == "ok":
        services.ctx.logger.info("ws_auth_ok client=%s", client)
        return True
    services.ctx.logger.warning("ws_auth_failed client=%s outcome=%s", client, outcome)
    if outcome != "disconnected":
        with suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close(code=POLICY_VIOLATION)
    return False


async def _forward(websocket: WebSocket, queue: asyncio.Queue[BuildEvent]) -> None:
    """Send every queued build event to the client."""
    while True:
        event = await queue.get()
        await websocket.send_json(WsEvent(event=build_event(event)).model_dump(mode="json"))


async def _drain(websocket: WebSocket) -> None:
    """Consume and ignore client frames until the client disconnects."""
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return


async def _stream(websocket: WebSocket, services: ServicesDep) -> None:
    """Send ``ready``, the snapshot and then live events until the client goes away."""
    tasks = services.tasks
    # Subscribe and read the latest build without awaiting in between: every later event is
    # queued, and none can slip between the snapshot and the subscription.
    queue = tasks.subscribe()
    workers: list[asyncio.Task[None]] = []
    try:
        latest = tasks.latest()
        snapshot = WsSnapshot(task=build_status(latest)).model_dump(mode="json") if latest else None
        await websocket.send_json(WsReady().model_dump())
        if snapshot is not None:
            await websocket.send_json(snapshot)
        workers = [
            asyncio.create_task(_forward(websocket, queue)),
            asyncio.create_task(_drain(websocket)),
        ]
        done, _pending = await asyncio.wait(workers, return_when=asyncio.FIRST_COMPLETED)
        for worker in done:
            worker.result()  # surfaces a failure of the forwarder (a disconnect, or a bug)
    except (WebSocketDisconnect, RuntimeError):
        pass  # the client went away (RuntimeError: a send after the socket closed)
    finally:
        tasks.unsubscribe(queue)
        for worker in workers:
            worker.cancel()
        # Let the cancellations land so no worker outlives the handler, and retrieve every
        # outcome (a failure the handler did not surface included) without raising. Runs after
        # ``unsubscribe``; if the handler itself is being cancelled this await may re-raise
        # ``CancelledError``, which is deliberately not swallowed.
        await asyncio.gather(*workers, return_exceptions=True)


@router.websocket("/ws/tasks")
async def task_stream(websocket: WebSocket, services: ServicesDep) -> None:
    """Authenticate with a first message, then stream build events until disconnect.

    Protocol: the client sends ``{"type": "auth", "token": <access token>}`` within
    ``AUTH_TIMEOUT_SECONDS``; the server answers ``ready``, then a ``snapshot`` of the
    latest build (if any), then one ``event`` per build event. Any other first message
    closes the socket with code 1008.
    """
    await websocket.accept()
    if not await _authenticate(websocket, services):
        return
    try:
        await _stream(websocket, services)
    except Exception as exc:
        # A bug, not a client problem: log the type only (the text may hold internals).
        services.ctx.logger.error(
            "ws_stream_failed client=%s error_type=%s", _client_host(websocket), type(exc).__name__
        )
        with suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close(code=INTERNAL_ERROR)
