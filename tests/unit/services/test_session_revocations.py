import asyncio
from datetime import UTC, datetime, timedelta

from bunsho.services.session_revocations import MemorySessionRevocations

NOW = datetime(2026, 1, 2, tzinfo=UTC)


def test_a_session_is_revoked_only_after_revoke() -> None:
    revocations = MemorySessionRevocations()
    assert revocations.is_revoked("sid-a") is False
    asyncio.run(revocations.revoke("sid-a", NOW + timedelta(days=30)))
    assert revocations.is_revoked("sid-a") is True
    assert revocations.is_revoked("sid-b") is False


def test_expiry_reports_when_the_revocation_lapses() -> None:
    revocations = MemorySessionRevocations()
    assert revocations.expiry("sid-a") is None
    asyncio.run(revocations.revoke("sid-a", NOW + timedelta(days=30)))
    assert revocations.expiry("sid-a") == NOW + timedelta(days=30)
