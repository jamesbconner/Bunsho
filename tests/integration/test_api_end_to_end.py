import dataclasses
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bunsho.api.app import create_app
from bunsho.api.services import ServiceOverrides
from bunsho.config.service import ServiceConfig
from bunsho.context import Context
from bunsho.orchestration.content_build import ContentBuildOrchestrator
from bunsho.services.anki_importer import AnkiDeckImporter
from bunsho.services.content_repository import ContentWriter
from bunsho.services.kana_source import KanaSource
from tests.apkg_builder import build_apkg, note
from tests.base import PASSWORD, FakeKanjiSource, make_service_config


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
            while True:
                event = ws.receive_json()["event"]
                if event["kind"] == "state" and event["state"] != "running":
                    break
        assert event["state"] == "succeeded"

        summary = client.get("/api/v1/content/summary", headers=headers).json()
        assert summary["built"] is True
        assert (summary["kana"], summary["kanji"], summary["vocab"]) == (208, 4, 2)
        assert client.get("/api/v1/health").json()["components"]["content_db"]["status"] == "ok"

    # A restarted service sees the same progress.db and the built content.db, without a backup.
    with TestClient(create_app(config, overrides=overrides)) as client:
        headers = {
            "Authorization": "Bearer "
            + client.post(
                "/api/v1/auth/login", json={"username": "james", "password": PASSWORD}
            ).json()["access_token"]
        }
        assert client.get("/api/v1/content/summary", headers=headers).json()["vocab"] == 2
    assert not (config.app.data_dir / "backups").exists()
