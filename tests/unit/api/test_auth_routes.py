import pytest
from fastapi.testclient import TestClient

from tests.base import PASSWORD

LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
PROTECTED = [
    ("GET", "/api/v1/content/summary"),
    ("GET", "/api/v1/admin/config-check"),
    ("GET", "/api/v1/admin/content/build"),
    ("POST", "/api/v1/admin/content/build"),
]


def _login(client: TestClient, password: str = PASSWORD, username: str = "james"):  # type: ignore[no-untyped-def]
    return client.post(LOGIN, json={"username": username, "password": password})


def test_login_returns_tokens_that_open_protected_routes(client: TestClient) -> None:
    response = _login(client)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 15 * 60
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    assert client.get("/api/v1/content/summary", headers=headers).status_code == 200


def test_wrong_username_and_wrong_password_look_identical(client: TestClient) -> None:
    bad_password = _login(client, password="nope")
    bad_user = _login(client, username="mallory")
    assert bad_password.status_code == bad_user.status_code == 401
    assert bad_password.json() == bad_user.json()
    assert bad_password.headers["www-authenticate"] == "Bearer"


def test_login_is_throttled_after_repeated_failures(client: TestClient) -> None:
    for _ in range(5):
        assert _login(client, password="nope").status_code == 401
    blocked = _login(client, password="nope")
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert _login(client).status_code == 429  # even the right password waits


def test_login_body_is_validated(client: TestClient) -> None:
    assert client.post(LOGIN, json={"username": "james"}).status_code == 422
    assert client.post(LOGIN, json={"username": "", "password": ""}).status_code == 422


def test_refresh_issues_new_tokens_and_rejects_bad_ones(client: TestClient) -> None:
    tokens = _login(client).json()
    refreshed = client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] != tokens["access_token"]
    assert client.post(REFRESH, json={"refresh_token": tokens["access_token"]}).status_code == 401
    assert client.post(REFRESH, json={"refresh_token": "garbage"}).status_code == 401


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_protected_routes_reject_missing_and_bad_tokens(
    client: TestClient, method: str, path: str
) -> None:
    missing = client.request(method, path)
    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"
    bad = client.request(method, path, headers={"Authorization": "Bearer not-a-token"})
    assert bad.status_code == 401
    refresh_token = _login(client).json()["refresh_token"]
    wrong_type = client.request(method, path, headers={"Authorization": f"Bearer {refresh_token}"})
    assert wrong_type.status_code == 401
