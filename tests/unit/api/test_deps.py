import pytest
from fastapi.testclient import TestClient

from bunsho.api.app import create_app
from bunsho.api.deps import CurrentUser
from bunsho.config.service import ServiceConfig
from bunsho.services.auth import TokenPair


@pytest.fixture
def probe_client(service_config: ServiceConfig):  # type: ignore[no-untyped-def]
    """A client for an app with one protected probe route."""
    app = create_app(service_config)

    @app.get("/probe")
    def probe(user: CurrentUser) -> dict[str, str]:
        return {"user": user}

    with TestClient(app) as client:
        yield client


def _tokens(client: TestClient) -> TokenPair:
    return client.app.state.services.auth.issue_tokens("james")  # type: ignore[attr-defined,no-any-return]


def test_no_token_is_401_with_a_bearer_challenge(probe_client: TestClient) -> None:
    response = probe_client.get("/probe")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_a_valid_access_token_resolves_the_username(probe_client: TestClient) -> None:
    headers = {"Authorization": f"Bearer {_tokens(probe_client).access_token}"}
    response = probe_client.get("/probe", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"user": "james"}


def test_a_refresh_token_is_rejected(probe_client: TestClient) -> None:
    headers = {"Authorization": f"Bearer {_tokens(probe_client).refresh_token}"}
    response = probe_client.get("/probe", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_a_garbage_token_is_rejected(probe_client: TestClient) -> None:
    response = probe_client.get("/probe", headers={"Authorization": "Bearer not.a.jwt"})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_a_non_bearer_scheme_is_rejected(probe_client: TestClient) -> None:
    token = _tokens(probe_client).access_token
    response = probe_client.get("/probe", headers={"Authorization": f"Basic {token}"})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
