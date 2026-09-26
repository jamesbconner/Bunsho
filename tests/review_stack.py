"""Builders for review-engine tests: a fake clock and a fully wired session stack."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path

from bunsho.context import Context
from bunsho.db.engine import ProgressDatabase
from bunsho.db.progress_repository import ProgressRepository
from bunsho.factories import create_new_card_policy, create_scheduler
from bunsho.models.content import Kana, Kanji, Vocab
from bunsho.models.review_settings import ReviewSettings
from bunsho.orchestration.review_session import ReviewSessionOrchestrator
from bunsho.services.content_access import ContentGate
from bunsho.services.content_repository import CONTENT_SCHEMA_VERSION, ContentRepository
from bunsho.services.protocols import Scheduler
from bunsho.services.review_settings import ReviewSettingsService
from bunsho.services.review_stats import ReviewStatsService
from tests.base import make_service_config, write_content

START = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
LOGGER_NAME = "bunsho.tests.review"


class FakeClock:
    """A controllable clock: call it for the time, ``advance`` to move it."""

    def __init__(self, now: datetime = START) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        """Move the clock forward, for example ``advance(minutes=11)``."""
        self.now += timedelta(**delta)


@dataclass(slots=True)
class ReviewStack:
    """Everything a review test needs, wired together."""

    ctx: Context
    clock: FakeClock
    progress: ProgressRepository
    settings: ReviewSettingsService
    orchestrator: ReviewSessionOrchestrator
    stats: ReviewStatsService


def _scheduler(settings: ReviewSettings) -> Scheduler:
    return create_scheduler(
        "fsrs", desired_retention=settings.target_retention, enable_fuzzing=False
    )


def stack_for_repository(
    tmp_path: Path,
    database: ProgressDatabase,
    repository: ContentRepository | None,
    *,
    clock: FakeClock | None = None,
    tz: tzinfo = UTC,
    shuffle_seed: int | None = None,
) -> ReviewStack:
    """Wire the services around an existing content repository (``None`` = not built)."""
    fake = clock or FakeClock()
    logger = logging.getLogger(LOGGER_NAME)
    ctx = Context(config=make_service_config(tmp_path).app, logger=logger, content_repo=repository)
    progress = ProgressRepository(database)
    settings = ReviewSettingsService(progress, logger)
    gate = ContentGate(ctx)
    orchestrator = ReviewSessionOrchestrator(
        gate=gate,
        progress=progress,
        settings=settings,
        scheduler_factory=_scheduler,
        policy_factory=create_new_card_policy,
        tz=tz,
        logger=logger,
        clock=fake,
        shuffle_seed=shuffle_seed,
    )
    stats = ReviewStatsService(gate=gate, progress=progress, settings=settings, tz=tz, clock=fake)
    return ReviewStack(ctx, fake, progress, settings, orchestrator, stats)


def build_review_stack(
    tmp_path: Path,
    database: ProgressDatabase,
    *,
    kana: Iterable[Kana] = (),
    kanji: Iterable[Kanji] = (),
    vocab: Iterable[Vocab] = (),
    schema_version: str = CONTENT_SCHEMA_VERSION,
    built: bool = True,
    clock: FakeClock | None = None,
    tz: tzinfo = UTC,
    shuffle_seed: int | None = None,
) -> ReviewStack:
    """Write a small ``content.db`` (unless ``built=False``) and wire a stack around it."""
    repository = (
        write_content(
            tmp_path / "data" / "content.db",
            kana=kana,
            kanji=kanji,
            vocab=vocab,
            schema_version=schema_version,
        )
        if built
        else None
    )
    return stack_for_repository(
        tmp_path, database, repository, clock=clock, tz=tz, shuffle_seed=shuffle_seed
    )
