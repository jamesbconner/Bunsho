import logging
from pathlib import Path

import pytest

from bunsho.db.engine import ProgressDatabase
from bunsho.db.progress_repository import ProgressRepository
from bunsho.models.review_settings import KanaGate, NewCardPolicyName, ReviewSettings, TypeEnabled
from bunsho.services.review_settings import SETTINGS_KEY, ReviewSettingsService
from tests.base import run_with_database

LOGGER = logging.getLogger("bunsho.tests.settings")


def test_load_returns_defaults_when_nothing_was_saved(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        service = ReviewSettingsService(ProgressRepository(db), LOGGER)
        assert await service.load() == ReviewSettings()

    run_with_database(tmp_path, scenario)


def test_saved_settings_are_loaded_back(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        service = ReviewSettingsService(ProgressRepository(db), LOGGER)
        chosen = ReviewSettings(
            new_card_policy=NewCardPolicyName.MASTERY_UNLOCK, target_retention=0.85
        )
        assert await service.save(chosen) == chosen
        assert await service.load() == chosen

    run_with_database(tmp_path, scenario)


def test_an_unreadable_stored_document_falls_back_to_defaults_with_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        repo = ProgressRepository(db)
        await repo.set_setting(SETTINGS_KEY, '{"rollover_hour": 99}')
        service = ReviewSettingsService(repo, LOGGER)
        assert await service.load() == ReviewSettings()

    with caplog.at_level(logging.WARNING, logger=LOGGER.name):
        run_with_database(tmp_path, scenario)
    assert "review_settings_invalid" in caplog.text
    assert "rollover_hour" in caplog.text


def test_a_document_saved_before_the_type_switches_existed_loads_with_todays_behaviour(
    tmp_path: Path,
) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        repo = ProgressRepository(db)
        await repo.set_setting(
            SETTINGS_KEY, '{"new_card_policy": "mastery_unlock", "target_retention": 0.85}'
        )
        loaded = await ReviewSettingsService(repo, LOGGER).load()
        assert loaded == ReviewSettings(
            new_card_policy=NewCardPolicyName.MASTERY_UNLOCK, target_retention=0.85
        )
        assert loaded.type_enabled == TypeEnabled()
        assert loaded.kana_gate == KanaGate()

    run_with_database(tmp_path, scenario)
