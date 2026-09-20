"""Statistics for the dashboard: today's work, recent history and progress per level."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta, tzinfo

from bunsho.db.progress_repository import ProgressRepository
from bunsho.models.content import JlptLevel
from bunsho.models.review import DIRECTIONS_BY_TYPE, CardKey, Grade, ItemType, SchedState
from bunsho.models.review_session import (
    DayCount,
    LevelProgress,
    StatsSummary,
    TypeCounts,
    TypeProgress,
)
from bunsho.services.content_access import ContentGate
from bunsho.services.content_catalog import ContentCatalog
from bunsho.services.review_settings import ReviewSettingsService
from bunsho.services.study_day import study_date, study_day_window

RETENTION_DAYS = 30


def _count(states: Mapping[CardKey, SchedState], wanted: SchedState) -> int:
    return sum(1 for state in states.values() if state is wanted)


class ReviewStatsService:
    """Builds ``StatsSummary`` from the review log, card states and the content catalogue."""

    def __init__(
        self,
        *,
        gate: ContentGate,
        progress: ProgressRepository,
        settings: ReviewSettingsService,
        tz: tzinfo,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Create the service.

        Args:
            gate: Hands out the usable content repository.
            progress: Card state and review log storage.
            settings: The review settings service (for the rollover hour).
            tz: Timezone in which the rollover hour is read.
            clock: Returns the current UTC time (defaults to the system clock).
        """
        self._gate = gate
        self._progress = progress
        self._settings = settings
        self._tz = tz
        self._clock = clock or (lambda: datetime.now(UTC))

    async def summary(self, now: datetime | None = None) -> StatsSummary:
        """Return the statistics as of ``now``.

        Retention is the share of reviews of cards in the Review state, over the last 30 study
        days, that were graded Hard or better; it is ``None`` when there were none.

        Raises:
            ContentNotReadyError: Content is missing, unreadable or has the wrong schema.
        """
        moment = now or self._clock()
        repo = await self._gate.repository()
        rollover = (await self._settings.load()).rollover_hour
        window_start, window_end = study_day_window(moment, rollover, self._tz)
        today = study_date(moment, rollover, self._tz)
        daily = dict.fromkeys(
            [today - timedelta(days=offset) for offset in range(RETENTION_DAYS - 1, -1, -1)], 0
        )
        records = await self._progress.reviews_between(
            window_start - timedelta(days=RETENTION_DAYS + 1), window_end
        )
        answered = passed = 0
        for record in records:
            day = study_date(record.reviewed_at, rollover, self._tz)
            if day not in daily:
                continue
            daily[day] += 1
            if record.state_before is SchedState.REVIEW:
                answered += 1
                if record.grade >= Grade.HARD:
                    passed += 1
        introduced = await self._progress.new_cards_introduced(window_start, window_end)
        states = await self._progress.card_states()
        catalog = ContentCatalog(repo)
        by_type: dict[ItemType, TypeProgress] = {}
        by_level: list[LevelProgress] = []
        for item_type in ItemType:
            entries = await asyncio.to_thread(catalog.entries, item_type)
            directions = DIRECTIONS_BY_TYPE[item_type]
            typed = {key: state for key, state in states.items() if key.item_type is item_type}
            by_type[item_type] = TypeProgress(
                total=len(entries) * len(directions),
                learning=_count(typed, SchedState.LEARNING),
                review=_count(typed, SchedState.REVIEW),
                relearning=_count(typed, SchedState.RELEARNING),
            )
            if item_type is ItemType.KANA:
                continue
            level_of = {entry.item_id: entry.level for entry in entries}
            for level in JlptLevel.study_order():
                in_level = [
                    state for key, state in typed.items() if level_of.get(key.item_id) is level
                ]
                by_level.append(
                    LevelProgress(
                        item_type=item_type,
                        level=level.label,
                        total=sum(1 for e in entries if e.level is level) * len(directions),
                        introduced=len(in_level),
                        review=sum(1 for state in in_level if state is SchedState.REVIEW),
                    )
                )
        return StatsSummary(
            reviewed_today=daily[today],
            introduced_today=TypeCounts.from_mapping(introduced),
            daily_reviews=[DayCount(day=day, reviews=count) for day, count in daily.items()],
            retention_30d=None if answered == 0 else round(passed / answered, 4),
            by_type=by_type,
            by_level=by_level,
        )
