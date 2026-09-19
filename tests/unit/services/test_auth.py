from datetime import UTC, datetime

import jwt
import pytest

from bunsho.services.auth import AuthError, AuthService
from tests.base import JWT_SECRET, PASSWORD, make_auth_settings


@pytest.fixture(scope="module")
def auth() -> AuthService:
    return AuthService(make_auth_settings())


def test_correct_credentials_are_accepted(auth: AuthService) -> None:
    assert auth.verify_credentials("james", PASSWORD) is True


@pytest.mark.parametrize(
    ("username", "password"),
    [("james", "wrong"), ("mallory", PASSWORD), ("", ""), ("JAMES", PASSWORD)],
)
def test_wrong_credentials_are_rejected(auth: AuthService, username: str, password: str) -> None:
    assert auth.verify_credentials(username, password) is False


def test_token_round_trip(auth: AuthService) -> None:
    tokens = auth.issue_tokens("james")
    assert tokens.token_type == "bearer"
    assert tokens.expires_in == 15 * 60
    assert auth.authenticate(tokens.access_token) == "james"
    claims = jwt.decode(tokens.access_token, JWT_SECRET, algorithms=["HS256"])
    assert claims["typ"] == "access"
    assert claims["sub"] == "james"


def test_refresh_issues_a_new_pair(auth: AuthService) -> None:
    first = auth.issue_tokens("james")
    second = auth.refresh(first.refresh_token)
    assert second.access_token != first.access_token
    assert auth.authenticate(second.access_token) == "james"


def test_access_and_refresh_tokens_are_not_interchangeable(auth: AuthService) -> None:
    tokens = auth.issue_tokens("james")
    with pytest.raises(AuthError):
        auth.authenticate(tokens.refresh_token)
    with pytest.raises(AuthError):
        auth.refresh(tokens.access_token)


def test_expired_token_is_rejected() -> None:
    past = AuthService(make_auth_settings(), clock=lambda: datetime(2020, 1, 1, tzinfo=UTC))
    with pytest.raises(AuthError):
        past.authenticate(past.issue_tokens("james").access_token)


def test_token_signed_with_another_secret_is_rejected(auth: AuthService) -> None:
    other = AuthService(make_auth_settings(jwt_secret="o" * 40))
    with pytest.raises(AuthError):
        auth.authenticate(other.issue_tokens("james").access_token)


def test_tampered_and_garbage_tokens_are_rejected(auth: AuthService) -> None:
    token = auth.issue_tokens("james").access_token
    with pytest.raises(AuthError):
        auth.authenticate(token[:-3] + ("abc" if not token.endswith("abc") else "xyz"))
    with pytest.raises(AuthError):
        auth.authenticate("not.a.jwt")
    with pytest.raises(AuthError):
        auth.authenticate("")


def test_token_for_another_subject_is_rejected(auth: AuthService) -> None:
    with pytest.raises(AuthError):
        auth.authenticate(auth.issue_tokens("mallory").access_token)


def test_token_without_expiry_is_rejected(auth: AuthService) -> None:
    forged = jwt.encode({"sub": "james", "typ": "access"}, JWT_SECRET, algorithm="HS256")
    with pytest.raises(AuthError):
        auth.authenticate(forged)
