"""In-memory session revocations: the default for ``AuthService`` and a fake for tests."""

from __future__ import annotations

from datetime import datetime


class MemorySessionRevocations:
    """A ``SessionRevocations`` that forgets everything when the process ends."""

    def __init__(self) -> None:
        """Create an empty set of revocations."""
        self._revoked: dict[str, datetime] = {}

    def is_revoked(self, sid: str) -> bool:
        """Return whether ``sid`` was revoked."""
        return sid in self._revoked

    async def revoke(self, sid: str, expires_at: datetime) -> None:
        """Revoke ``sid`` until ``expires_at``."""
        self._revoked[sid] = expires_at

    def expiry(self, sid: str) -> datetime | None:
        """Return when the revocation of ``sid`` lapses, or ``None`` if it is not revoked."""
        return self._revoked.get(sid)
