import dataclasses
import logging
import sqlite3
from pathlib import Path

import pytest

from bunsho.config.settings import AppConfig
from bunsho.factories import create_content_build_orchestrator, create_context
from bunsho.models.content import ImportedDeck
from bunsho.orchestration.content_build import ContentBuildError, ContentBuildOrchestrator
from bunsho.services.content_repository import ContentWriter
from tests.base import FakeKanjiCatalog, FakeKanjiSource, make_kanji_details, make_vocab

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


def test_context_exposes_the_catalog_when_jamdict_is_available(
    app_config: AppConfig, quiet_logger: logging.Logger, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = FakeKanjiSource()
    monkeypatch.setattr("bunsho.factories.JamdictService", lambda _db_file: service)
    ctx = create_context(app_config, logger=quiet_logger)
    assert ctx.kanji_source is service
    assert ctx.kanji_catalog is service  # one JamdictService plays both roles


def test_context_has_no_catalog_when_jamdict_is_unavailable(
    app_config: AppConfig, tmp_path: Path, quiet_logger: logging.Logger
) -> None:
    config = dataclasses.replace(app_config, jamdict_db=tmp_path / "missing.db")
    ctx = create_context(config, logger=quiet_logger)
    assert ctx.kanji_source is None
    assert ctx.kanji_catalog is None


class _EmptyDeckImporter:
    def __init__(self, *_args: object) -> None:
        pass

    def import_vocab(self, deck_path: Path) -> ImportedDeck:
        return ImportedDeck(vocab=[], sha256="a" * 64)


def test_orchestrator_from_context_stores_unleveled_kanji_from_the_context_catalog(
    app_config: AppConfig, quiet_logger: logging.Logger, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("bunsho.factories.AnkiDeckImporter", _EmptyDeckImporter)
    ctx = create_context(app_config, logger=quiet_logger)
    ctx.kanji_source = FakeKanjiSource({"犬": make_kanji_details(grade=1)})
    ctx.kanji_catalog = FakeKanjiCatalog(["犬"])

    report = create_content_build_orchestrator(ctx).build(
        app_config.deck_path, app_config.content_db_path
    )

    assert report.unleveled_kanji_count == 1
    assert report.kanji_count == 1
    repo = ctx.refresh_content_repo()
    assert repo is not None
    assert [k.char for k in repo.list_kanji(unleveled=True)] == ["犬"]


def test_orchestrator_from_context_without_a_catalog_stores_only_deck_kanji(
    app_config: AppConfig, quiet_logger: logging.Logger, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("bunsho.factories.AnkiDeckImporter", _EmptyDeckImporter)
    ctx = create_context(app_config, logger=quiet_logger)
    ctx.kanji_source = FakeKanjiSource({"犬": make_kanji_details(grade=1)})
    ctx.kanji_catalog = None

    report = create_content_build_orchestrator(ctx).build(
        app_config.deck_path, app_config.content_db_path
    )

    assert (report.kanji_count, report.unleveled_kanji_count) == (0, 0)


@pytest.mark.parametrize("error", [OSError("unreadable"), sqlite3.DatabaseError("corrupt")])
def test_jamdict_os_and_sqlite_errors_degrade_gracefully(
    app_config: AppConfig,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
) -> None:
    def broken(_db_file: object) -> None:
        raise error

    monkeypatch.setattr("bunsho.factories.JamdictService", broken)
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        ctx = create_context(app_config, logger=logging.getLogger(LOGGER_NAME))
    assert ctx.kanji_source is None
    assert ctx.kanji_catalog is None
    assert "service_init_failed service=jamdict" in caplog.text
