"""Accepted-answer strings for typed-answer and multiple-choice review modes.

Pure and synchronous: every function here touches only the item it is given, never the
database, so callers never need ``asyncio.to_thread`` for anything in this module.
"""

from __future__ import annotations

from bunsho.models.content import Item, Kana, Kanji, Vocab
from bunsho.models.review import CardDirection

ROMAJI_VARIANTS: dict[str, tuple[str, ...]] = {
    "shi": ("si",),
    "chi": ("ti",),
    "tsu": ("tu",),
    "fu": ("hu",),
    "ji": ("zi",),
    "zu": ("du",),
    "sha": ("sya",),
    "shu": ("syu",),
    "sho": ("syo",),
    "cha": ("tya",),
    "chu": ("tyu",),
    "cho": ("tyo",),
    "ja": ("zya",),
    "ju": ("zyu",),
    "jo": ("zyo",),
}
"""Hepburn romaji (as stored on ``Kana.romaji``) to its other common romanization spellings."""

_HOMOPHONE_KANA: dict[str, tuple[str, ...]] = {
    "じ": ("ぢ",),
    "ぢ": ("じ",),
    "ず": ("づ",),
    "づ": ("ず",),
}
"""Kana pairs that are phonetically identical in modern Japanese, so either glyph is accepted
for the other's romaji (``sound_to_glyph``)."""


def accepted_answers_for(direction: CardDirection, item: Item) -> list[str]:
    """Every string that counts as a correct typed answer for ``direction``.

    The most-preferred answer is first (also used as the correct multiple-choice option's
    display text). An empty list means this direction has nothing usable to grade against
    (for example a kanji with no meanings on file); callers should fall back to flip mode.

    Args:
        direction: Which way the card asks its question.
        item: The kana, kanji or vocabulary item the card is about.

    Returns:
        Accepted answer strings, most-preferred first.
    """
    if isinstance(item, Kana):
        return _kana_answers(direction, item)
    if isinstance(item, Kanji):
        return _kanji_answers(direction, item)
    return _vocab_answers(direction, item)


def _kana_answers(direction: CardDirection, kana: Kana) -> list[str]:
    if direction is CardDirection.GLYPH_TO_SOUND:
        return [kana.romaji, *ROMAJI_VARIANTS.get(kana.romaji, ())]
    return [kana.char, *_HOMOPHONE_KANA.get(kana.char, ())]


def _kanji_answers(direction: CardDirection, kanji: Kanji) -> list[str]:
    if direction is CardDirection.KANJI_TO_MEANING:
        return list(kanji.meanings)
    if direction is CardDirection.KANJI_TO_READING:
        return [*kanji.on_readings, *kanji.kun_readings]
    return [kanji.char]  # meaning_to_kanji


def _vocab_answers(direction: CardDirection, vocab: Vocab) -> list[str]:
    if direction is CardDirection.RECOGNITION:
        answers = [vocab.meaning]
        if vocab.additional_definitions != "":
            answers.append(vocab.additional_definitions)
        return answers
    return [vocab.expression]  # recall
