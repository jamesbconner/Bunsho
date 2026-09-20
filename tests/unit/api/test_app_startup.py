import asyncio
import logging
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import DatabaseError

from bunsho import __version__
from bunsho.api.app import create_app
from bunsho.api.services import StartupError, build_services
from bunsho.config.service import ServiceConfig
from bunsho.services.content_repository import ContentWriter
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


def test_cors_preflight_allows_put_so_a_browser_can_save_settings(tmp_path: Path) -> None:
    origin = "http://localhost:5173"
    config = make_service_config(tmp_path, cors_origins=(origin,))
    preflight = {"Origin": origin, "Access-Control-Request-Method": "PUT"}
    with TestClient(create_app(config)) as client:
        response = client.options("/api/v1/settings", headers=preflight)
    assert response.status_code == 200
    assert "PUT" in response.headers["access-control-allow-methods"]


def test_cors_exposes_retry_after_so_browsers_can_read_the_login_throttle(tmp_path: Path) -> None:
    origin = "http://localhost:5173"
    config = make_service_config(tmp_path, cors_origins=(origin,))
    login = "/api/v1/auth/login"
    wrong = {"username": "james", "password": "nope"}
    with TestClient(create_app(config)) as client:
        simple = client.get("/api/v1/health", headers={"Origin": origin})
        assert "Retry-After" in simple.headers["access-control-expose-headers"]

        for _ in range(5):
            assert client.post(login, json=wrong, headers={"Origin": origin}).status_code == 401
        blocked = client.post(login, json=wrong, headers={"Origin": origin})
    assert blocked.status_code == 429
    assert "retry-after" in blocked.headers
    exposed = blocked.headers["access-control-expose-headers"]
    assert "Retry-After" in [h.strip() for h in exposed.split(",")]


def test_no_cors_headers_without_configured_origins(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    assert "access-control-allow-origin" not in response.headers


def test_a_corrupt_progress_db_aborts_startup(tmp_path: Path) -> None:
    config = make_service_config(tmp_path)
    config.app.data_dir.mkdir(parents=True)
    config.app.progress_db_path.write_bytes(b"definitely not sqlite" * 20)

    with pytest.raises(StartupError) as info, TestClient(create_app(config)):
        pass
    assert isinstance(info.value.__cause__, DatabaseError)


def test_a_corrupt_progress_db_gives_an_actionable_startup_error(
    service_config: ServiceConfig, caplog: pytest.LogCaptureFixture
) -> None:
    path = service_config.app.progress_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a database" * 100)
    with pytest.raises(StartupError) as info:
        asyncio.run(build_services(service_config))
    message = str(info.value)
    assert str(path) in message
    assert str(service_config.app.data_dir / "backups") in message
    assert "DatabaseError" in message
    assert "progress_db_startup_failed" in caplog.text


def test_stale_build_temp_files_are_swept_at_startup(service_config: ServiceConfig) -> None:
    data_dir = service_config.app.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    stale = data_dir / f"content.db.{'a' * 32}.tmp"
    stale.write_bytes(b"x")

    async def scenario() -> None:
        services = await build_services(service_config)
        await services.aclose()

    asyncio.run(scenario())
    assert not stale.exists()


def test_a_second_instance_on_the_same_data_folder_is_refused(
    service_config: ServiceConfig,
) -> None:
    async def scenario() -> None:
        first = await build_services(service_config)
        try:
            with pytest.raises(StartupError, match="instance"):
                await build_services(service_config)
        finally:
            await first.aclose()
        second = await build_services(service_config)  # the lock was released by aclose
        await second.aclose()

    asyncio.run(scenario())


def test_a_failed_startup_releases_the_instance_lock(service_config: ServiceConfig) -> None:
    from bunsho.db.instance_lock import InstanceLock

    path = service_config.app.progress_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a database" * 100)
    with pytest.raises(StartupError):
        asyncio.run(build_services(service_config))
    probe = InstanceLock(service_config.app.data_dir)
    probe.acquire()  # would raise InstanceLockedError if the failed start kept the lock
    probe.release()


def test_an_unusable_data_folder_gives_an_actionable_startup_error(
    service_config: ServiceConfig,
) -> None:
    service_config.app.data_dir.parent.mkdir(parents=True, exist_ok=True)
    service_config.app.data_dir.write_text("a file, not a folder")
    with pytest.raises(StartupError, match="instance lock"):
        asyncio.run(build_services(service_config))


def test_startup_logs_a_content_schema_mismatch_but_still_starts(
    service_config: ServiceConfig, caplog: pytest.LogCaptureFixture
) -> None:
    ContentWriter().write(
        service_config.app.content_db_path,
        kana=[],
        kanji=[],
        vocab=[],
        meta={"schema_version": "1"},
    )

    async def scenario() -> None:
        services = await build_services(service_config)
        await services.aclose()

    with caplog.at_level(logging.ERROR, logger="bunsho"):
        asyncio.run(scenario())
    assert "content_schema_check_failed" in caplog.text
