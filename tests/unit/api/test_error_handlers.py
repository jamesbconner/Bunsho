import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bunsho.api.app import create_app
from bunsho.config.service import ServiceConfig
from bunsho.models.review import ReviewError, UnknownItemError
from tests.base import make_service_config

INTERNAL_ERROR = {"detail": "internal error"}


def _boom() -> None:
    raise RuntimeError("secret /etc/passwd")


def _unmapped_review_error() -> None:
    raise ReviewError("secret detail")


def _mapped_review_error() -> None:
    raise UnknownItemError("no such item: kana:hira:x")


@pytest.fixture
def failing_client(service_config: ServiceConfig):  # type: ignore[no-untyped-def]
    """A client whose app has routes that raise. Server errors come back as responses."""
    app = create_app(service_config)
    app.add_api_route("/boom", _boom)
    app.add_api_route("/unmapped", _unmapped_review_error)
    app.add_api_route("/mapped", _mapped_review_error)
    # Starlette's ServerErrorMiddleware sends the 500 and then re-raises; do not surface that.
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_an_unhandled_exception_gives_a_fixed_json_500_and_is_logged(
    failing_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="bunsho"):
        response = failing_client.get("/boom")
    assert response.status_code == 500
    assert response.json() == INTERNAL_ERROR
    assert "secret" not in response.text
    assert "unhandled_error path=/boom" in caplog.text
    assert "secret /etc/passwd" in caplog.text  # the detail stays server side


def test_an_unmapped_review_error_hides_its_message(failing_client: TestClient) -> None:
    response = failing_client.get("/unmapped")
    assert response.status_code == 500
    assert response.json() == INTERNAL_ERROR
    assert "secret" not in response.text


def test_a_mapped_review_error_keeps_its_status_and_message(failing_client: TestClient) -> None:
    response = failing_client.get("/mapped")
    assert response.status_code == 404
    assert response.json() == {"detail": "no such item: kana:hira:x"}


ORIGIN = "http://localhost:5173"


@pytest.fixture
def cors_failing_client(tmp_path: Path) -> Iterator[TestClient]:
    """Like ``failing_client``, with CORS enabled for one origin."""
    app = create_app(make_service_config(tmp_path, cors_origins=(ORIGIN,)))
    app.add_api_route("/boom", _boom)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_the_500_carries_cors_headers_for_an_allowed_origin(
    cors_failing_client: TestClient,
) -> None:
    response = cors_failing_client.get("/boom", headers={"Origin": ORIGIN})
    assert response.status_code == 500
    assert response.json() == INTERNAL_ERROR
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert "Retry-After" in response.headers["access-control-expose-headers"]


def test_the_500_gets_no_cors_header_for_a_disallowed_origin(
    cors_failing_client: TestClient,
) -> None:
    response = cors_failing_client.get("/boom", headers={"Origin": "http://evil.example"})
    assert response.status_code == 500
    assert response.json() == INTERNAL_ERROR
    assert "access-control-allow-origin" not in response.headers


def test_the_500_gets_no_cors_header_without_an_origin(cors_failing_client: TestClient) -> None:
    response = cors_failing_client.get("/boom")
    assert response.status_code == 500
    assert "access-control-allow-origin" not in response.headers


def test_the_500_from_a_cors_app_still_hides_the_detail_and_logs_it(
    cors_failing_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="bunsho"):
        response = cors_failing_client.get("/boom", headers={"Origin": ORIGIN})
    assert "secret" not in response.text
    assert "unhandled_error path=/boom" in caplog.text
    assert "secret /etc/passwd" in caplog.text
