"""Run ``progress.db`` migrations, backing up an existing database first."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


@dataclass(frozen=True, slots=True)
class MigrationResult:
    """Outcome of ``run_migrations``."""

    from_revision: str | None
    to_revision: str
    upgraded: bool
    backup_path: Path | None


def _config(db_path: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR).replace("%", "%%"))
    cfg.attributes["db_path"] = str(db_path)
    return cfg


def _current_revision(db_path: Path) -> str | None:
    engine = create_engine(URL.create("sqlite", database=str(db_path)))
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def _backup(db_path: Path, backup_dir: Path, revision: str | None, stamp: datetime) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    name = f"progress-{stamp.strftime('%Y%m%dT%H%M%SZ')}-from-{revision or 'unversioned'}.db"
    target = backup_dir / name
    with closing(sqlite3.connect(db_path)) as source, closing(sqlite3.connect(target)) as dest:
        source.backup(dest)
    return target


def run_migrations(
    db_path: Path,
    *,
    backup_dir: Path,
    now: Callable[[], datetime] | None = None,
    logger: logging.Logger | None = None,
) -> MigrationResult:
    """Bring ``progress.db`` to the latest schema, backing it up first if it exists.

    Args:
        db_path: Location of ``progress.db`` (created if missing).
        backup_dir: Where the pre-migration backup is written.
        now: Clock used for the backup file name (defaults to UTC now).
        logger: Logger for key=value messages.

    Returns:
        What happened, including the backup path when one was made.

    Raises:
        sqlalchemy.exc.DatabaseError: The file is not a valid SQLite database, or a
            migration failed part-way (any backup taken beforehand is kept and its
            path is logged).
    """
    log = logger or logging.getLogger(__name__)
    clock = now or (lambda: datetime.now(UTC))
    cfg = _config(db_path)
    head = ScriptDirectory.from_config(cfg).get_current_head()
    if head is None:
        raise RuntimeError("no progress.db migrations found")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    existed = db_path.is_file()
    current = _current_revision(db_path) if existed else None
    if existed and current == head:
        log.info("progress_db_up_to_date revision=%s path=%s", head, db_path)
        return MigrationResult(current, head, False, None)
    backup = _backup(db_path, backup_dir, current, clock()) if existed else None
    if backup is not None:
        log.info("progress_db_backup_created path=%s from=%s", backup, current or "unversioned")
    try:
        command.upgrade(cfg, "head")
    except Exception:
        log.exception(
            "progress_db_migration_failed from=%s backup=%s path=%s", current, backup, db_path
        )
        raise
    log.info(
        "progress_db_migrated from=%s to=%s backup=%s path=%s",
        current,
        head,
        backup,
        db_path,
    )
    return MigrationResult(current, head, True, backup)
