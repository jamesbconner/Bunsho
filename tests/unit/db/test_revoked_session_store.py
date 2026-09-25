from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from bunsho.db.engine import ProgressDatabase
from bunsho.db.models import RevokedSession
from bunsho.db.revoked_session_store import RevokedSessionStore
from tests.base import run_with_database

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


async def _stored_sids(database: ProgressDatabase) -> list[str]:
    async with database.sessions() as session:
        return sorted((await session.scalars(select(RevokedSession.sid))).all())


def test_a_revoked_session_is_revoked_and_another_is_not(tmp_path: Path) -> None:
    async def scenario(database: ProgressDatabase) -> tuple[bool, bool]:
        store = RevokedSessionStore(database, clock=lambda: NOW)
        await store.revoke("sid-a", NOW + timedelta(days=30))
        return store.is_revoked("sid-a"), store.is_revoked("sid-b")

    assert run_with_database(tmp_path, scenario) == (True, False)


def test_a_new_instance_sees_revocations_only_after_load(tmp_path: Path) -> None:
    async def scenario(database: ProgressDatabase) -> tuple[bool, bool]:
        first = RevokedSessionStore(database, clock=lambda: NOW)
        await first.revoke("sid-a", NOW + timedelta(days=30))
        second = RevokedSessionStore(database, clock=lambda: NOW)
        before = second.is_revoked("sid-a")
        await second.load()
        return before, second.is_revoked("sid-a")

    assert run_with_database(tmp_path, scenario) == (False, True)


def test_load_prunes_rows_whose_revocation_has_lapsed(tmp_path: Path) -> None:
    async def scenario(database: ProgressDatabase) -> tuple[bool, bool, list[str]]:
        early = RevokedSessionStore(database, clock=lambda: NOW)
        await early.revoke("old", NOW + timedelta(days=1))
        await early.revoke("fresh", NOW + timedelta(days=30))
        later = RevokedSessionStore(database, clock=lambda: NOW + timedelta(days=2))
        await later.load()
        return later.is_revoked("old"), later.is_revoked("fresh"), await _stored_sids(database)

    assert run_with_database(tmp_path, scenario) == (False, True, ["fresh"])


def test_revoke_prunes_lapsed_rows_and_forgets_them(tmp_path: Path) -> None:
    async def scenario(database: ProgressDatabase) -> tuple[bool, bool, list[str]]:
        clock = [NOW]
        store = RevokedSessionStore(database, clock=lambda: clock[0])
        await store.revoke("old", NOW + timedelta(days=1))
        clock[0] = NOW + timedelta(days=2)
        await store.revoke("new", clock[0] + timedelta(days=30))
        return store.is_revoked("old"), store.is_revoked("new"), await _stored_sids(database)

    assert run_with_database(tmp_path, scenario) == (False, True, ["new"])


def test_revoking_twice_keeps_one_row_and_the_later_expiry(tmp_path: Path) -> None:
    async def scenario(database: ProgressDatabase) -> tuple[list[str], bool]:
        store = RevokedSessionStore(database, clock=lambda: NOW)
        await store.revoke("sid-a", NOW + timedelta(days=1))
        await store.revoke("sid-a", NOW + timedelta(days=5))
        reloaded = RevokedSessionStore(database, clock=lambda: NOW + timedelta(days=2))
        await reloaded.load()  # a day-1 expiry would have been pruned by now
        return await _stored_sids(database), reloaded.is_revoked("sid-a")

    assert run_with_database(tmp_path, scenario) == (["sid-a"], True)


def test_a_failed_write_leaves_the_session_unrevoked(tmp_path: Path) -> None:
    class BrokenDatabase:
        def sessions(self) -> None:
            raise RuntimeError("database is down")

    async def scenario(_database: ProgressDatabase) -> bool:
        store = RevokedSessionStore(BrokenDatabase(), clock=lambda: NOW)  # type: ignore[arg-type]
        with pytest.raises(RuntimeError, match="database is down"):
            await store.revoke("sid-a", NOW + timedelta(days=30))
        return store.is_revoked("sid-a")

    assert run_with_database(tmp_path, scenario) is False
