"""Access to the content repository once it is known to be usable."""

from __future__ import annotations

import asyncio
import sqlite3

from bunsho.context import Context
from bunsho.models.review import ContentNotReadyError
from bunsho.services.content_repository import ContentRepository, ContentSchemaError


class ContentGate:
    """Hands out ``ctx.content_repo`` after checking its schema once per repository object.

    A content build replaces ``ctx.content_repo`` with a new object, so a rebuilt database is
    verified again automatically.
    """

    def __init__(self, ctx: Context) -> None:
        """Create the gate.

        Args:
            ctx: The application context whose ``content_repo`` is read on every call.
        """
        self._ctx = ctx
        self._verified: ContentRepository | None = None

    async def repository(self) -> ContentRepository:
        """Return the content repository.

        Raises:
            ContentNotReadyError: Content has not been built, has another schema version,
                or cannot be read.
        """
        repo = self._ctx.content_repo
        if repo is None:
            raise ContentNotReadyError("content has not been built yet; run a content build")
        if repo is not self._verified:
            try:
                await asyncio.to_thread(repo.verify_schema)
            except ContentSchemaError as exc:
                raise ContentNotReadyError(str(exc)) from exc
            except (sqlite3.Error, OSError) as exc:
                self._ctx.logger.warning("content_unreadable error=%s: %s", type(exc).__name__, exc)
                raise ContentNotReadyError("content.db cannot be read; see /health") from exc
            self._verified = repo
        return repo
