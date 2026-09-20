"""The API's shared service container and its construction."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from dataclasses import dataclass

from alembic.util.exc import CommandError
from sqlalchemy.exc import DatabaseError

from bunsho.config.service import ServiceConfig
from bunsho.context import Context
from bunsho.db.engine import ProgressDatabase
from bunsho.db.instance_lock import InstanceLock, InstanceLockedError
from bunsho.db.migrate import run_migrations
from bunsho.factories import create_content_build_orchestrator, create_context
from bunsho.orchestration.build_tasks import BuildTaskManager, OrchestratorFactory
from bunsho.services.auth import AuthService
from bunsho.services.content_repository import ContentSchemaError, remove_stale_temp_files
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
    instance_lock: InstanceLock

    async def aclose(self) -> None:
        """Wait briefly for an active build, close the engine, release the instance lock.

        The engine is disposed and the lock released even if waiting for the build fails or
        is cancelled.
        """
        try:
            await self.tasks.aclose()
        finally:
            try:
                await self.progress_db.dispose()
            finally:
                self.instance_lock.release()


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
    lock = InstanceLock(app_config.data_dir)
    try:
        lock.acquire()
    except InstanceLockedError as exc:
        logger.error("instance_lock_held path=%s", lock.path)
        raise StartupError(str(exc)) from exc
    except OSError as exc:
        raise StartupError(
            f"cannot create the instance lock in {app_config.data_dir} "
            f"({type(exc).__name__}: {exc}). Check that the data folder exists and is "
            "writable by the service user."
        ) from exc
    try:
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
            await _check_content_schema(ctx, logger)
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
                instance_lock=lock,
            )
        except BaseException:
            await progress_db.dispose()
            raise
    except BaseException:
        lock.release()
        raise


async def _check_content_schema(ctx: Context, logger: logging.Logger) -> None:
    """Log (at ERROR) when ``content.db`` exists but cannot be used; never blocks startup.

    ``/health`` reports the same problem as ``degraded`` and the review endpoints answer 503
    until the content is rebuilt.
    """
    if ctx.content_repo is None:
        return
    try:
        await asyncio.to_thread(ctx.content_repo.verify_schema)
    except (ContentSchemaError, sqlite3.Error, OSError) as exc:
        logger.error("content_schema_check_failed error=%s: %s", type(exc).__name__, exc)
