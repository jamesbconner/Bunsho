"""Domain types for the review engine: cards, grades, scheduling state and errors."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict

from bunsho.models.content import JlptLevel


class ItemType(StrEnum):
    """The kind of content a card is about."""

    KANA = "kana"
    KANJI = "kanji"
    VOCAB = "vocab"


class CardDirection(StrEnum):
    """Which way a card asks its question. Each direction belongs to one item type."""

    GLYPH_TO_SOUND = "glyph_to_sound"
    SOUND_TO_GLYPH = "sound_to_glyph"
    KANJI_TO_MEANING = "kanji_to_meaning"
    KANJI_TO_READING = "kanji_to_reading"
    MEANING_TO_KANJI = "meaning_to_kanji"
    RECOGNITION = "recognition"
    RECALL = "recall"

    @property
    def item_type(self) -> ItemType:
        """The item type this direction belongs to."""
        return _TYPE_BY_DIRECTION[self]


DIRECTIONS_BY_TYPE: dict[ItemType, tuple[CardDirection, ...]] = {
    ItemType.KANA: (CardDirection.GLYPH_TO_SOUND, CardDirection.SOUND_TO_GLYPH),
    ItemType.KANJI: (
        CardDirection.KANJI_TO_MEANING,
        CardDirection.KANJI_TO_READING,
        CardDirection.MEANING_TO_KANJI,
    ),
    ItemType.VOCAB: (CardDirection.RECOGNITION, CardDirection.RECALL),
}

_TYPE_BY_DIRECTION: dict[CardDirection, ItemType] = {
    direction: item_type
    for item_type, directions in DIRECTIONS_BY_TYPE.items()
    for direction in directions
}


class Grade(IntEnum):
    """How well the card was recalled."""

    AGAIN = 1
    HARD = 2
    GOOD = 3
    EASY = 4


class SchedState(IntEnum):
    """Scheduling state. ``NEW`` means the card has no ``card_state`` row yet."""

    NEW = 0
    LEARNING = 1
    REVIEW = 2
    RELEARNING = 3


@dataclass(frozen=True, slots=True)
class CardKey:
    """Identity of a card: a content item plus a direction.

    ``item_id`` is an opaque content id (for example ``vocab:度:ど#2``); nothing parses it.
    """

    item_id: str
    direction: CardDirection

    @property
    def item_type(self) -> ItemType:
        """The item type, derived from the direction."""
        return self.direction.item_type


class CardSchedule(BaseModel):
    """FSRS scheduling state of one card; mirrors the ``card_state`` columns."""

    model_config = ConfigDict(frozen=True)

    state: SchedState
    step: int | None = None
    stability: float | None = None
    difficulty: float | None = None
    due: AwareDatetime
    last_review: AwareDatetime | None = None


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """One content item as the new-card policies see it.

    ``position`` is the item's index in ``content.db`` study order; ``level`` is ``None``
    for kana.
    """

    item_id: str
    item_type: ItemType
    level: JlptLevel | None
    position: int


class ReviewError(Exception):
    """Base class for review-engine errors the API maps to HTTP statuses."""


class StaleReviewError(ReviewError):
    """The card changed since the client fetched it (409)."""


class UnknownItemError(ReviewError):
    """The item id does not exist in the content database (404)."""


class ContentNotReadyError(ReviewError):
    """``content.db`` is missing, unreadable or has the wrong schema version (503)."""
