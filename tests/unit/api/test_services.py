import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from bunsho.api import services as services_module
from bunsho.api.app import create_app
from bunsho.api.services import Services, build_services
from bunsho.config.service import ServiceConfig
from bunsho.db.engine import ProgressDatabase
from bunsho.services.health import HealthService


class _FailingDb:
    async def ping(self) -> None:
        raise OSError("disk gone")


def _count_disposals(monkeypatch: pytest.MonkeyPatch) -> list[ProgressDatabase]:
    disposed: list[ProgressDatabase] = []
    original = ProgressDatabase.dispose

    async def dispose(self: ProgressDatabase) -> None:
        disposed.append(self)
        await original(self)

    monkeypatch.setattr(ProgressDatabase, "dispose", dispose)
    return disposed


def test_ping_failure_disposes_the_engine_and_propagates(
    service_config: ServiceConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    disposed = _count_disposals(monkeypatch)

    async def failing_ping(self: ProgressDatabase) -> None:
        raise OSError("cannot open progress.db")

    monkeypatch.setattr(ProgressDatabase, "ping", failing_ping)
    with pytest.raises(OSError, match="cannot open progress.db"):
        asyncio.run(build_services(service_config))
    assert len(disposed) == 1


def test_context_failure_disposes_the_engine_and_propagates(
    service_config: ServiceConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    disposed = _count_disposals(monkeypatch)

    def failing_create_context(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("context boom")

    monkeypatch.setattr(services_module, "create_context", failing_create_context)
    with pytest.raises(RuntimeError, match="context boom"):
        asyncio.run(build_services(service_config))
    assert len(disposed) == 1


def test_shutdown_closes_the_build_manager_then_the_engine(
    service_config: ServiceConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    original_dispose = ProgressDatabase.dispose

    async def dispose(self: ProgressDatabase) -> None:
        calls.append("dispose")
        await original_dispose(self)

    monkeypatch.setattr(ProgressDatabase, "dispose", dispose)
    with TestClient(create_app(service_config)) as client:
        tasks = client.app.state.services.tasks  # type: ignore[attr-defined]
        original_aclose = tasks.aclose

        async def aclose(*args: Any, **kwargs: Any) -> None:
            calls.append("aclose")
            await original_aclose(*args, **kwargs)

        monkeypatch.setattr(tasks, "aclose", aclose)
        assert calls == []
    assert calls == ["aclose", "dispose"]


def test_engine_is_disposed_even_if_closing_the_build_manager_fails() -> None:
    disposed: list[bool] = []

    class _Tasks:
        async def aclose(self) -> None:
            raise RuntimeError("aclose boom")

    class _Db:
        async def dispose(self) -> None:
            disposed.append(True)

    fake = SimpleNamespace(tasks=_Tasks(), progress_db=_Db())
    with pytest.raises(RuntimeError, match="aclose boom"):
        asyncio.run(Services.aclose(fake))  # type: ignore[arg-type]
    assert disposed == [True]


def test_health_is_503_when_progress_db_is_in_error(client: TestClient) -> None:
    services = client.app.state.services  # type: ignore[attr-defined]
    services.health = HealthService(_FailingDb(), services.ctx)  # type: ignore[arg-type]
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert body["components"]["progress_db"]["detail"] == "OSError"


def test_health_is_200_when_only_degraded(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
