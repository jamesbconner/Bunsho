"""Fixtures for API tests."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from bunsho.api.app import create_app
from bunsho.config.service import ServiceConfig


@pytest.fixture
def client(service_config: ServiceConfig) -> Iterator[TestClient]:
    """A ``TestClient`` running inside the app lifespan."""
    with TestClient(create_app(service_config)) as test_client:
        yield test_client
