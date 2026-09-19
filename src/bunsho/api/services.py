"""The API's shared service container and its construction."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from bunsho.config.service import ServiceConfig
from bunsho.context import Context
from bunsho.db.engine import ProgressDatabase
from bunsho.db.migrate import run_migrations
from bunsho.factories import create_content_build_orchestrator, create_context
from bunsho.orchestration.build_tasks import BuildTaskManager, OrchestratorFactory
from bunsho.services.auth import AuthService
from bunsho.services.health import HealthService
from bunsho.services.login_throttle import LoginThrottle


@dataclass(slots=True)
class Services:
    """Everything request handlers share."""

    config: ServiceConfig
    ctx: Context
    progress_db: ProgressDatabase
    auth: AuthService
    throttle: LoginThrottle
    tasks: BuildTaskManager
    health: HealthService

    async def aclose(self) -> None:
        """Wait briefly for an active build, then close the database engine."""
        await self.tasks.aclose()
        await self.progress_db.dispose()


@dataclass(frozen=True, slots=True)
class ServiceOverrides:
    """Test seams for ``build_services``."""

    orchestrator_factory: OrchestratorFactory | None = None


async def build_services(
    config: ServiceConfig, overrides: ServiceOverrides | None = None
) -> Services:
    """Migrate ``progress.db`` and wire every service.

    Args:
        config: Validated service configuration.
        overrides: Optional test seams.

    Returns:
        The service container.

    Raises:
        Exception: A migration or the ``progress.db`` ping failed (fail fast).
    """
    logger = logging.getLogger("bunsho")
    app_config = config.app
    await asyncio.to_thread(
        run_migrations,
        app_config.progress_db_path,
        backup_dir=app_config.data_dir / "backups",
        logger=logger,
    )
    progress_db = ProgressDatabase(app_config.progress_db_path)
    try:
        await progress_db.ping()
        ctx = await asyncio.to_thread(create_context, app_config, logger=logger)
        factory = (overrides.orchestrator_factory if overrides else None) or (
            create_content_build_orchestrator
        )
        return Services(
            config=config,
            ctx=ctx,
            progress_db=progress_db,
            auth=AuthService(config.auth),
            throttle=LoginThrottle(),
            tasks=BuildTaskManager(ctx, factory),
            health=HealthService(progress_db, ctx),
        )
    except BaseException:
        await progress_db.dispose()
        raise
