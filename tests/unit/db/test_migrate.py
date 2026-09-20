import logging
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.util.exc import CommandError
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


def test_backup_is_logged_on_a_successful_upgrade(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    db = tmp_path / "progress.db"
    with closing(sqlite3.connect(db)) as con, con:
        con.execute("CREATE TABLE legacy (v TEXT)")
    logger = logging.getLogger("bunsho.test_migrate")
    with caplog.at_level(logging.INFO, logger=logger.name):
        result = run_migrations(db, backup_dir=tmp_path / "backups", now=lambda: NOW, logger=logger)
    assert f"progress_db_backup_created path={result.backup_path} from=unversioned" in caplog.text


def test_failed_migration_keeps_and_logs_the_backup(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    db = tmp_path / "progress.db"
    with closing(sqlite3.connect(db)) as con, con:
        con.execute("CREATE TABLE card_state (x TEXT)")
    logger = logging.getLogger("bunsho.test_migrate")
    with caplog.at_level(logging.INFO, logger=logger.name), pytest.raises(DatabaseError):
        run_migrations(db, backup_dir=tmp_path / "backups", now=lambda: NOW, logger=logger)
    backup = tmp_path / "backups" / "progress-20260102T030405Z-from-unversioned.db"
    assert "card_state" in _tables(backup)
    with closing(sqlite3.connect(backup)) as con:
        assert [row[1] for row in con.execute("PRAGMA table_info(card_state)")] == ["x"]
    assert "progress_db_backup_created" in caplog.text
    assert "progress_db_migration_failed" in caplog.text


def test_corrupt_database_fails_fast_without_a_backup(tmp_path: Path) -> None:
    db = tmp_path / "progress.db"
    db.write_bytes(b"this is not a sqlite database" * 20)
    with pytest.raises(DatabaseError):
        run_migrations(db, backup_dir=tmp_path / "backups", now=lambda: NOW)
    assert not (tmp_path / "backups").exists()


def test_unknown_revision_raises_after_a_backup_and_leaves_the_database_untouched(
    tmp_path: Path,
) -> None:
    db = tmp_path / "progress.db"
    with closing(sqlite3.connect(db)) as con, con:
        con.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        con.execute("INSERT INTO alembic_version VALUES ('from_the_future')")
    original = db.read_bytes()
    with pytest.raises(CommandError):
        run_migrations(db, backup_dir=tmp_path / "backups", now=lambda: NOW)
    assert db.read_bytes() == original
    backup = tmp_path / "backups" / "progress-20260102T030405Z-from-from_the_future.db"
    with closing(sqlite3.connect(backup)) as con:
        assert con.execute("SELECT version_num FROM alembic_version").fetchall() == [
            ("from_the_future",)
        ]


def _legacy_db(path: Path, value: str) -> None:
    with closing(sqlite3.connect(path)) as con, con:
        con.execute("CREATE TABLE legacy (v TEXT)")
        con.execute("INSERT INTO legacy VALUES (?)", (value,))


def test_a_backup_name_collision_never_overwrites_an_existing_backup(tmp_path: Path) -> None:
    first, second = tmp_path / "one.db", tmp_path / "two.db"
    _legacy_db(first, "first")
    _legacy_db(second, "second")
    backups = tmp_path / "backups"
    one = run_migrations(first, backup_dir=backups, now=lambda: NOW).backup_path
    two = run_migrations(second, backup_dir=backups, now=lambda: NOW).backup_path
    assert one is not None
    assert two is not None
    assert one != two
    assert one.name == "progress-20260102T030405Z-from-unversioned.db"
    assert two.name == "progress-20260102T030405Z-from-unversioned-2.db"
    for backup, value in ((one, "first"), (two, "second")):
        with closing(sqlite3.connect(backup)) as con:
            assert con.execute("SELECT v FROM legacy").fetchall() == [(value,)]


def test_a_third_collision_gets_the_next_suffix(tmp_path: Path) -> None:
    backups = tmp_path / "backups"
    names = []
    for index in range(3):
        db = tmp_path / f"db{index}.db"
        _legacy_db(db, str(index))
        result = run_migrations(db, backup_dir=backups, now=lambda: NOW)
        assert result.backup_path is not None
        names.append(result.backup_path.name)
    assert names == [
        "progress-20260102T030405Z-from-unversioned.db",
        "progress-20260102T030405Z-from-unversioned-2.db",
        "progress-20260102T030405Z-from-unversioned-3.db",
    ]


def test_the_backup_stamp_is_normalised_to_utc(tmp_path: Path) -> None:
    db = tmp_path / "progress.db"
    _legacy_db(db, "x")
    tokyo = datetime(2026, 1, 2, 12, 4, 5, tzinfo=timezone(timedelta(hours=9)))
    result = run_migrations(db, backup_dir=tmp_path / "backups", now=lambda: tokyo)
    assert result.backup_path is not None
    assert result.backup_path.name == "progress-20260102T030405Z-from-unversioned.db"


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
