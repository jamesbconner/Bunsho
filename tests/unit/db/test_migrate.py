import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.exc import DatabaseError

from bunsho.db.migrate import run_migrations
from bunsho.db.models import Base

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def _tables(db_path: Path) -> set[str]:
    with closing(sqlite3.connect(db_path)) as con:
        return {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_fresh_database_is_created_without_backup(tmp_path: Path) -> None:
    db = tmp_path / "data" / "progress.db"
    result = run_migrations(db, backup_dir=tmp_path / "backups", now=lambda: NOW)
    assert (result.from_revision, result.to_revision) == (None, "0001")
    assert result.upgraded is True
    assert result.backup_path is None
    assert {"card_state", "review_log", "app_setting", "alembic_version"} <= _tables(db)
    assert not (tmp_path / "backups").exists()


def test_second_run_is_a_no_op(tmp_path: Path) -> None:
    db = tmp_path / "progress.db"
    run_migrations(db, backup_dir=tmp_path / "backups", now=lambda: NOW)
    again = run_migrations(db, backup_dir=tmp_path / "backups", now=lambda: NOW)
    assert (again.from_revision, again.upgraded, again.backup_path) == ("0001", False, None)
    assert not (tmp_path / "backups").exists()


def test_existing_unversioned_database_is_backed_up_then_upgraded(tmp_path: Path) -> None:
    db = tmp_path / "progress.db"
    with closing(sqlite3.connect(db)) as con, con:
        con.execute("CREATE TABLE legacy (v TEXT)")
        con.execute("INSERT INTO legacy VALUES ('keep me')")
    result = run_migrations(db, backup_dir=tmp_path / "backups", now=lambda: NOW)
    assert result.upgraded is True
    expected = tmp_path / "backups" / "progress-20260102T030405Z-from-unversioned.db"
    assert result.backup_path == expected
    with closing(sqlite3.connect(expected)) as con:
        assert con.execute("SELECT v FROM legacy").fetchall() == [("keep me",)]
    assert "card_state" not in _tables(expected)  # backup predates the upgrade
    assert {"legacy", "card_state"} <= _tables(db)


def test_corrupt_database_fails_fast_without_a_backup(tmp_path: Path) -> None:
    db = tmp_path / "progress.db"
    db.write_bytes(b"this is not a sqlite database" * 20)
    with pytest.raises(DatabaseError):
        run_migrations(db, backup_dir=tmp_path / "backups", now=lambda: NOW)
    assert not (tmp_path / "backups").exists()


def test_migration_matches_the_models(tmp_path: Path) -> None:
    db = tmp_path / "progress.db"
    run_migrations(db, backup_dir=tmp_path / "backups", now=lambda: NOW)
    engine = create_engine(URL.create("sqlite", database=str(db)))
    try:
        with engine.connect() as connection:
            differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    finally:
        engine.dispose()
    assert differences == []
