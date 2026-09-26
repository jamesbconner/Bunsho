import dataclasses
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response

from bunsho.api.app import create_app
from bunsho.api.csp import DEFAULT_POLICY, DOCS_PATHS, DOCS_POLICY
from bunsho.config.service import ServiceConfig
from tests.base import make_service_config

ORIGIN = "http://localhost:5173"
BASELINE = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
}


def _boom() -> None:
    raise RuntimeError("secret")


def _assert_secured(response: Response, policy: str = DEFAULT_POLICY) -> None:
    for name, value in BASELINE.items():
        assert response.headers[name] == value
    assert response.headers["content-security-policy"] == policy
    assert "content-security-policy-report-only" not in response.headers


@pytest.mark.parametrize(
    "path", ["/api/v1/health", "/openapi.json", "/api/v1/does-not-exist", "/nothing/at/all"]
)
def test_api_and_schema_responses_carry_the_headers_and_default_policy(
    client: TestClient, path: str
) -> None:
    _assert_secured(client.get(path))


def test_an_unauthorized_response_is_secured(client: TestClient) -> None:
    response = client.get("/api/v1/reviews/next")
    assert response.status_code == 401
    _assert_secured(response)


def test_a_method_not_allowed_response_is_secured(client: TestClient) -> None:
    response = client.post("/api/v1/health", json={})
    assert response.status_code == 405
    _assert_secured(response)


@pytest.mark.parametrize("path", sorted(DOCS_PATHS))
def test_the_docs_pages_carry_the_docs_policy(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    _assert_secured(response, DOCS_POLICY)


def test_the_docs_paths_match_the_apps_real_urls(service_config: ServiceConfig) -> None:
    app = create_app(service_config)
    assert {app.docs_url, app.redoc_url, app.swagger_ui_oauth2_redirect_url} == DOCS_PATHS


def test_every_origin_the_docs_pages_load_from_is_allowed_by_the_docs_policy(
    client: TestClient,
) -> None:
    for path in ("/docs", "/redoc"):
        response = client.get(path)
        origins = set(re.findall(r"https?://[^/\"' )>?]+", response.text))
        assert origins, f"{path} references no external origin: the pattern needs a look"
        for origin in origins:
            assert origin in response.headers["content-security-policy"], (
                f"{path} loads from {origin}, which the docs policy does not allow; a FastAPI "
                "upgrade probably changed the page: update DOCS_POLICY and the spec"
            )


def test_the_docs_policy_keeps_the_origins_the_page_html_cannot_show(client: TestClient) -> None:
    # Swagger UI and ReDoc load their fonts from the stylesheet and their web worker from the
    # script, so neither appears in the HTML the scanning test above reads; pin them explicitly.
    policy = client.get("/redoc").headers["content-security-policy"]
    assert policy == DOCS_POLICY
    directives = {part.strip() for part in policy.split(";")}
    assert "worker-src blob:" in directives
    assert "font-src https://fonts.gstatic.com" in directives


@pytest.fixture
def failing_client(service_config: ServiceConfig) -> Iterator[TestClient]:
    app = create_app(service_config)
    app.add_api_route("/boom", _boom)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_the_json_500_is_secured(failing_client: TestClient) -> None:
    response = failing_client.get("/boom")
    assert response.status_code == 500
    _assert_secured(response)


def test_a_cors_preflight_is_secured(tmp_path: Path) -> None:
    config = make_service_config(tmp_path, cors_origins=(ORIGIN,))
    preflight = {"Origin": ORIGIN, "Access-Control-Request-Method": "GET"}
    with TestClient(create_app(config)) as client:
        response = client.options("/api/v1/health", headers=preflight)
    assert response.status_code == 200
    _assert_secured(response)


def test_report_only_mode_sends_only_the_report_only_header(service_config: ServiceConfig) -> None:
    server = dataclasses.replace(service_config.server, csp_report_only=True)
    config = dataclasses.replace(service_config, server=server)
    with TestClient(create_app(config)) as client:
        response = client.get("/api/v1/health")
    assert response.headers["content-security-policy-report-only"] == DEFAULT_POLICY
    assert "content-security-policy" not in response.headers
    for name, value in BASELINE.items():
        assert response.headers[name] == value
