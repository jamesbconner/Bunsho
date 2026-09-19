"""Ports (interfaces) the content pipeline depends on."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from bunsho.models.content import ImportedDeck, Kana, Kanji, KanjiDetails, Vocab


class DeckImporter(Protocol):
    """Reads vocabulary from a deck file."""

    def import_vocab(self, deck_path: Path) -> ImportedDeck:
        """Import all vocabulary from ``deck_path``."""
        ...


class KanaProvider(Protocol):
    """Supplies the kana study set."""

    def all_kana(self) -> list[Kana]:
        """Return every kana to study."""
        ...


class KanjiInfoSource(Protocol):
    """Looks up dictionary facts about a kanji."""

    def get_kanji(self, char: str) -> KanjiDetails | None:
        """Return details for ``char`` or ``None`` when unknown."""
        ...


class KanjiCatalog(Protocol):
    """Enumerates the kanji a dictionary assigns a school or usage grade to."""

    def graded_kanji(self) -> list[str]:
        """Return kanji literals with a dictionary grade of 1-10.

        Only unified-ideograph code points are included (see ``bunsho.text.is_kanji``), in
        ascending code point order and without duplicates.
        """
        ...


class ContentWriting(Protocol):
    """Persists a complete content build."""

    def write(
        self,
        target: Path,
        *,
        kana: Sequence[Kana],
        kanji: Sequence[Kanji],
        vocab: Sequence[Vocab],
        meta: Mapping[str, str],
    ) -> None:
        """Write all content to ``target``."""
        ...
