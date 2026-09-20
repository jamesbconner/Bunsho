"""Review sessions: choosing the next card and recording answers."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo

from bunsho.db.progress_repository import ProgressRepository
from bunsho.models.content import Kana, Kanji, Vocab
from bunsho.models.review import (
    CardKey,
    CardSchedule,
    Grade,
    ItemType,
    SchedState,
    StaleReviewError,
    UnknownItemError,
)
from bunsho.models.review_session import (
    CardView,
    GradeIntervals,
    NextCard,
    ReviewCounts,
    TypeCounts,
)
from bunsho.models.review_settings import ReviewSettings
from bunsho.services.content_access import ContentGate
from bunsho.services.content_catalog import ContentCatalog
from bunsho.services.content_repository import ContentRepository
from bunsho.services.protocols import NewCardPolicy, Scheduler
from bunsho.services.review_settings import ReviewSettingsService
from bunsho.services.study_day import study_day_window

REVIEW_MODE = "flip"
_TYPE_ORDER = (ItemType.KANA, ItemType.KANJI, ItemType.VOCAB)
_ORPHAN_SCAN = 50
"""How many due cards to look through for one whose content item still exists."""

Item = Kana | Kanji | Vocab


@dataclass(frozen=True, slots=True)
class _Plan:
    """What is due and what could be introduced right now."""

    settings: ReviewSettings
    introduced: dict[ItemType, int]
    due_counts: dict[ItemType, int]
    new_keys: dict[ItemType, list[CardKey]]

    @property
    def counts(self) -> ReviewCounts:
        return ReviewCounts(
            due=TypeCounts.from_mapping(self.due_counts),
            new_remaining=TypeCounts.from_mapping(
                {item_type: len(keys) for item_type, keys in self.new_keys.items()}
            ),
        )

    def pick_new(self) -> CardKey | None:
        """Pick from the type with the largest remaining share of its daily allowance.

        Ties go to the earlier type in kana, kanji, vocab order. An unlimited type counts
        as a full allowance.
        """
        best: CardKey | None = None
        best_share = -1.0
        for item_type in _TYPE_ORDER:
            keys = self.new_keys[item_type]
            if not keys:
                continue
            limit = self.settings.new_limits.for_type(item_type)
            share = 1.0 if limit == 0 else (limit - self.introduced.get(item_type, 0)) / limit
            if share > best_share:
                best, best_share = keys[0], share
        return best


def _load_item(repo: ContentRepository, key: CardKey) -> Item | None:
    match key.item_type:
        case ItemType.KANA:
            return repo.get_kana(key.item_id)
        case ItemType.KANJI:
            return repo.get_kanji(key.item_id)
        case ItemType.VOCAB:
            return repo.get_vocab(key.item_id)


def _seconds_until(due: CardSchedule, now: datetime) -> int:
    return max(0, round((due.due - now).total_seconds()))


def _view(
    key: CardKey, schedule: CardSchedule, item: Item, scheduler: Scheduler, now: datetime
) -> CardView:
    previews = scheduler.preview(schedule, now)
    return CardView(
        item_id=key.item_id,
        direction=key.direction,
        item_type=key.item_type,
        is_new=schedule.state is SchedState.NEW,
        state=schedule.state,
        expected_last_review=schedule.last_review,
        intervals=GradeIntervals(
            again=_seconds_until(previews[Grade.AGAIN], now),
            hard=_seconds_until(previews[Grade.HARD], now),
            good=_seconds_until(previews[Grade.GOOD], now),
            easy=_seconds_until(previews[Grade.EASY], now),
        ),
        kana=item if isinstance(item, Kana) else None,
        kanji=item if isinstance(item, Kanji) else None,
        vocab=item if isinstance(item, Vocab) else None,
    )


class ReviewSessionOrchestrator:
    """Coordinates settings, content, scheduling and persistence for reviews.

    Stateless between calls: ``next_card`` creates nothing, so an ungraded new card is simply
    offered again, and every call reads the current settings.
    """

    def __init__(
        self,
        *,
        gate: ContentGate,
        progress: ProgressRepository,
        settings: ReviewSettingsService,
        scheduler_factory: Callable[[ReviewSettings], Scheduler],
        policy_factory: Callable[[ReviewSettings], NewCardPolicy],
        tz: tzinfo,
        logger: logging.Logger,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Create the orchestrator.

        Args:
            gate: Hands out the usable content repository.
            progress: Card state and review log storage.
            settings: The review settings service.
            scheduler_factory: Builds the scheduler from the current settings.
            policy_factory: Builds the new-card policy from the current settings.
            tz: Timezone in which the study-day rollover hour is read.
            logger: Logger for key=value messages.
            clock: Returns the current UTC time (defaults to the system clock).
        """
        self._gate = gate
        self._progress = progress
        self._settings = settings
        self._scheduler_factory = scheduler_factory
        self._policy_factory = policy_factory
        self._tz = tz
        self._logger = logger
        self._clock = clock or (lambda: datetime.now(UTC))

    async def next_card(self, now: datetime | None = None) -> NextCard:
        """Return the next card to study, plus what is left to do.

        Due cards come first (earliest due); otherwise a new card chosen by the active
        policy within today's per-type limits; otherwise no card and ``next_due_at``.

        Args:
            now: Override the current time (tests).

        Returns:
            The next card, the soonest future due time when there is no card, and the counts.

        Raises:
            ContentNotReadyError: Content is missing, unreadable or has the wrong schema.
        """
        moment = now or self._clock()
        repo = await self._gate.repository()
        settings = await self._settings.load()
        scheduler = self._scheduler_factory(settings)
        plan = await self._plan(moment, repo, settings)
        card = await self._due_view(moment, repo, scheduler)
        if card is None:
            key = plan.pick_new()
            item = None if key is None else await asyncio.to_thread(_load_item, repo, key)
            if key is not None and item is not None:
                card = _view(key, scheduler.initial(moment), item, scheduler, moment)
        next_due_at = None if card is not None else await self._progress.next_due_after(moment)
        return NextCard(card=card, next_due_at=next_due_at, counts=plan.counts)

    async def answer(
        self,
        key: CardKey,
        grade: Grade,
        *,
        expected_last_review: datetime | None,
        duration_ms: int | None = None,
        now: datetime | None = None,
    ) -> ReviewCounts:
        """Grade a card and store the result.

        Args:
            key: The card being answered.
            grade: The grade given.
            expected_last_review: The ``expected_last_review`` from ``next_card`` (``None``
                for a new card). It must match the stored card.
            duration_ms: How long the answer took, if known.
            now: Override the current time (tests).

        Returns:
            Fresh counts after the answer.

        Raises:
            ContentNotReadyError: Content is missing, unreadable or has the wrong schema.
            UnknownItemError: The item id is not in the content database.
            StaleReviewError: The card changed since it was fetched.
        """
        moment = now or self._clock()
        repo = await self._gate.repository()
        if await asyncio.to_thread(_load_item, repo, key) is None:
            raise UnknownItemError(f"unknown item {key.item_id!r} for {key.direction.value}")
        settings = await self._settings.load()
        scheduler = self._scheduler_factory(settings)
        stored = await self._progress.get_card(key)
        before = stored.schedule if stored else scheduler.initial(moment)
        if before.last_review != expected_last_review:
            raise StaleReviewError(
                f"card {key.item_id} ({key.direction.value}) changed since it was fetched"
            )
        after = scheduler.schedule(before, grade, moment)
        await self._progress.record_review(
            key,
            before=before,
            after=after,
            grade=grade,
            mode=REVIEW_MODE,
            duration_ms=duration_ms,
        )
        self._logger.info(
            "review_recorded item=%s direction=%s grade=%s state=%s due=%s",
            key.item_id,
            key.direction.value,
            grade.name,
            after.state.name,
            after.due.isoformat(),
        )
        return (await self._plan(moment, repo, settings)).counts

    async def _due_view(
        self, now: datetime, repo: ContentRepository, scheduler: Scheduler
    ) -> CardView | None:
        for stored in await self._progress.due_cards(now, _ORPHAN_SCAN):
            item = await asyncio.to_thread(_load_item, repo, stored.key)
            if item is not None:
                return _view(stored.key, stored.schedule, item, scheduler, now)
            self._logger.warning(
                "review_card_orphaned item=%s direction=%s",
                stored.key.item_id,
                stored.key.direction.value,
            )
        return None

    async def _plan(
        self, now: datetime, repo: ContentRepository, settings: ReviewSettings
    ) -> _Plan:
        window = study_day_window(now, settings.rollover_hour, self._tz)
        states = await self._progress.card_states()
        introduced = await self._progress.new_cards_introduced(*window)
        due_counts = await self._progress.due_counts(now)
        policy = self._policy_factory(settings)
        catalog = ContentCatalog(repo)
        new_keys: dict[ItemType, list[CardKey]] = {}
        for item_type in _TYPE_ORDER:
            limit = settings.new_limits.for_type(item_type)
            allowance = None if limit == 0 else max(0, limit - introduced.get(item_type, 0))
            if allowance == 0:
                new_keys[item_type] = []
                continue
            entries = await asyncio.to_thread(catalog.entries, item_type)
            new_keys[item_type] = policy.select(item_type, entries, states, allowance)
        return _Plan(settings, introduced, due_counts, new_keys)
