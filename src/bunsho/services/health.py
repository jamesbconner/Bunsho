"""Health checks for the API service's dependencies."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal, Protocol

from bunsho.context import Context
from bunsho.services.content_repository import ContentSchemaError

Status = Literal["ok", "degraded", "error"]
_SEVERITY: dict[Status, int] = {"ok": 0, "degraded": 1, "error": 2}


class _Pingable(Protocol):
    async def ping(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ComponentHealth:
    """Health of one component."""

    status: Status
    detail: str = ""
    latency_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class HealthReport:
    """Overall health: the worst component status plus every component."""

    status: Status
    components: dict[str, ComponentHealth]


class HealthService:
    """Checks ``progress.db``, ``content.db`` and jamdict."""

    def __init__(self, progress_db: _Pingable, ctx: Context) -> None:
        """Create the service.

        Args:
            progress_db: Anything with ``async ping()`` (normally ``ProgressDatabase``).
            ctx: Application context holding the content repository and jamdict handle.
        """
        self._progress_db = progress_db
        self._ctx = ctx

    async def check(self) -> HealthReport:
        """Run every check; never raises."""
        components = {
            "progress_db": await self._check_progress_db(),
            "content_db": self._check_content_db(),
            "jamdict": self._check_jamdict(),
        }
        worst = max((c.status for c in components.values()), key=_SEVERITY.__getitem__)
        return HealthReport(status=worst, components=components)

    async def _check_progress_db(self) -> ComponentHealth:
        started = time.perf_counter()
        try:
            await self._progress_db.ping()
        except Exception as exc:
            elapsed = (time.perf_counter() - started) * 1000
            # The endpoint is unauthenticated: expose the class name only, log the rest.
            self._ctx.logger.warning(
                "health_check_failed component=progress_db error=%s: %s", type(exc).__name__, exc
            )
            return ComponentHealth("error", type(exc).__name__, elapsed)
        return ComponentHealth("ok", latency_ms=(time.perf_counter() - started) * 1000)

    def _check_content_db(self) -> ComponentHealth:
        repo = self._ctx.content_repo
        if repo is None:
            return ComponentHealth("degraded", "content.db not built yet; run a content build")
        started = time.perf_counter()
        try:
            repo.verify_schema()
        except ContentSchemaError as exc:
            return ComponentHealth("degraded", str(exc))
        except Exception as exc:  # sqlite3.Error/OSError expected; anything else must not 500
            self._ctx.logger.warning(
                "health_check_failed component=content_db error=%s: %s", type(exc).__name__, exc
            )
            return ComponentHealth("degraded", type(exc).__name__)
        return ComponentHealth("ok", latency_ms=(time.perf_counter() - started) * 1000)

    def _check_jamdict(self) -> ComponentHealth:
        if self._ctx.kanji_source is None:
            return ComponentHealth("degraded", "jamdict database unavailable; builds are disabled")
        return ComponentHealth("ok")
