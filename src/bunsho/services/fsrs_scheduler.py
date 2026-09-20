"""FSRS scheduling behind the ``Scheduler`` protocol."""

from __future__ import annotations

from datetime import UTC, datetime

from fsrs import Card, Rating, State
from fsrs import Scheduler as _FsrsScheduler

from bunsho.models.review import CardSchedule, Grade, SchedState

_RATINGS: dict[Grade, Rating] = {
    Grade.AGAIN: Rating.Again,
    Grade.HARD: Rating.Hard,
    Grade.GOOD: Rating.Good,
    Grade.EASY: Rating.Easy,
}


def _utc(now: datetime) -> datetime:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware (a naive datetime has no timezone)")
    return now.astimezone(UTC)


def _to_card(current: CardSchedule, now: datetime) -> Card:
    if current.state is SchedState.NEW:
        # py-fsrs has no "new" state: a fresh card is a Learning card at step 0.
        return Card(
            state=State.Learning,
            step=0,
            stability=None,
            difficulty=None,
            due=now,
            last_review=None,
        )
    return Card(
        state=State(int(current.state)),
        step=current.step,
        stability=current.stability,
        difficulty=current.difficulty,
        due=current.due,
        last_review=current.last_review,
    )


def _from_card(card: Card) -> CardSchedule:
    return CardSchedule(
        state=SchedState(int(card.state)),
        step=card.step,
        stability=card.stability,
        difficulty=card.difficulty,
        due=card.due,
        last_review=card.last_review,
    )


def _review(
    scheduler: _FsrsScheduler, current: CardSchedule, grade: Grade, now: datetime
) -> CardSchedule:
    moment = _utc(now)
    reviewed, _log = scheduler.review_card(_to_card(current, moment), _RATINGS[grade], moment)
    return _from_card(reviewed)


class FSRSScheduler:
    """``Scheduler`` implementation backed by ``py-fsrs``."""

    def __init__(self, *, desired_retention: float = 0.9, enable_fuzzing: bool = True) -> None:
        """Create the scheduler.

        Args:
            desired_retention: Target probability of recall when a card comes due.
            enable_fuzzing: Spread review-state intervals randomly (turn off in tests).
        """
        self._scheduler = _FsrsScheduler(
            desired_retention=desired_retention, enable_fuzzing=enable_fuzzing
        )
        # Button labels must not jitter, so previews always use a fuzz-free scheduler.
        self._preview_scheduler = _FsrsScheduler(
            desired_retention=desired_retention, enable_fuzzing=False
        )

    def initial(self, now: datetime) -> CardSchedule:
        """Return the state of a card that has never been reviewed.

        Args:
            now: The current time (timezone-aware).

        Returns:
            A ``NEW`` schedule that is due immediately.

        Raises:
            ValueError: ``now`` is not timezone-aware.
        """
        return CardSchedule(state=SchedState.NEW, due=_utc(now))

    def schedule(self, current: CardSchedule, grade: Grade, now: datetime) -> CardSchedule:
        """Return the state after grading ``current`` at ``now``.

        Args:
            current: The card's state before this review.
            grade: How well it was recalled.
            now: The review time (timezone-aware; converted to UTC).

        Returns:
            The new state, with ``last_review == now``.

        Raises:
            ValueError: ``now`` is not timezone-aware.
        """
        return _review(self._scheduler, current, grade, now)

    def preview(self, current: CardSchedule, now: datetime) -> dict[Grade, CardSchedule]:
        """Return the state each grade would produce, without fuzzing.

        Args:
            current: The card's state.
            now: The review time (timezone-aware).

        Returns:
            One state per ``Grade``.

        Raises:
            ValueError: ``now`` is not timezone-aware.
        """
        return {grade: _review(self._preview_scheduler, current, grade, now) for grade in Grade}
