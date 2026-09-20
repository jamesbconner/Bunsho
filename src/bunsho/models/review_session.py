"""Response models for review sessions and statistics."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from bunsho.models.content import Kana, Kanji, Vocab
from bunsho.models.review import CardDirection, ItemType, SchedState


class TypeCounts(BaseModel):
    """A count per item type."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    kana: int = 0
    kanji: int = 0
    vocab: int = 0

    @classmethod
    def from_mapping(cls, counts: Mapping[ItemType, int]) -> TypeCounts:
        """Build from a mapping; missing types count as zero."""
        return cls(
            kana=counts.get(ItemType.KANA, 0),
            kanji=counts.get(ItemType.KANJI, 0),
            vocab=counts.get(ItemType.VOCAB, 0),
        )


class GradeIntervals(BaseModel):
    """Seconds until the card would be due again, for each grade (for button labels)."""

    again: int
    hard: int
    good: int
    easy: int


class CardView(BaseModel):
    """A card ready to show: identity, scheduling facts and the content item.

    Exactly one of ``kana``, ``kanji`` and ``vocab`` is set, matching ``item_type``. Send
    ``expected_last_review`` back exactly as received when answering.
    """

    item_id: str
    direction: CardDirection
    item_type: ItemType
    is_new: bool
    state: SchedState
    expected_last_review: AwareDatetime | None = Field(
        description=(
            "An opaque token (null for a new card): send it back exactly as received, byte for "
            "byte, in `POST /reviews/answer`. Never parse or reformat it; a client that "
            "re-serialises the timestamp can lose microseconds and get a permanent 409."
        )
    )
    intervals: GradeIntervals
    kana: Kana | None = None
    kanji: Kanji | None = None
    vocab: Vocab | None = None


class ReviewCounts(BaseModel):
    """What is left to do right now."""

    due: TypeCounts
    new_remaining: TypeCounts


class NextCard(BaseModel):
    """Response of ``GET /reviews/next``.

    ``card`` is ``None`` when nothing is due and no new card is available; ``next_due_at``
    then says when the next scheduled card (for example a learning step) comes due.
    """

    card: CardView | None
    next_due_at: AwareDatetime | None
    counts: ReviewCounts


class TypeProgress(BaseModel):
    """Cards of one item type by scheduling state."""

    total: int
    learning: int
    review: int
    relearning: int


class LevelProgress(BaseModel):
    """Progress through one JLPT level of one item type."""

    item_type: ItemType
    level: str
    total: int
    introduced: int
    review: int


class DayCount(BaseModel):
    """Reviews on one study day."""

    day: date
    reviews: int


class StatsSummary(BaseModel):
    """Response of ``GET /stats/summary``."""

    reviewed_today: int
    introduced_today: TypeCounts
    daily_reviews: list[DayCount]
    retention_30d: float | None
    by_type: dict[ItemType, TypeProgress]
    by_level: list[LevelProgress]
