"""Derive JLPT levels for kanji from the vocabulary that uses them."""

from __future__ import annotations

from collections.abc import Iterable

from bunsho.models.content import JlptLevel, Vocab
from bunsho.text import extract_kanji


def derive_kanji_levels(vocab: Iterable[Vocab]) -> dict[str, JlptLevel]:
    """Assign each kanji the easiest level of any word whose expression contains it.

    The JLPT publishes no official kanji lists, so a kanji is treated as "learned" at the
    first (easiest) level where it shows up in vocabulary. N5 is the easiest level and has
    the highest numeric value.

    Args:
        vocab: Vocabulary items with levels.

    Returns:
        Mapping of kanji character to derived level.
    """
    levels: dict[str, JlptLevel] = {}
    for item in vocab:
        for char in extract_kanji(item.expression):
            current = levels.get(char)
            if current is None or item.level > current:
                levels[char] = item.level
    return levels
