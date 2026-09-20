from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from bunsho.models.review import (
    DIRECTIONS_BY_TYPE,
    CardDirection,
    CardKey,
    CardSchedule,
    Grade,
    ItemType,
    ReviewError,
    SchedState,
    StaleReviewError,
    UnknownItemError,
)


def test_every_direction_belongs_to_exactly_one_item_type() -> None:
    listed = [d for directions in DIRECTIONS_BY_TYPE.values() for d in directions]
    assert sorted(listed) == sorted(CardDirection)
    assert len(listed) == len(set(listed))


@pytest.mark.parametrize(
    ("item_type", "count"), [(ItemType.KANA, 2), (ItemType.KANJI, 3), (ItemType.VOCAB, 2)]
)
def test_direction_counts_per_type(item_type: ItemType, count: int) -> None:
    assert len(DIRECTIONS_BY_TYPE[item_type]) == count


@pytest.mark.parametrize(
    ("direction", "item_type"),
    [
        (CardDirection.GLYPH_TO_SOUND, ItemType.KANA),
        (CardDirection.SOUND_TO_GLYPH, ItemType.KANA),
        (CardDirection.KANJI_TO_MEANING, ItemType.KANJI),
        (CardDirection.KANJI_TO_READING, ItemType.KANJI),
        (CardDirection.MEANING_TO_KANJI, ItemType.KANJI),
        (CardDirection.RECOGNITION, ItemType.VOCAB),
        (CardDirection.RECALL, ItemType.VOCAB),
    ],
)
def test_a_direction_knows_its_item_type(direction: CardDirection, item_type: ItemType) -> None:
    assert direction.item_type is item_type
    assert CardKey("opaque:id", direction).item_type is item_type


def test_grades_and_states_use_the_documented_numbers() -> None:
    assert [g.value for g in Grade] == [1, 2, 3, 4]
    assert [s.value for s in SchedState] == [0, 1, 2, 3]


def test_card_schedule_rejects_naive_datetimes() -> None:
    with pytest.raises(ValidationError):
        CardSchedule(state=SchedState.NEW, due=datetime(2026, 9, 20, 12, 0))


def test_card_schedule_is_frozen() -> None:
    schedule = CardSchedule(state=SchedState.NEW, due=datetime(2026, 9, 20, tzinfo=UTC))
    with pytest.raises(ValidationError):
        schedule.state = SchedState.REVIEW  # type: ignore[misc]


def test_review_errors_share_a_base() -> None:
    assert issubclass(StaleReviewError, ReviewError)
    assert issubclass(UnknownItemError, ReviewError)
