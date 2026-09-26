import dataclasses
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response

from bunsho.api.app import create_app
from bunsho.api.csp import DEFAULT_POLICY, shell_policy
from bunsho.api.static import SPAStaticFiles
from bunsho.config.service import ServiceConfig
from bunsho.frontend_shell import CSP_NONCE_PLACEHOLDER, StaleShellError
from tests.base import make_service_config

INDEX_HTML = (
    '<!doctype html><html><head><meta name="csp-nonce" content="__CSP_NONCE__" /></head>'
    '<body><div id="root"></div></body></html>'
)
SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
}
NONCE_IN_POLICY = re.compile(r"'nonce-([A-Za-z0-9+/=]+)'")
NONCE_IN_BODY = re.compile(r'name="csp-nonce" content="([^"]*)"')


def shell_nonce(response: Response) -> str:
    """The nonce in the CSP header; asserts it is the same one the page body carries."""
    header = NONCE_IN_POLICY.search(response.headers["content-security-policy"])
    body = NONCE_IN_BODY.search(response.text)
    assert header is not None, "the shell's CSP carries no nonce"
    assert body is not None, "the shell body carries no csp-nonce meta tag"
    assert header.group(1) == body.group(1)
    return header.group(1)


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


def test_the_root_serves_the_shell_with_a_nonce_and_no_caching(ui_client: TestClient) -> None:
    response = ui_client.get("/")
    assert response.status_code == 200
    nonce = shell_nonce(response)
    assert response.text == INDEX_HTML.replace(CSP_NONCE_PLACEHOLDER, nonce)
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["content-security-policy"] == shell_policy(nonce)
    for name, value in SECURITY_HEADERS.items():
        assert response.headers[name] == value


@pytest.mark.parametrize("path", ["/build", "/some/nested/route", "/login", "/index.html"])
def test_client_side_routes_and_index_get_the_shell_with_a_nonce(
    ui_client: TestClient, path: str
) -> None:
    response = ui_client.get(path)
    assert response.status_code == 200
    nonce = shell_nonce(response)
    assert response.text == INDEX_HTML.replace(CSP_NONCE_PLACEHOLDER, nonce)
    assert response.headers["cache-control"] == "no-cache"


def test_every_shell_response_gets_a_fresh_nonce(ui_client: TestClient) -> None:
    nonces = [shell_nonce(ui_client.get(path)) for path in ["/", "/", "/build", "/build", "/login"]]
    assert len(set(nonces)) == len(nonces)


def test_the_placeholder_never_reaches_the_client(ui_client: TestClient) -> None:
    for path in ["/", "/build", "/index.html"]:
        assert CSP_NONCE_PLACEHOLDER not in ui_client.get(path).text


@pytest.mark.parametrize("path", ["/", "/build"])
def test_head_on_the_shell_is_secured_and_has_a_nonce(ui_client: TestClient, path: str) -> None:
    response = ui_client.head(path)
    assert response.status_code == 200
    assert NONCE_IN_POLICY.search(response.headers["content-security-policy"])
    assert response.headers["cache-control"] == "no-cache"
    assert response.content == b""


def test_the_nonce_still_matches_when_cors_is_on_and_the_request_has_an_origin(
    tmp_path: Path, dist: Path
) -> None:
    origin = "https://app.example.com"
    config = make_service_config(tmp_path, cors_origins=(origin,))
    config = dataclasses.replace(config, app=dataclasses.replace(config.app, frontend_dir=dist))
    with TestClient(create_app(config)) as client:
        response = client.get("/build", headers={"Origin": origin})
    assert response.status_code == 200
    nonce = shell_nonce(response)
    assert response.headers["content-security-policy"] == shell_policy(nonce)
    assert response.headers["access-control-allow-origin"] == origin


@pytest.mark.parametrize("path", ["/", "/index.html", "/build"])
@pytest.mark.parametrize("method", ["post", "put", "delete", "patch"])
def test_writes_to_the_shell_are_refused_not_answered_with_it(
    ui_client: TestClient, method: str, path: str
) -> None:
    response = getattr(ui_client, method)(path)
    assert response.status_code == 405
    assert CSP_NONCE_PLACEHOLDER not in response.text
    assert "csp-nonce" not in response.text
    assert "nonce" not in response.headers["content-security-policy"]


def test_hashed_assets_are_cached_forever_and_get_no_nonce(ui_client: TestClient) -> None:
    response = ui_client.get("/assets/app-abc123.js")
    assert response.status_code == 200
    assert response.text == "console.log(1);"
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == DEFAULT_POLICY


def test_other_files_are_served_but_not_cached_and_get_no_nonce(ui_client: TestClient) -> None:
    response = ui_client.get("/favicon.svg")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["content-security-policy"] == DEFAULT_POLICY


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


@pytest.mark.parametrize("path", ["/assets/missing.js", "/nope.png", "/api/nothing", "/api"])
def test_a_404_never_gets_the_shell_body_or_policy(ui_client: TestClient, path: str) -> None:
    response = ui_client.get(path)
    assert response.status_code == 404
    assert "nonce" not in response.headers["content-security-policy"]
    assert CSP_NONCE_PLACEHOLDER not in response.text
    assert response.headers["content-security-policy"] == DEFAULT_POLICY


def test_a_stale_build_is_refused_when_the_files_are_constructed(tmp_path: Path) -> None:
    stale = tmp_path / "stale"
    stale.mkdir()
    (stale / "index.html").write_text("<html><body>old</body></html>", encoding="utf-8")
    with pytest.raises(StaleShellError, match="npm run build"):
        SPAStaticFiles(directory=stale, html=True)


def test_create_app_refuses_a_stale_build(service_config: ServiceConfig, tmp_path: Path) -> None:
    stale = tmp_path / "stale"
    stale.mkdir()
    (stale / "index.html").write_text("<html><body>old</body></html>", encoding="utf-8")
    app_config = dataclasses.replace(service_config.app, frontend_dir=stale)
    with pytest.raises(ValueError, match="npm run build"):
        create_app(dataclasses.replace(service_config, app=app_config))


def test_a_folder_without_an_index_keeps_its_old_behaviour(
    service_config: ServiceConfig, tmp_path: Path
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    app_config = dataclasses.replace(service_config.app, frontend_dir=empty)
    config = dataclasses.replace(service_config, app=app_config)
    with TestClient(create_app(config)) as client:
        assert client.get("/favicon.svg").status_code == 200
        assert client.get("/").status_code == 404
        assert client.get("/build").status_code == 404
