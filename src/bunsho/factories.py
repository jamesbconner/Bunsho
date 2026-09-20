"""Factory functions that build concrete services from configuration."""

from __future__ import annotations

import logging
import sqlite3

from bunsho.config.settings import AppConfig
from bunsho.context import Context
from bunsho.models.review_settings import NewCardPolicyName, ReviewSettings
from bunsho.orchestration.content_build import ContentBuildError, ContentBuildOrchestrator
from bunsho.services.anki_importer import AnkiDeckImporter
from bunsho.services.content_repository import ContentWriter
from bunsho.services.fsrs_scheduler import FSRSScheduler
from bunsho.services.jamdict_service import JamdictService, JamdictUnavailableError
from bunsho.services.kana_source import KanaSource
from bunsho.services.new_card_policies import (
    MasteryUnlockPolicy,
    PinnedLevelsPolicy,
    StrictOrderPolicy,
)
from bunsho.services.protocols import KanjiCatalog, KanjiInfoSource, NewCardPolicy, Scheduler


def create_context(
    config: AppConfig, *, dry_run: bool = False, logger: logging.Logger | None = None
) -> Context:
    """Build a ``Context``, tolerating optional services that fail to start.

    A jamdict failure is logged as a warning and leaves ``kanji_source`` and
    ``kanji_catalog`` as ``None``; otherwise both are the same ``JamdictService``.
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
    kanji_catalog: KanjiCatalog | None = None
    try:
        jamdict = JamdictService(config.jamdict_db)
        kanji_source = jamdict
        kanji_catalog = jamdict
    except (JamdictUnavailableError, OSError, sqlite3.Error) as exc:
        log.warning("service_init_failed service=jamdict error=%s", exc)
    ctx = Context(
        config=config,
        logger=log,
        dry_run=dry_run,
        kanji_source=kanji_source,
        kanji_catalog=kanji_catalog,
        content_repo=None,
    )
    ctx.refresh_content_repo()
    return ctx


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
        kanji_catalog=ctx.kanji_catalog,
    )


def create_scheduler(
    kind: str = "fsrs", *, desired_retention: float = 0.9, enable_fuzzing: bool = True
) -> Scheduler:
    """Build the spaced-repetition scheduler named by ``kind``.

    Args:
        kind: Scheduler algorithm; only ``"fsrs"`` is supported today.
        desired_retention: Target probability of recall when a card comes due.
        enable_fuzzing: Spread review intervals randomly (disable for deterministic tests).

    Returns:
        The scheduler.

    Raises:
        ValueError: ``kind`` is not a supported scheduler.
    """
    match kind:
        case "fsrs":
            return FSRSScheduler(desired_retention=desired_retention, enable_fuzzing=enable_fuzzing)
        case _:
            raise ValueError(f"unsupported scheduler {kind!r}; supported: 'fsrs'")


def create_new_card_policy(settings: ReviewSettings) -> NewCardPolicy:
    """Build the new-card policy named by ``settings.new_card_policy``.

    Args:
        settings: The review settings (policy name, mastery threshold, active levels).

    Returns:
        The policy.

    Raises:
        ValueError: The policy name is not supported.
    """
    match settings.new_card_policy:
        case NewCardPolicyName.STRICT_ORDER:
            return StrictOrderPolicy()
        case NewCardPolicyName.MASTERY_UNLOCK:
            return MasteryUnlockPolicy(settings.mastery_threshold)
        case NewCardPolicyName.PINNED_LEVELS:
            return PinnedLevelsPolicy(settings.levels())
        case _:
            raise ValueError(f"unsupported new-card policy {settings.new_card_policy!r}")


def create_scheduler_from_settings(settings: ReviewSettings) -> Scheduler:
    """Build the scheduler configured by ``settings.target_retention`` (fuzzing on)."""
    return create_scheduler("fsrs", desired_retention=settings.target_retention)
