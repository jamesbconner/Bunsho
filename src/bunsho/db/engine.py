"""Async access to ``progress.db``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _configure_connection(dbapi_connection: Any, _connection_record: Any) -> None:
    """Apply the pragmas every ``progress.db`` connection needs.

    WAL lets readers proceed while a review is being written and is persistent in the file;
    ``foreign_keys`` is per connection and must be set each time.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


class ProgressDatabase:
    """Async engine and session factory for ``progress.db``.

    The schema is managed by Alembic (see ``bunsho.db.migrate``); this class never
    creates tables. Every connection runs in WAL mode with foreign keys enforced.
    """

    def __init__(self, path: Path) -> None:
        """Create the engine (no connection is opened until first use).

        Args:
            path: Location of ``progress.db``.
        """
        self._engine = create_async_engine(URL.create("sqlite+aiosqlite", database=str(path)))
        event.listen(self._engine.sync_engine, "connect", _configure_connection)
        self.sessions: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine, expire_on_commit=False
        )

    async def ping(self) -> None:
        """Run ``SELECT 1``; raises if the database cannot be opened."""
        async with self._engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def dispose(self) -> None:
        """Close pooled connections."""
        await self._engine.dispose()
