"""Async persistence of card scheduling state, the review log and settings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import func, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError

from bunsho.db.engine import ProgressDatabase
from bunsho.db.models import AppSetting, CardState, ReviewLog
from bunsho.db.timestamps import format_timestamp, parse_timestamp
from bunsho.models.review import (
    CardDirection,
    CardKey,
    CardSchedule,
    Grade,
    ItemType,
    SchedState,
    StaleReviewError,
)


@dataclass(frozen=True, slots=True)
class StoredCard:
    """A ``card_state`` row as a domain object."""

    key: CardKey
    schedule: CardSchedule
    reps: int
    lapses: int


@dataclass(frozen=True, slots=True)
class ReviewRecord:
    """The parts of a ``review_log`` row that statistics need."""

    reviewed_at: datetime
    grade: Grade
    state_before: SchedState
    direction: CardDirection


def _stored(row: CardState) -> StoredCard:
    return StoredCard(
        key=CardKey(row.item_id, CardDirection(row.direction)),
        schedule=CardSchedule(
            state=SchedState(row.state),
            step=row.step,
            stability=row.stability,
            difficulty=row.difficulty,
            due=parse_timestamp(row.due),
            last_review=parse_timestamp(row.last_review) if row.last_review else None,
        ),
        reps=row.reps,
        lapses=row.lapses,
    )


class ProgressRepository:
    """Reads and writes ``progress.db``: cards, the review log and settings."""

    def __init__(self, database: ProgressDatabase) -> None:
        """Create the repository.

        Args:
            database: The async engine wrapper for ``progress.db``.
        """
        self._database = database

    async def get_card(self, key: CardKey) -> StoredCard | None:
        """Return the stored card, or ``None`` when it has never been reviewed."""
        async with self._database.sessions() as session:
            row = await session.scalar(
                select(CardState).where(
                    CardState.item_id == key.item_id, CardState.direction == key.direction.value
                )
            )
        return _stored(row) if row else None

    async def due_cards(self, now: datetime, limit: int) -> list[StoredCard]:
        """Return up to ``limit`` cards due at ``now``, earliest due first."""
        statement = (
            select(CardState)
            .where(CardState.due <= format_timestamp(now))
            .order_by(CardState.due, CardState.id)
            .limit(limit)
        )
        async with self._database.sessions() as session:
            rows = (await session.scalars(statement)).all()
        return [_stored(row) for row in rows]

    async def due_counts(self, now: datetime) -> dict[ItemType, int]:
        """Count the cards due at ``now`` per item type (types with none are omitted)."""
        statement = (
            select(CardState.direction, func.count())
            .where(CardState.due <= format_timestamp(now))
            .group_by(CardState.direction)
        )
        async with self._database.sessions() as session:
            rows = (await session.execute(statement)).all()
        return _sum_by_type(rows)

    async def next_due_after(self, now: datetime) -> datetime | None:
        """Return the soonest due time after ``now``, or ``None`` when nothing is scheduled."""
        async with self._database.sessions() as session:
            due = await session.scalar(
                select(func.min(CardState.due)).where(CardState.due > format_timestamp(now))
            )
        return parse_timestamp(due) if due else None

    async def card_states(self) -> dict[CardKey, SchedState]:
        """Return the scheduling state of every card that has been reviewed."""
        async with self._database.sessions() as session:
            rows = (
                await session.execute(
                    select(CardState.item_id, CardState.direction, CardState.state)
                )
            ).all()
        return {
            CardKey(item_id, CardDirection(direction)): SchedState(state)
            for item_id, direction, state in rows
        }

    async def new_cards_introduced(self, start: datetime, end: datetime) -> dict[ItemType, int]:
        """Count first reviews per item type with ``start <= reviewed_at < end``."""
        statement = (
            select(ReviewLog.direction, func.count())
            .where(
                ReviewLog.state_before == int(SchedState.NEW),
                ReviewLog.reviewed_at >= format_timestamp(start),
                ReviewLog.reviewed_at < format_timestamp(end),
            )
            .group_by(ReviewLog.direction)
        )
        async with self._database.sessions() as session:
            rows = (await session.execute(statement)).all()
        return _sum_by_type(rows)

    async def reviews_between(self, start: datetime, end: datetime) -> list[ReviewRecord]:
        """Return reviews with ``start <= reviewed_at < end``, oldest first."""
        statement = (
            select(
                ReviewLog.reviewed_at,
                ReviewLog.grade,
                ReviewLog.state_before,
                ReviewLog.direction,
            )
            .where(
                ReviewLog.reviewed_at >= format_timestamp(start),
                ReviewLog.reviewed_at < format_timestamp(end),
            )
            .order_by(ReviewLog.reviewed_at, ReviewLog.id)
        )
        async with self._database.sessions() as session:
            rows = (await session.execute(statement)).all()
        return [
            ReviewRecord(
                reviewed_at=parse_timestamp(reviewed_at),
                grade=Grade(grade),
                state_before=SchedState(state_before or 0),
                direction=CardDirection(direction),
            )
            for reviewed_at, grade, state_before, direction in rows
        ]

    async def record_review(
        self,
        key: CardKey,
        *,
        before: CardSchedule,
        after: CardSchedule,
        grade: Grade,
        mode: str,
        duration_ms: int | None,
    ) -> None:
        """Store the new card state and append the review log entry in one transaction.

        The write is a compare-and-set: a new card is inserted (the unique constraint
        rejects a second first review), an existing card is updated only if its
        ``last_review`` still equals ``before.last_review``. Either failure means another
        review got there first.

        Args:
            key: The card.
            before: The state the review was based on (``SchedState.NEW`` for a new card).
            after: The state to store; ``after.last_review`` is the review time.
            grade: The grade given.
            mode: The review mode, for example ``"flip"``.
            duration_ms: How long the answer took, if known.

        Raises:
            StaleReviewError: The stored card no longer matches ``before``.
            ValueError: ``after.last_review`` is missing, or ``before`` is not new but
                has no ``last_review``.
        """
        if after.last_review is None:
            raise ValueError("after.last_review is required")
        reviewed_at = format_timestamp(after.last_review)
        is_new = before.state is SchedState.NEW
        expected_last_review: str | None = None
        if not is_new:
            if before.last_review is None:
                raise ValueError("before.last_review is required for a card that is not new")
            expected_last_review = format_timestamp(before.last_review)
        elapsed = (
            None
            if before.last_review is None
            else (after.last_review - before.last_review).total_seconds() / 86400
        )
        lapsed = grade is Grade.AGAIN and before.state is SchedState.REVIEW
        values: dict[str, Any] = {
            "state": int(after.state),
            "step": after.step,
            "stability": after.stability,
            "difficulty": after.difficulty,
            "due": format_timestamp(after.due),
            "last_review": reviewed_at,
        }
        async with self._database.sessions() as session, session.begin():
            if is_new:
                session.add(
                    CardState(
                        item_id=key.item_id,
                        direction=key.direction.value,
                        reps=1,
                        lapses=0,
                        **values,
                    )
                )
                try:
                    await session.flush()
                except IntegrityError as exc:
                    raise StaleReviewError(
                        f"card {key.item_id} ({key.direction.value}) was already reviewed"
                    ) from exc
            else:
                result = await session.execute(
                    update(CardState)
                    .where(
                        CardState.item_id == key.item_id,
                        CardState.direction == key.direction.value,
                        CardState.last_review == expected_last_review,
                    )
                    .values(
                        reps=CardState.reps + 1,
                        lapses=CardState.lapses + (1 if lapsed else 0),
                        **values,
                    )
                )
                if cast(CursorResult[Any], result).rowcount != 1:
                    raise StaleReviewError(
                        f"card {key.item_id} ({key.direction.value}) changed since it was read"
                    )
            session.add(
                ReviewLog(
                    item_id=key.item_id,
                    direction=key.direction.value,
                    grade=int(grade),
                    mode=mode,
                    reviewed_at=reviewed_at,
                    state_before=int(before.state),
                    stability_before=before.stability,
                    difficulty_before=before.difficulty,
                    elapsed_days=elapsed,
                    duration_ms=duration_ms,
                )
            )

    async def get_setting(self, key: str) -> str | None:
        """Return a stored setting value, or ``None`` when it was never saved."""
        async with self._database.sessions() as session:
            value: str | None = await session.scalar(
                select(AppSetting.value).where(AppSetting.key == key)
            )
        return value

    async def set_setting(self, key: str, value: str) -> None:
        """Insert or replace a setting."""
        statement = sqlite_insert(AppSetting).values(key=key, value=value)
        statement = statement.on_conflict_do_update(
            index_elements=[AppSetting.key], set_={"value": value}
        )
        async with self._database.sessions() as session, session.begin():
            await session.execute(statement)


def _sum_by_type(rows: Any) -> dict[ItemType, int]:
    totals: dict[ItemType, int] = {}
    for direction, count in rows:
        item_type = CardDirection(direction).item_type
        totals[item_type] = totals.get(item_type, 0) + count
    return totals
