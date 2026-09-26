import asyncio
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from bunsho.services.auth import AuthError, AuthService, SessionClaims
from bunsho.services.session_revocations import MemorySessionRevocations
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


def _claims(token: str) -> dict:  # type: ignore[type-arg]
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])


@pytest.fixture
def fresh_auth() -> AuthService:
    return AuthService(make_auth_settings(), revocations=MemorySessionRevocations())


def test_both_tokens_of_one_login_share_a_session_id(fresh_auth: AuthService) -> None:
    first = fresh_auth.issue_tokens("james")
    second = fresh_auth.issue_tokens("james")
    sid = _claims(first.access_token)["sid"]
    assert sid == _claims(first.refresh_token)["sid"]
    assert len(sid) == 32
    assert sid != _claims(second.access_token)["sid"]


def test_refresh_keeps_the_session_id(fresh_auth: AuthService) -> None:
    first = fresh_auth.issue_tokens("james")
    second = fresh_auth.refresh(first.refresh_token)
    assert _claims(second.access_token)["sid"] == _claims(first.access_token)["sid"]
    assert _claims(second.refresh_token)["sid"] == _claims(first.refresh_token)["sid"]


def test_authenticate_session_returns_the_username_and_session_id(
    fresh_auth: AuthService,
) -> None:
    tokens = fresh_auth.issue_tokens("james")
    assert fresh_auth.authenticate_session(tokens.access_token) == SessionClaims(
        username="james", sid=_claims(tokens.access_token)["sid"]
    )


def test_revoking_a_session_rejects_all_of_its_tokens(fresh_auth: AuthService) -> None:
    first = fresh_auth.issue_tokens("james")
    second = fresh_auth.refresh(first.refresh_token)  # a later pair of the same login
    sid = asyncio.run(fresh_auth.revoke(first.refresh_token))
    assert sid == _claims(first.access_token)["sid"]
    for token in (first.access_token, second.access_token):
        with pytest.raises(AuthError):
            fresh_auth.authenticate(token)
        with pytest.raises(AuthError):
            fresh_auth.authenticate_session(token)
    for token in (first.refresh_token, second.refresh_token):
        with pytest.raises(AuthError):
            fresh_auth.refresh(token)


def test_revoking_one_session_leaves_another_login_alone(fresh_auth: AuthService) -> None:
    one = fresh_auth.issue_tokens("james")
    two = fresh_auth.issue_tokens("james")
    asyncio.run(fresh_auth.revoke(one.refresh_token))
    assert fresh_auth.authenticate(two.access_token) == "james"
    assert fresh_auth.refresh(two.refresh_token).access_token


def test_a_revoked_session_stays_revoked_for_a_full_refresh_lifetime() -> None:
    revocations = MemorySessionRevocations()
    auth = AuthService(make_auth_settings(), revocations=revocations)
    tokens = auth.issue_tokens("james")
    before = datetime.now(UTC)
    sid = asyncio.run(auth.revoke(tokens.refresh_token))
    after = datetime.now(UTC)
    expires_at = revocations.expiry(sid)
    assert expires_at is not None
    # Not the presented token's own exp: a newer refresh token of the same login can outlive it.
    assert before + timedelta(days=30) <= expires_at <= after + timedelta(days=30)


@pytest.mark.parametrize("kind", ["access", "refresh"])
def test_a_token_without_a_session_id_is_rejected(fresh_auth: AuthService, kind: str) -> None:
    """Tokens issued before sessions existed carry no ``sid``; the user logs in again once."""
    legacy = jwt.encode(
        {"sub": "james", "typ": kind, "exp": datetime.now(UTC) + timedelta(days=1)},
        JWT_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(AuthError):
        fresh_auth.authenticate(legacy)
    with pytest.raises(AuthError):
        fresh_auth.refresh(legacy)
    with pytest.raises(AuthError):
        asyncio.run(fresh_auth.revoke(legacy))


def test_revoke_rejects_tokens_that_do_not_verify(fresh_auth: AuthService) -> None:
    tokens = fresh_auth.issue_tokens("james")
    past = AuthService(make_auth_settings(), clock=lambda: datetime(2020, 1, 1, tzinfo=UTC))
    for bad in ("garbage", "", tokens.access_token, past.issue_tokens("james").refresh_token):
        with pytest.raises(AuthError):
            asyncio.run(fresh_auth.revoke(bad))
    # A failed revoke revoked nothing.
    assert fresh_auth.authenticate(tokens.access_token) == "james"


def test_revoking_an_already_revoked_session_raises(fresh_auth: AuthService) -> None:
    tokens = fresh_auth.issue_tokens("james")
    asyncio.run(fresh_auth.revoke(tokens.refresh_token))
    with pytest.raises(AuthError):
        asyncio.run(fresh_auth.revoke(tokens.refresh_token))
