"""Persistent set of revoked login sessions (the ``revoked_session`` table in ``progress.db``).

``is_revoked`` reads memory only: ``AuthService`` calls it on every request and WebSocket
connect, inside async handlers, so it must never block the event loop on SQLite. That is
safe because the service runs as a single process (see ``bunsho.db.instance_lock``).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from bunsho.db.engine import ProgressDatabase
from bunsho.db.models import RevokedSession
from bunsho.db.timestamps import format_timestamp, parse_timestamp


class RevokedSessionStore:
    """Revoked session ids: SQLite for durability, a dict for the per-request check."""

    def __init__(
        self, database: ProgressDatabase, *, clock: Callable[[], datetime] | None = None
    ) -> None:
        """Create the store; call ``load`` once at startup before serving requests.

        Args:
            database: The async engine wrapper for ``progress.db``.
            clock: Time source for pruning (defaults to UTC now).
        """
        self._database = database
        self._clock = clock or (lambda: datetime.now(UTC))
        self._expiry: dict[str, datetime] = {}

    async def load(self) -> None:
        """Delete lapsed rows, then load the remaining revocations into memory."""
        now = format_timestamp(self._clock())
        async with self._database.sessions() as session, session.begin():
            await session.execute(delete(RevokedSession).where(RevokedSession.expires_at <= now))
            rows = (
                await session.execute(select(RevokedSession.sid, RevokedSession.expires_at))
            ).all()
        self._expiry = {sid: parse_timestamp(expires_at) for sid, expires_at in rows}

    def is_revoked(self, sid: str) -> bool:
        """Return whether ``sid`` was revoked (memory only, no I/O)."""
        return sid in self._expiry

    async def revoke(self, sid: str, expires_at: datetime) -> None:
        """Persist the revocation of ``sid`` until ``expires_at``, then remember it in memory.

        Lapsed rows are pruned in the same transaction. If the write fails nothing changes
        in memory and the error propagates.

        Raises:
            ValueError: ``expires_at`` is a naive datetime.
        """
        now = self._clock()
        stored = format_timestamp(expires_at)
        statement = sqlite_insert(RevokedSession).values(sid=sid, expires_at=stored)
        statement = statement.on_conflict_do_update(
            index_elements=[RevokedSession.sid], set_={"expires_at": stored}
        )
        async with self._database.sessions() as session, session.begin():
            await session.execute(
                delete(RevokedSession).where(RevokedSession.expires_at <= format_timestamp(now))
            )
            await session.execute(statement)
        self._expiry = {known: until for known, until in self._expiry.items() if until > now}
        self._expiry[sid] = expires_at
