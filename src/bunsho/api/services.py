"""The API's shared service container and its construction."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from alembic.util.exc import CommandError
from sqlalchemy.exc import DatabaseError

from bunsho.config.service import ServiceConfig
from bunsho.context import Context
from bunsho.db.engine import ProgressDatabase
from bunsho.db.migrate import run_migrations
from bunsho.factories import create_content_build_orchestrator, create_context
from bunsho.orchestration.build_tasks import BuildTaskManager, OrchestratorFactory
from bunsho.services.auth import AuthService
from bunsho.services.content_repository import remove_stale_temp_files
from bunsho.services.health import HealthService
from bunsho.services.login_throttle import LoginThrottle


class StartupError(RuntimeError):
    """The service cannot start; the message says what to check."""


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
        """Wait briefly for an active build, then close the database engine.

        The engine is disposed even if waiting for the build fails or is cancelled.
        """
        try:
            await self.tasks.aclose()
        finally:
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
        StartupError: ``progress.db`` could not be opened or migrated (corrupt, unknown
            revision, not writable, or another process held the migration lock too long).
        Exception: The ``progress.db`` ping or context creation failed (fail fast).
    """
    logger = logging.getLogger("bunsho")
    app_config = config.app
    backup_dir = app_config.data_dir / "backups"
    try:
        await asyncio.to_thread(
            run_migrations, app_config.progress_db_path, backup_dir=backup_dir, logger=logger
        )
    except (DatabaseError, CommandError, OSError) as exc:  # OSError includes filelock.Timeout
        logger.error(
            "progress_db_startup_failed path=%s backups=%s error=%s: %s",
            app_config.progress_db_path,
            backup_dir,
            type(exc).__name__,
            exc,
        )
        raise StartupError(
            f"progress.db could not be opened or migrated ({type(exc).__name__}). "
            f"Database: {app_config.progress_db_path}. Backups: {backup_dir}. "
            "Check that the data folder is writable by the service user and that the file is "
            "a Bunshō progress database. To restore, stop the service and copy a backup over "
            "progress.db."
        ) from exc
    await asyncio.to_thread(remove_stale_temp_files, app_config.content_db_path, logger)
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
