"""Fixtures for API tests."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from bunsho.api.app import create_app
from bunsho.api.services import ServiceOverrides
from bunsho.config.service import ServiceConfig
from tests.base import PASSWORD, StubOrchestrator


@pytest.fixture
def client(service_config: ServiceConfig) -> Iterator[TestClient]:
    """A ``TestClient`` running inside the app lifespan."""
    with TestClient(create_app(service_config)) as test_client:
        yield test_client


@pytest.fixture
def stub() -> StubOrchestrator:
    """The fake build orchestrator used by ``stub_client``."""
    return StubOrchestrator()


@pytest.fixture
def stub_client(service_config: ServiceConfig, stub: StubOrchestrator) -> Iterator[TestClient]:
    """A ``TestClient`` whose app builds content with ``stub``."""
    overrides = ServiceOverrides(orchestrator_factory=lambda _ctx: stub)  # type: ignore[arg-type,return-value]
    with TestClient(create_app(service_config, overrides=overrides)) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(stub_client: TestClient) -> dict[str, str]:
    """An ``Authorization`` header obtained by logging in through the API."""
    response = stub_client.post(
        "/api/v1/auth/login", json={"username": "james", "password": PASSWORD}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
