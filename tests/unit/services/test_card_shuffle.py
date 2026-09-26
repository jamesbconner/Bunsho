from datetime import UTC, datetime

from bunsho.models.review import CardDirection, CardKey
from bunsho.services.card_shuffle import StableShuffle

KEY = CardKey("kana:hira:あ", CardDirection.GLYPH_TO_SOUND)
OTHER = CardKey("kana:hira:い", CardDirection.GLYPH_TO_SOUND)
REVIEWED = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def test_the_rank_of_a_card_is_repeatable() -> None:
    assert StableShuffle(1).rank(KEY, None) == StableShuffle(1).rank(KEY, None)


def test_a_different_seed_gives_a_different_order() -> None:
    keys = [CardKey(f"kana:hira:{n}", CardDirection.GLYPH_TO_SOUND) for n in range(20)]
    first = sorted(keys, key=lambda key: StableShuffle(1).rank(key, None))
    second = sorted(keys, key=lambda key: StableShuffle(2).rank(key, None))
    assert first != second


def test_answering_a_card_reshuffles_it() -> None:
    shuffle = StableShuffle(1)
    assert shuffle.rank(KEY, None) != shuffle.rank(KEY, REVIEWED)


def test_the_direction_is_part_of_the_rank() -> None:
    shuffle = StableShuffle(1)
    sibling = CardKey(KEY.item_id, CardDirection.SOUND_TO_GLYPH)
    assert shuffle.rank(KEY, None) != shuffle.rank(sibling, None)
    assert shuffle.rank(KEY, None) != shuffle.rank(OTHER, None)


def test_an_unseeded_shuffle_is_random_per_instance() -> None:
    ranks = {StableShuffle().rank(KEY, None) for _ in range(5)}
    assert len(ranks) > 1
