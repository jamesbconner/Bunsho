import dataclasses
import logging
from pathlib import Path

import pytest

from bunsho.config.settings import AppConfig
from bunsho.factories import create_content_build_orchestrator, create_context
from bunsho.orchestration.content_build import ContentBuildError, ContentBuildOrchestrator
from bunsho.services.content_repository import ContentWriter
from tests.base import FakeKanjiSource, make_vocab

LOGGER_NAME = "bunsho.test_factories"


def test_missing_jamdict_degrades_gracefully(
    app_config: AppConfig, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config = dataclasses.replace(app_config, jamdict_db=tmp_path / "missing.db")
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        ctx = create_context(config, logger=logging.getLogger(LOGGER_NAME))
    assert ctx.kanji_source is None
    assert "service_init_failed service=jamdict" in caplog.text
    with pytest.raises(ContentBuildError, match="jamdict"):
        create_content_build_orchestrator(ctx)


def test_content_repo_only_when_database_exists(
    app_config: AppConfig, quiet_logger: logging.Logger
) -> None:
    assert create_context(app_config, logger=quiet_logger).content_repo is None
    ContentWriter().write(
        app_config.content_db_path, kana=[], kanji=[], vocab=[make_vocab()], meta={}
    )
    ctx = create_context(app_config, dry_run=True, logger=quiet_logger)
    assert ctx.content_repo is not None
    assert ctx.content_repo.counts().vocab == 1
    assert ctx.dry_run is True


def test_orchestrator_is_built_from_context(
    app_config: AppConfig, quiet_logger: logging.Logger
) -> None:
    ctx = create_context(app_config, logger=quiet_logger)
    ctx.kanji_source = FakeKanjiSource()
    assert isinstance(create_content_build_orchestrator(ctx), ContentBuildOrchestrator)


def test_refresh_content_repo_follows_the_database_file(
    app_config: AppConfig, quiet_logger: logging.Logger
) -> None:
    ctx = create_context(app_config, logger=quiet_logger)
    assert ctx.content_repo is None
    assert ctx.refresh_content_repo() is None

    ContentWriter().write(
        app_config.content_db_path, kana=[], kanji=[], vocab=[make_vocab()], meta={}
    )
    repo = ctx.refresh_content_repo()
    assert repo is not None
    assert ctx.content_repo is repo
    assert repo.counts().vocab == 1

    app_config.content_db_path.unlink()
    assert ctx.refresh_content_repo() is None
    assert ctx.content_repo is None
