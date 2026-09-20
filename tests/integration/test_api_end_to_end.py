import asyncio
import dataclasses
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.testclient import WebSocketTestSession

from bunsho.api.app import create_app
from bunsho.api.services import ServiceOverrides
from bunsho.config.service import ServiceConfig
from bunsho.context import Context
from bunsho.db.engine import ProgressDatabase
from bunsho.db.models import AppSetting
from bunsho.orchestration.content_build import ContentBuildOrchestrator
from bunsho.services.anki_importer import AnkiDeckImporter
from bunsho.services.content_repository import ContentWriter
from bunsho.services.kana_source import KanaSource
from tests.apkg_builder import build_apkg, note
from tests.base import (
    PASSWORD,
    FakeKanjiSource,
    close_and_wait_for_unsubscribe,
    make_service_config,
)


def _config_with_a_synthetic_deck(tmp_path: Path) -> ServiceConfig:
    config = make_service_config(tmp_path)
    (tmp_path / "resources").mkdir()
    sha = build_apkg(
        config.app.deck_path,
        [note("日本", "日本[にほん]"), note("学生", "学生[がくせい]", "jlpt_N4")],
    )
    return dataclasses.replace(config, app=dataclasses.replace(config.app, deck_sha256=sha))


def _real_orchestrator(ctx: Context) -> ContentBuildOrchestrator:
    return ContentBuildOrchestrator(
        importer=AnkiDeckImporter(ctx.config.deck_sha256, ctx.logger),
        kana_provider=KanaSource(),
        kanji_source=FakeKanjiSource(),  # type: ignore[arg-type]
        writer=ContentWriter(),
        logger=ctx.logger,
    )


MAX_WS_MESSAGES = 500
"""Hard cap on messages read while waiting for a build to end; a build emits far fewer."""


def _await_terminal_event(ws: WebSocketTestSession) -> dict[str, Any]:
    """Read the stream until a build reaches a terminal state.

    ``ready`` and ``snapshot`` messages are ignored. The loop is bounded by
    ``MAX_WS_MESSAGES`` so a stream that never finishes fails instead of hanging.
    """
    seen: list[str] = []
    for _ in range(MAX_WS_MESSAGES):
        message = ws.receive_json()
        if message["type"] != "event":
            seen.append(message["type"])
            continue
        event: dict[str, Any] = message["event"]
        if event["kind"] == "state" and event["state"] != "running":
            return event
        seen.append(f"{event['kind']}:{event.get('state')}")
    pytest.fail(f"no terminal build event within {MAX_WS_MESSAGES} messages; saw {seen[:10]}...")


async def _write_setting(path: Path, key: str, value: str) -> None:
    db = ProgressDatabase(path)
    try:
        async with db.sessions() as session, session.begin():
            session.add(AppSetting(key=key, value=value))
    finally:
        await db.dispose()


async def _read_setting(path: Path, key: str) -> str | None:
    db = ProgressDatabase(path)
    try:
        async with db.sessions() as session:
            return await session.scalar(select(AppSetting.value).where(AppSetting.key == key))
    finally:
        await db.dispose()


@pytest.mark.integration
def test_login_build_stream_and_restart(tmp_path: Path) -> None:
    config = _config_with_a_synthetic_deck(tmp_path)
    overrides = ServiceOverrides(orchestrator_factory=_real_orchestrator)
    with TestClient(create_app(config, overrides=overrides)) as client:
        tokens = client.post(
            "/api/v1/auth/login", json={"username": "james", "password": PASSWORD}
        ).json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        checks = client.get("/api/v1/admin/config-check", headers=headers).json()
        assert {c["name"]: c["ok"] for c in checks["checks"]}["deck_checksum"] is True

        with client.websocket_connect("/api/v1/ws/tasks") as ws:
            ws.send_json({"type": "auth", "token": tokens["access_token"]})
            assert ws.receive_json() == {"type": "ready"}
            assert (
                client.post("/api/v1/admin/content/build", json={}, headers=headers).status_code
                == 202
            )
            event = _await_terminal_event(ws)
            close_and_wait_for_unsubscribe(client, ws)
        assert event["state"] == "succeeded"

        summary = client.get("/api/v1/content/summary", headers=headers).json()
        assert summary["built"] is True
        assert (summary["kana"], summary["kanji"], summary["vocab"]) == (208, 4, 2)
        assert client.get("/api/v1/health").json()["components"]["content_db"]["status"] == "ok"

    # A restarted service sees the same progress.db (with data written in between), the built
    # content.db and a still-valid refresh token, and it makes no backup.
    progress_path = config.app.progress_db_path
    asyncio.run(_write_setting(progress_path, "e2e_marker", "kept"))
    with TestClient(create_app(config, overrides=overrides)) as client:
        assert asyncio.run(_read_setting(progress_path, "e2e_marker")) == "kept"
        refreshed = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert refreshed.status_code == 200
        headers = {"Authorization": f"Bearer {refreshed.json()['access_token']}"}
        assert client.get("/api/v1/content/summary", headers=headers).json()["vocab"] == 2
    assert not (config.app.data_dir / "backups").exists()
