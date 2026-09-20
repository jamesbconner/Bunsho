import asyncio
import gc
import logging
import time
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from bunsho.api.routers import ws as ws_module
from tests.base import PASSWORD

WS = "/api/v1/ws/tasks"
BUILD = "/api/v1/admin/content/build"


def _login(client: TestClient) -> dict:  # type: ignore[type-arg]
    return client.post(  # type: ignore[no-any-return]
        "/api/v1/auth/login", json={"username": "james", "password": PASSWORD}
    ).json()


def _subscriber_count(client: TestClient) -> int:
    return len(client.app.state.services.tasks._subscribers)  # type: ignore[attr-defined]


def _close_and_wait_for_unsubscribe(client: TestClient, ws: WebSocketTestSession) -> None:
    """Close the client side and wait until the server handler has released its subscription.

    Leaving the ``with`` block cancels the server task right after sending the disconnect;
    letting the handler finish first keeps that test-harness race out of the assertions.
    """
    ws.close()
    deadline = time.monotonic() + 5
    while _subscriber_count(client) != 0:
        assert time.monotonic() < deadline, "subscription was not released"
        time.sleep(0.005)


def _send_and_receive(client: TestClient, first_message: object | None, *, binary: bool) -> None:
    with client.websocket_connect(WS) as ws:
        if binary:
            ws.send_bytes(b"\x00\x01\x02")
        elif isinstance(first_message, str):
            ws.send_text(first_message)
        elif first_message is not None:
            ws.send_json(first_message)
        ws.receive_json()


def _connect_and_get_disconnect(
    client: TestClient, first_message: object | None, *, binary: bool = False
) -> WebSocketDisconnect:
    with pytest.raises(WebSocketDisconnect) as info:
        _send_and_receive(client, first_message, binary=binary)
    return info.value


def _connect_and_expect_close(
    client: TestClient, first_message: object | None, *, binary: bool = False
) -> int:
    return _connect_and_get_disconnect(client, first_message, binary=binary).code


@pytest.mark.parametrize(
    "first_message",
    [
        {"type": "auth", "token": "bad-token"},
        {"type": "hello"},
        {"type": "auth"},
        {"type": "auth", "token": ""},
        ["not", "an", "object"],
        "this is not json",
        "null",
    ],
)
def test_bad_first_messages_close_with_1008(stub_client: TestClient, first_message: object) -> None:
    assert _connect_and_expect_close(stub_client, first_message) == 1008
    assert _subscriber_count(stub_client) == 0


def test_a_binary_first_frame_closes_with_1008(stub_client: TestClient) -> None:
    assert _connect_and_expect_close(stub_client, None, binary=True) == 1008


def test_an_oversized_first_message_closes_with_1008(stub_client: TestClient) -> None:
    huge = {"type": "auth", "token": "x" * 100_000}
    assert _connect_and_expect_close(stub_client, huge) == 1008


def test_a_refresh_token_cannot_authenticate_the_socket(stub_client: TestClient) -> None:
    tokens = _login(stub_client)
    message = {"type": "auth", "token": tokens["refresh_token"]}
    assert _connect_and_expect_close(stub_client, message) == 1008


def test_the_close_reason_never_echoes_the_message(stub_client: TestClient) -> None:
    message = {"type": "auth", "token": "super-secret-value"}
    disconnect = _connect_and_get_disconnect(stub_client, message)
    assert disconnect.code == 1008
    assert "super-secret-value" not in (disconnect.reason or "")


