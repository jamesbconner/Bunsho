"""Factory functions that build concrete services from configuration."""

from __future__ import annotations

import logging

from bunsho.config.settings import AppConfig
from bunsho.context import Context
from bunsho.orchestration.content_build import ContentBuildError, ContentBuildOrchestrator
from bunsho.services.anki_importer import AnkiDeckImporter
from bunsho.services.content_repository import ContentRepository, ContentWriter
from bunsho.services.jamdict_service import JamdictService, JamdictUnavailableError
from bunsho.services.kana_source import KanaSource
from bunsho.services.protocols import KanjiInfoSource


def create_context(
    config: AppConfig, *, dry_run: bool = False, logger: logging.Logger | None = None
) -> Context:
    """Build a ``Context``, tolerating optional services that fail to start.

    A jamdict failure is logged as a warning and leaves ``kanji_source`` as ``None``;
    ``content_repo`` is set only when ``content.db`` already exists.

    Args:
        config: Validated configuration.
        dry_run: Operational flag carried on the context.
        logger: Logger to use (defaults to ``bunsho``).

    Returns:
        The initialized context.
    """
    log = logger or logging.getLogger("bunsho")
    kanji_source: KanjiInfoSource | None = None
    try:
        kanji_source = JamdictService(config.jamdict_db)
    except JamdictUnavailableError as exc:
        log.warning("service_init_failed service=jamdict error=%s", exc)
    content_repo = (
        ContentRepository(config.content_db_path) if config.content_db_path.is_file() else None
    )
    return Context(
        config=config,
        logger=log,
        dry_run=dry_run,
        kanji_source=kanji_source,
        content_repo=content_repo,
    )


def create_content_build_orchestrator(ctx: Context) -> ContentBuildOrchestrator:
    """Assemble the content build orchestrator.

    Raises:
        ContentBuildError: If the jamdict service is unavailable.
    """
    if ctx.kanji_source is None:
        raise ContentBuildError(
            "cannot build content: the jamdict database is unavailable "
            "(install jamdict-data-fix or set paths.jamdict_db)"
        )
    return ContentBuildOrchestrator(
        importer=AnkiDeckImporter(ctx.config.deck_sha256, ctx.logger),
        kana_provider=KanaSource(),
        kanji_source=ctx.kanji_source,
        writer=ContentWriter(),
        logger=ctx.logger,
    )
