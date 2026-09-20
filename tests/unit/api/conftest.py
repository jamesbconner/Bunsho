"""Fixtures for API tests."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from bunsho.api.app import create_app
from bunsho.api.services import ServiceOverrides
from bunsho.config.service import ServiceConfig
from bunsho.models.content import JlptLevel
from tests.base import PASSWORD, StubOrchestrator, make_kana, make_kanji, make_vocab, write_content


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


@pytest.fixture
def review_config(service_config: ServiceConfig) -> ServiceConfig:
    """``service_config`` whose data folder already holds a small ``content.db``."""
    write_content(
        service_config.app.content_db_path,
        kana=[make_kana("あ", "a")],
        kanji=[make_kanji("日", JlptLevel.N5)],
        vocab=[make_vocab("日本", "にほん"), make_vocab("学生", "がくせい", JlptLevel.N4)],
    )
    return service_config


@pytest.fixture
def review_client(review_config: ServiceConfig) -> Iterator[TestClient]:
    """A ``TestClient`` on an app that starts with content already built."""
    with TestClient(create_app(review_config)) as test_client:
        yield test_client


@pytest.fixture
def review_headers(review_client: TestClient) -> dict[str, str]:
    """An ``Authorization`` header for ``review_client``."""
    response = review_client.post(
        "/api/v1/auth/login", json={"username": "james", "password": PASSWORD}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
