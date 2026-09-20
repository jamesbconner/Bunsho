import asyncio
from pathlib import Path

import pytest

from bunsho.db.engine import ProgressDatabase
from bunsho.db.migrate import run_migrations
from bunsho.db.models import AppSetting, CardState


def test_round_trip_through_the_async_engine(tmp_path: Path) -> None:
    path = tmp_path / "progress.db"
    run_migrations(path, backup_dir=tmp_path / "backups")

    async def scenario() -> tuple[str, int]:
        database = ProgressDatabase(path)
        try:
            await database.ping()
            async with database.sessions() as session:
                session.add(AppSetting(key="theme", value="dark"))
                session.add(
                    CardState(
                        item_id="kana:hira:あ", direction="glyph-sound", due="2026-01-01T00:00:00Z"
                    )
                )
                await session.commit()
            async with database.sessions() as session:
                setting = await session.get(AppSetting, "theme")
                card = await session.get(CardState, 1)
                assert setting is not None
                assert card is not None
                return setting.value, card.reps
        finally:
            await database.dispose()

    assert asyncio.run(scenario()) == ("dark", 0)


def test_ping_fails_for_an_unreachable_database(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = ProgressDatabase(tmp_path / "missing-dir" / "progress.db")
        try:
            await database.ping()
        finally:
            await database.dispose()

    with pytest.raises(Exception):  # noqa: B017,PT011 - driver-specific OperationalError
        asyncio.run(scenario())
