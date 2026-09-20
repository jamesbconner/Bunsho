"""Async access to ``progress.db``."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


class ProgressDatabase:
    """Async engine and session factory for ``progress.db``.

    The schema is managed by Alembic (see ``bunsho.db.migrate``); this class never
    creates tables.
    """

    def __init__(self, path: Path) -> None:
        """Create the engine (no connection is opened until first use).

        Args:
            path: Location of ``progress.db``.
        """
        self._engine = create_async_engine(URL.create("sqlite+aiosqlite", database=str(path)))
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