def test_silence_times_out_with_1008(
    stub_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("bunsho.api.routers.ws.AUTH_TIMEOUT_SECONDS", 0.2)
    assert _connect_and_expect_close(stub_client, None) == 1008
    assert _subscriber_count(stub_client) == 0


def test_disconnecting_before_authenticating_leaks_nothing(stub_client: TestClient) -> None:
    with stub_client.websocket_connect(WS) as ws:
        ws.close()
    assert _subscriber_count(stub_client) == 0


def test_disconnecting_after_ready_unsubscribes(stub_client: TestClient) -> None:
    tokens = _login(stub_client)
    with stub_client.websocket_connect(WS) as ws:
        ws.send_json({"type": "auth", "token": tokens["access_token"]})
        assert ws.receive_json() == {"type": "ready"}
        assert _subscriber_count(stub_client) == 1
        _close_and_wait_for_unsubscribe(stub_client, ws)
    assert _subscriber_count(stub_client) == 0


def test_client_messages_after_auth_are_ignored(stub_client: TestClient) -> None:
    tokens = _login(stub_client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    with stub_client.websocket_connect(WS) as ws:
        ws.send_json({"type": "auth", "token": tokens["access_token"]})
        assert ws.receive_json() == {"type": "ready"}
        ws.send_text("chatter")
        ws.send_bytes(b"\xff\xfe")
        task_id = stub_client.post(BUILD, json={}, headers=headers).json()["task_id"]
        first = ws.receive_json()
        _close_and_wait_for_unsubscribe(stub_client, ws)
    assert first["type"] == "event"
    assert first["event"]["task_id"] == task_id


def test_events_are_streamed_for_a_build_started_after_connecting(stub_client: TestClient) -> None:
    tokens = _login(stub_client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    with stub_client.websocket_connect(WS) as ws:
        ws.send_json({"type": "auth", "token": tokens["access_token"]})
        assert ws.receive_json() == {"type": "ready"}
        started = stub_client.post(BUILD, json={}, headers=headers)
        assert started.status_code == 202
        task_id = started.json()["task_id"]
        messages = []
        while True:
            message = ws.receive_json()
            messages.append(message)
            event = message["event"]
            if event["kind"] == "state" and event["state"] != "running":
                break
        _close_and_wait_for_unsubscribe(stub_client, ws)
    assert all(m["type"] == "event" and m["event"]["task_id"] == task_id for m in messages)
    assert (messages[0]["event"]["kind"], messages[0]["event"]["state"]) == ("state", "running")
    assert messages[-1]["event"]["state"] == "succeeded"
    stages = [m["event"]["progress"]["stage"] for m in messages if m["event"]["progress"]]
    assert stages[0] == "import_deck"
    assert stages[-1] == "write"


def test_a_late_client_gets_a_snapshot_of_the_latest_build(stub_client: TestClient) -> None:
    tokens = _login(stub_client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    task_id = stub_client.post(BUILD, json={"dry_run": True}, headers=headers).json()["task_id"]
    deadline = time.monotonic() + 10
    while stub_client.get(f"{BUILD}/{task_id}", headers=headers).json()["state"] == "running":
        assert time.monotonic() < deadline
        time.sleep(0.02)
    with stub_client.websocket_connect(WS) as ws:
        ws.send_json({"type": "auth", "token": tokens["access_token"]})
        assert ws.receive_json() == {"type": "ready"}
        snapshot = ws.receive_json()
        _close_and_wait_for_unsubscribe(stub_client, ws)
    assert snapshot["type"] == "snapshot"
    assert snapshot["task"]["task_id"] == task_id
    assert snapshot["task"]["state"] == "succeeded"


def test_an_unexpected_stream_failure_closes_1011_without_leaking_details(
    stub_client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def broken(*_args: Any) -> None:
        raise ValueError("internal secret detail")

    monkeypatch.setattr("bunsho.api.routers.ws._forward", broken)
    tokens = _login(stub_client)
    caplog.set_level(logging.INFO, logger="bunsho")
    with stub_client.websocket_connect(WS) as ws:
        ws.send_json({"type": "auth", "token": tokens["access_token"]})
        assert ws.receive_json() == {"type": "ready"}
        with pytest.raises(WebSocketDisconnect) as info:
            ws.receive_json()
    assert info.value.code == 1011
    assert "internal secret detail" not in (info.value.reason or "")
    assert "internal secret detail" not in caplog.text
    assert "ws_stream_failed" in caplog.text
    assert _subscriber_count(stub_client) == 0


def test_a_client_that_vanishes_while_streaming_is_not_an_error(
    stub_client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def gone(*_args: Any) -> None:
        raise WebSocketDisconnect(1006)

    monkeypatch.setattr("bunsho.api.routers.ws._forward", gone)
    tokens = _login(stub_client)
    caplog.set_level(logging.INFO, logger="bunsho")
    with stub_client.websocket_connect(WS) as ws:
        ws.send_json({"type": "auth", "token": tokens["access_token"]})
        assert ws.receive_json() == {"type": "ready"}
        deadline = time.monotonic() + 5
        while _subscriber_count(stub_client) != 0:
            assert time.monotonic() < deadline, "subscription was not released"
            time.sleep(0.005)
    assert "ws_stream_failed" not in caplog.text


class _FakeSocket:
    """Just enough of a ``WebSocket`` for ``_stream``: records sends, disconnects on demand."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self._released = asyncio.Event()

    async def send_json(self, data: dict[str, Any]) -> None:
        self.sent.append(data)

    async def receive(self) -> dict[str, str]:
        await self._released.wait()
        return {"type": "websocket.disconnect"}

    def disconnect(self) -> None:
        self._released.set()


class _FakeTasks:
    """The slice of ``BuildTaskManager`` that ``_stream`` uses."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[Any] = asyncio.Queue()
        self.unsubscribed = 0

    def subscribe(self) -> asyncio.Queue[Any]:
        return self.queue

    def latest(self) -> None:
        return None

    def unsubscribe(self, queue: asyncio.Queue[Any]) -> None:
        assert queue is self.queue
        self.unsubscribed += 1


def _record_workers(monkeypatch: pytest.MonkeyPatch, *, fail: bool = False) -> list[asyncio.Task]:  # type: ignore[type-arg]
    """Wrap ``_forward`` and ``_drain`` to record their tasks; optionally make both fail."""
    recorded: list[asyncio.Task] = []  # type: ignore[type-arg]

    def wrap(original: Any) -> Any:
        async def worker(*args: Any) -> None:
            task = asyncio.current_task()
            assert task is not None
            recorded.append(task)
            if fail:
                raise RuntimeError("worker failed")
            await original(*args)

        return worker

    monkeypatch.setattr(ws_module, "_forward", wrap(ws_module._forward))
    monkeypatch.setattr(ws_module, "_drain", wrap(ws_module._drain))
    return recorded


def test_a_disconnect_leaves_no_worker_task_running(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded = _record_workers(monkeypatch)
    fake_ws, tasks = _FakeSocket(), _FakeTasks()
    services = SimpleNamespace(tasks=tasks)

    async def disconnect_once_streaming() -> None:
        while len(recorded) < 2:
            await asyncio.sleep(0)
        assert not any(t.done() for t in recorded)
        fake_ws.disconnect()

    async def scenario() -> None:
        disconnector = asyncio.create_task(disconnect_once_streaming())
        # Awaited directly, not as a task, so the check below runs with no extra loop turn.
        await asyncio.wait_for(ws_module._stream(fake_ws, services), 5)  # type: ignore[arg-type]
        assert all(t.done() for t in recorded)  # settled, not merely asked to cancel
        await disconnector

    asyncio.run(scenario())
    assert [m["type"] for m in fake_ws.sent] == ["ready"]
    assert len(recorded) == 2
    assert tasks.unsubscribed == 1


def test_a_cancelled_handler_still_unsubscribes_and_settles_its_workers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = _record_workers(monkeypatch)
    fake_ws, tasks = _FakeSocket(), _FakeTasks()
    services = SimpleNamespace(tasks=tasks)

    async def scenario() -> None:
        stream = asyncio.create_task(ws_module._stream(fake_ws, services))  # type: ignore[arg-type]
        while len(recorded) < 2:
            await asyncio.sleep(0)
        stream.cancel()  # what server shutdown does to a live handler
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(stream, 5)
        assert all(t.done() for t in recorded)

    asyncio.run(scenario())
    assert tasks.unsubscribed == 1


def test_two_workers_failing_together_leave_no_unretrieved_exception(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    recorded = _record_workers(monkeypatch, fail=True)
    fake_ws, tasks = _FakeSocket(), _FakeTasks()
    services = SimpleNamespace(tasks=tasks)
    caplog.set_level(logging.DEBUG, logger="asyncio")

    async def scenario() -> None:
        await asyncio.wait_for(ws_module._stream(fake_ws, services), 5)  # type: ignore[arg-type]
        assert len(recorded) == 2
        assert all(t.done() for t in recorded)
        recorded.clear()  # asyncio reports an unretrieved exception when the task is collected
        gc.collect()

    asyncio.run(scenario())
    gc.collect()
    assert "never retrieved" not in caplog.text
    assert tasks.unsubscribed == 1
