from concurrent.futures import ThreadPoolExecutor

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


def test_concurrent_wrong_logins_cannot_outrun_the_throttle(client: TestClient) -> None:
    with ThreadPoolExecutor(max_workers=20) as pool:
        responses = list(pool.map(lambda _: _login(client, password="nope"), range(40)))
    codes = [response.status_code for response in responses]
    assert codes.count(401) == 5  # max_failures attempts get through, the rest are blocked
    assert codes.count(429) == 35
    assert _login(client).status_code == 429


def test_successful_login_resets_the_counter(client: TestClient) -> None:
    for _ in range(4):
        assert _login(client, password="nope").status_code == 401
    assert _login(client).status_code == 200
    for _ in range(5):  # a fresh allowance, not a stale block
        assert _login(client, password="nope").status_code == 401
    assert _login(client, password="nope").status_code == 429


def test_success_amid_a_failure_burst_leaves_no_stale_block(client: TestClient) -> None:
    def attempt(index: int) -> int:
        password = PASSWORD if index == 0 else "nope"
        return _login(client, password=password).status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        codes = list(pool.map(attempt, range(4)))  # fewer than max_failures in total
    assert 200 in codes
    assert 429 not in codes
    for _ in range(5):
        assert _login(client, password="nope").status_code in (401, 429)
    assert _login(client).status_code == 429  # blocked only by the failures just made


def test_validation_errors_do_not_echo_the_submitted_input(client: TestClient) -> None:
    secret = "SuperSecretValue" * 80  # longer than the 1024 character limit
    too_long = client.post(LOGIN, json={"username": "james", "password": secret})
    assert too_long.status_code == 422
    assert secret not in too_long.text
    not_a_string = client.post(LOGIN, json={"username": "james", "password": 918273645})
    assert not_a_string.status_code == 422
    assert "918273645" not in not_a_string.text
    for response in (too_long, not_a_string):
        error = response.json()["detail"][0]
        assert error["loc"] == ["body", "password"]
        assert error["msg"]
        assert error["type"]
        assert set(error) == {"loc", "msg", "type"}


def test_malformed_json_body_gets_a_clean_422(client: TestClient) -> None:
    response = client.post(
        LOGIN,
        content='{"username": "james", "password": "hunter2-leak"',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert "hunter2-leak" not in response.text
    error = response.json()["detail"][0]
    assert set(error) == {"loc", "msg", "type"}
    assert error["type"] == "json_invalid"
