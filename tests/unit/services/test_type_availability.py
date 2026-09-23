from collections.abc import Mapping, Sequence

import pytest

from bunsho.models.review import CardDirection, CardKey, CatalogEntry, ItemType, SchedState
from bunsho.models.review_settings import KanaGate, ReviewSettings, TypeEnabled
from bunsho.services.type_availability import (
    Availability,
    BlockReason,
    kana_share,
    type_availability,
)

KANA, KANJI, VOCAB = ItemType.KANA, ItemType.KANJI, ItemType.VOCAB
G2S, S2G = CardDirection.GLYPH_TO_SOUND, CardDirection.SOUND_TO_GLYPH


def kana_entries(count: int) -> list[CatalogEntry]:
    return [CatalogEntry(f"kana:{i}", KANA, None, i) for i in range(count)]


def learned(entries: Sequence[CatalogEntry], cards: int) -> dict[CardKey, SchedState]:
    """The first ``cards`` kana cards (entry by entry, both directions) in Review."""
    keys = [CardKey(entry.item_id, direction) for entry in entries for direction in (G2S, S2G)]
    return dict.fromkeys(keys[:cards], SchedState.REVIEW)


def gated(threshold: float = 0.8, **switches: TypeEnabled) -> ReviewSettings:
    gate = KanaGate(kanji=True, vocab=True, threshold=threshold)
    return ReviewSettings(kana_gate=gate, **switches)


def test_everything_is_allowed_with_the_default_settings() -> None:
    result = type_availability(ReviewSettings(), kana_entries(5), {})
    assert result == {
        KANA: Availability(True),
        KANJI: Availability(True),
        VOCAB: Availability(True),
    }


def test_a_disabled_type_is_blocked_even_with_no_gate() -> None:
    settings = ReviewSettings(type_enabled=TypeEnabled(kanji=False))
    result = type_availability(settings, kana_entries(5), {})
    assert result[KANJI] == Availability(False, BlockReason.DISABLED)
    assert result[KANA].allowed
    assert result[VOCAB].allowed


def test_every_type_can_be_disabled() -> None:
    off = TypeEnabled(kana=False, kanji=False, vocab=False)
    result = type_availability(ReviewSettings(type_enabled=off), [], {})
    assert {t: a.reason for t, a in result.items()} == dict.fromkeys(ItemType, BlockReason.DISABLED)


def test_a_type_that_is_both_disabled_and_gated_reports_disabled() -> None:
    settings = gated(type_enabled=TypeEnabled(vocab=False))
    result = type_availability(settings, kana_entries(5), {})
    assert result[VOCAB] == Availability(False, BlockReason.DISABLED)


def test_a_gated_type_waits_for_kana() -> None:
    result = type_availability(gated(), kana_entries(5), {})
    assert result[KANJI] == Availability(False, BlockReason.WAITING_FOR_KANA, 0.0)
    assert result[VOCAB] == Availability(False, BlockReason.WAITING_FOR_KANA, 0.0)


def test_kana_is_never_gated() -> None:
    result = type_availability(gated(), kana_entries(5), {})
    assert result[KANA] == Availability(True)


def test_only_the_gated_type_waits() -> None:
    settings = ReviewSettings(kana_gate=KanaGate(kanji=True, vocab=False))
    result = type_availability(settings, kana_entries(5), {})
    assert result[KANJI].allowed is False
    assert result[VOCAB] == Availability(True)


@pytest.mark.parametrize(
    ("learned_cards", "threshold", "expected"),
    [
        (8, 0.8, True),  # exactly at the threshold opens the gate
        (7, 0.8, False),  # just below
        (0, 0.0, True),  # a threshold of 0 is always open
        (10, 1.0, True),
        (9, 1.0, False),  # 1.0 needs every kana card in Review
        (0, 0.01, False),
    ],
)
def test_the_gate_opens_at_the_threshold(
    learned_cards: int, threshold: float, expected: bool
) -> None:
    entries = kana_entries(5)  # 10 kana cards: 5 entries x 2 directions
    result = type_availability(gated(threshold), entries, learned(entries, learned_cards))
    assert result[KANJI].allowed is expected
    assert result[VOCAB].allowed is expected


@pytest.mark.parametrize("state", [SchedState.NEW, SchedState.LEARNING, SchedState.RELEARNING])
def test_only_the_review_state_counts_as_learned(state: SchedState) -> None:
    entries = kana_entries(5)
    states = dict.fromkeys(learned(entries, 10), state)
    assert type_availability(gated(), entries, states)[KANJI].allowed is False


def test_both_directions_of_every_kana_count() -> None:
    entries = kana_entries(3)  # 6 cards
    only_glyph_to_sound = {CardKey(e.item_id, G2S): SchedState.REVIEW for e in entries}
    assert kana_share(entries, only_glyph_to_sound) == 0.5
    assert type_availability(gated(0.5), entries, only_glyph_to_sound)[KANJI].allowed is True
    assert type_availability(gated(0.6), entries, only_glyph_to_sound)[KANJI].allowed is False


def test_an_empty_kana_catalog_leaves_the_gate_open() -> None:
    result = type_availability(gated(1.0), [], {})
    assert result[KANJI] == Availability(True, kana_share=None)
    assert result[VOCAB] == Availability(True, kana_share=None)


def test_the_share_is_measured_only_when_a_gate_is_on() -> None:
    class Untouchable(Sequence[CatalogEntry]):
        def __len__(self) -> int:
            raise AssertionError("the kana catalog was measured with no gate on")

        def __getitem__(self, index):  # type: ignore[no-untyped-def]
            raise AssertionError("the kana catalog was measured with no gate on")

    states: Mapping[CardKey, SchedState] = {}
    assert type_availability(ReviewSettings(), Untouchable(), states)[KANJI].allowed is True


def test_kana_share_is_none_without_kana_and_a_fraction_otherwise() -> None:
    assert kana_share([], {}) is None
    entries = kana_entries(2)  # 4 cards
    assert kana_share(entries, learned(entries, 1)) == 0.25
