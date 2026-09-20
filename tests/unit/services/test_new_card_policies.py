import pytest

from bunsho.models.content import JlptLevel
from bunsho.models.review import CardDirection, CardKey, CatalogEntry, ItemType, SchedState
from bunsho.services.new_card_policies import (
    MasteryUnlockPolicy,
    PinnedLevelsPolicy,
    StrictOrderPolicy,
)

VOCAB = ItemType.VOCAB
REC, RECALL = CardDirection.RECOGNITION, CardDirection.RECALL
N4, N5 = JlptLevel.N4, JlptLevel.N5


def entries(item_type: ItemType, spec: list[tuple[str, JlptLevel | None]]) -> list[CatalogEntry]:
    return [CatalogEntry(item_id, item_type, level, i) for i, (item_id, level) in enumerate(spec)]


# Deck order is mixed on purpose: the policies must order by level, then by position.
DECK = entries(VOCAB, [("a", N4), ("b", N5), ("c", N5), ("d", N4)])


def test_strict_order_offers_n5_before_n4_in_stable_order() -> None:
    chosen = StrictOrderPolicy().select(VOCAB, DECK, {}, 5)
    assert chosen == [
        CardKey("b", REC),
        CardKey("b", RECALL),
        CardKey("c", REC),
        CardKey("c", RECALL),
        CardKey("a", REC),
    ]


def test_strict_order_skips_cards_already_introduced() -> None:
    states = {CardKey("b", REC): SchedState.LEARNING}
    assert StrictOrderPolicy().select(VOCAB, DECK, states, 2) == [
        CardKey("b", RECALL),
        CardKey("c", REC),
    ]


def test_a_limit_of_none_means_everything_and_zero_means_nothing() -> None:
    assert len(StrictOrderPolicy().select(VOCAB, DECK, {}, None)) == 8
    assert StrictOrderPolicy().select(VOCAB, DECK, {}, 0) == []


def test_a_negative_limit_offers_nothing() -> None:
    assert StrictOrderPolicy().select(VOCAB, DECK, {}, -3) == []


LEVELS = entries(VOCAB, [("a", N5), ("b", N5), ("c", N4)])  # 4 N5 cards, 2 N4 cards
ALL_N5_LEARNED = {CardKey(i, d): SchedState.REVIEW for i in ("a", "b") for d in (REC, RECALL)}
N4_CARDS = [CardKey("c", REC), CardKey("c", RECALL)]


def test_mastery_unlocks_the_next_level_when_the_threshold_is_met() -> None:
    assert MasteryUnlockPolicy(0.8).select(VOCAB, LEVELS, ALL_N5_LEARNED, None) == N4_CARDS


def test_mastery_holds_the_next_level_back_below_the_threshold() -> None:
    states = {**ALL_N5_LEARNED, CardKey("b", RECALL): SchedState.LEARNING}  # 3 of 4 = 0.75
    assert MasteryUnlockPolicy(0.8).select(VOCAB, LEVELS, states, None) == []
    assert MasteryUnlockPolicy(0.75).select(VOCAB, LEVELS, states, None) == N4_CARDS


def test_mastery_still_offers_unintroduced_cards_of_an_unlocked_level() -> None:
    assert MasteryUnlockPolicy(0.8).select(VOCAB, LEVELS, {}, None) == [
        CardKey("a", REC),
        CardKey("a", RECALL),
        CardKey("b", REC),
        CardKey("b", RECALL),
    ]


def test_an_empty_level_does_not_block_the_next_one() -> None:
    only_n4 = entries(VOCAB, [("c", N4)])
    assert MasteryUnlockPolicy(0.9).select(VOCAB, only_n4, {}, None) == N4_CARDS


def test_pinned_levels_only_offers_the_chosen_levels() -> None:
    chosen = PinnedLevelsPolicy({N4}).select(VOCAB, DECK, {}, None)
    assert [key.item_id for key in chosen] == ["a", "a", "d", "d"]


def test_kanji_items_have_three_directions() -> None:
    kanji = entries(ItemType.KANJI, [("kanji:日", N5)])
    assert [k.direction for k in StrictOrderPolicy().select(ItemType.KANJI, kanji, {}, None)] == [
        CardDirection.KANJI_TO_MEANING,
        CardDirection.KANJI_TO_READING,
        CardDirection.MEANING_TO_KANJI,
    ]


@pytest.mark.parametrize(
    "policy",
    [StrictOrderPolicy(), MasteryUnlockPolicy(1.0), PinnedLevelsPolicy({JlptLevel.N1})],
)
def test_kana_is_never_level_gated(
    policy: StrictOrderPolicy | MasteryUnlockPolicy | PinnedLevelsPolicy,
) -> None:
    kana = entries(ItemType.KANA, [("k1", None), ("k2", None)])
    assert policy.select(ItemType.KANA, kana, {}, None) == [
        CardKey("k1", CardDirection.GLYPH_TO_SOUND),
        CardKey("k1", CardDirection.SOUND_TO_GLYPH),
        CardKey("k2", CardDirection.GLYPH_TO_SOUND),
        CardKey("k2", CardDirection.SOUND_TO_GLYPH),
    ]
