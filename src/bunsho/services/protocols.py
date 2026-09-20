"""Ports (interfaces) the content pipeline depends on."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Protocol

from bunsho.models.content import ImportedDeck, Kana, Kanji, KanjiDetails, Vocab
from bunsho.models.review import CardKey, CardSchedule, CatalogEntry, Grade, ItemType, SchedState


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


class Scheduler(Protocol):
    """Spaced-repetition scheduling: what happens to a card when it is graded."""

    def initial(self, now: datetime) -> CardSchedule:
        """Return the state of a card that has never been reviewed (``SchedState.NEW``)."""
        ...

    def schedule(self, current: CardSchedule, grade: Grade, now: datetime) -> CardSchedule:
        """Return the state after grading ``current`` at ``now``.

        Raises:
            ValueError: ``now`` is not timezone-aware.
        """
        ...

    def preview(self, current: CardSchedule, now: datetime) -> dict[Grade, CardSchedule]:
        """Return the state each of the four grades would produce (never fuzzed)."""
        ...


class NewCardPolicy(Protocol):
    """Chooses which never-seen cards of one item type to introduce next."""

    def select(
        self,
        item_type: ItemType,
        catalog: Sequence[CatalogEntry],
        states: Mapping[CardKey, SchedState],
        limit: int | None,
    ) -> list[CardKey]:
        """Return up to ``limit`` unintroduced cards, in the order they should appear.

        Args:
            item_type: The item type the catalogue belongs to.
            catalog: The type's entries (any order; the policy sorts them).
            states: State of every card that has been reviewed (its keys are "introduced").
            limit: Maximum number of cards, or ``None`` for no limit.
        """
        ...
