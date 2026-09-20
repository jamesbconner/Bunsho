import dataclasses
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bunsho.api.app import create_app
from bunsho.config.service import ServiceConfig

INDEX_HTML = '<!doctype html><html><body><div id="root"></div></body></html>'
SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
}


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (root / "assets" / "app-abc123.js").write_text("console.log(1);", encoding="utf-8")
    (root / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("top secret", encoding="utf-8")
    return root


@pytest.fixture
def ui_client(service_config: ServiceConfig, dist: Path) -> Iterator[TestClient]:
    app_config = dataclasses.replace(service_config.app, frontend_dir=dist)
    config = dataclasses.replace(service_config, app=app_config)
    with TestClient(create_app(config)) as client:
        yield client


def test_the_root_serves_the_app_shell_without_caching(ui_client: TestClient) -> None:
    response = ui_client.get("/")
    assert response.status_code == 200
    assert response.text == INDEX_HTML
    assert response.headers["cache-control"] == "no-cache"
    for name, value in SECURITY_HEADERS.items():
        assert response.headers[name] == value


@pytest.mark.parametrize("path", ["/build", "/some/nested/route", "/login"])
def test_client_side_routes_fall_back_to_the_shell(ui_client: TestClient, path: str) -> None:
    response = ui_client.get(path)
    assert response.status_code == 200
    assert response.text == INDEX_HTML
    assert response.headers["cache-control"] == "no-cache"


def test_hashed_assets_are_cached_forever(ui_client: TestClient) -> None:
    response = ui_client.get("/assets/app-abc123.js")
    assert response.status_code == 200
    assert response.text == "console.log(1);"
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_other_files_are_served_but_not_cached(ui_client: TestClient) -> None:
    response = ui_client.get("/favicon.svg")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize("path", ["/assets/missing.js", "/nope.png", "/assets/missing.css"])
def test_missing_files_are_a_404_not_the_shell(ui_client: TestClient, path: str) -> None:
    assert ui_client.get(path).status_code == 404


@pytest.mark.parametrize("path", ["/api/v1/does-not-exist", "/api/nothing", "/api"])
def test_unknown_api_paths_keep_their_json_404(ui_client: TestClient, path: str) -> None:
    response = ui_client.get(path)
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_api_routes_docs_and_the_schema_still_win(ui_client: TestClient) -> None:
    health = ui_client.get("/api/v1/health")
    assert health.status_code == 200
    assert "components" in health.json()
    assert ui_client.get("/api/v1/reviews/next").status_code == 401
    assert ui_client.get("/openapi.json").json()["openapi"].startswith("3.")
    assert ui_client.get("/docs").status_code == 200


def test_head_works_and_other_methods_are_refused(ui_client: TestClient) -> None:
    assert ui_client.head("/").status_code == 200
    assert ui_client.post("/", json={}).status_code == 405


def test_a_path_traversal_cannot_leave_the_frontend_folder(ui_client: TestClient) -> None:
    response = ui_client.get("/%2e%2e/secret.txt")
    assert "top secret" not in response.text


def test_without_a_frontend_folder_the_root_is_a_plain_json_404(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
