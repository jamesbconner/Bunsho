import logging

import pytest
from fastapi.testclient import TestClient

from bunsho.api.app import create_app
from bunsho.config.service import ServiceConfig
from bunsho.models.review import ReviewError, UnknownItemError

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
