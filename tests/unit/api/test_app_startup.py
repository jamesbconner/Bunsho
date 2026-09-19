import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bunsho import __version__
from bunsho.api.app import create_app
from tests.base import make_service_config


def test_health_needs_no_auth_and_reports_components(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == __version__
    assert body["components"]["progress_db"]["status"] == "ok"
    assert body["components"]["content_db"]["status"] == "degraded"  # first run: not built yet
    assert body["status"] == "degraded"


def test_startup_migrates_progress_db(client: TestClient, service_config) -> None:  # type: ignore[no-untyped-def]
    with closing(sqlite3.connect(service_config.app.progress_db_path)) as con:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"card_state", "review_log", "app_setting"} <= tables
    assert not (service_config.app.data_dir / "backups").exists()


def test_cors_is_only_enabled_for_configured_origins(tmp_path: Path) -> None:
    config = make_service_config(tmp_path, cors_origins=("http://localhost:5173",))
    preflight = {"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"}
    with TestClient(create_app(config)) as client:
        allowed = client.options("/api/v1/health", headers=preflight)
        assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
        other = client.options(
            "/api/v1/health", headers={**preflight, "Origin": "http://evil.example"}
        )
        assert "access-control-allow-origin" not in other.headers


def test_no_cors_headers_without_configured_origins(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    assert "access-control-allow-origin" not in response.headers


def test_a_corrupt_progress_db_aborts_startup(tmp_path: Path) -> None:
    config = make_service_config(tmp_path)
    config.app.data_dir.mkdir(parents=True)
    config.app.progress_db_path.write_bytes(b"definitely not sqlite" * 20)

    # sqlalchemy DatabaseError from the migration
    with pytest.raises(Exception), TestClient(create_app(config)):  # noqa: B017,PT011
        pass
