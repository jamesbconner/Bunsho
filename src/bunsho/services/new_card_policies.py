"""The three ways of choosing which new cards to introduce.

All three order candidates the same way (JLPT level N5 first, then ``content.db`` position,
then direction order) and skip cards that already have a ``card_state`` row. They differ only
in which levels they offer. Kana has no level and is never gated. Because candidates are
ordered by level, a later level is only reached once the earlier ones are used up.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from itertools import islice

from bunsho.models.content import JlptLevel
from bunsho.models.review import (
    DIRECTIONS_BY_TYPE,
    CardKey,
    CatalogEntry,
    ItemType,
    SchedState,
)

_STUDY_ORDER = JlptLevel.study_order()


def _rank(level: JlptLevel | None) -> int:
    return -1 if level is None else _STUDY_ORDER.index(level)


def _candidates(
    item_type: ItemType,
    catalog: Sequence[CatalogEntry],
    states: Mapping[CardKey, SchedState],
    allowed: Callable[[CatalogEntry], bool],
) -> Iterator[CardKey]:
    directions = DIRECTIONS_BY_TYPE[item_type]
    for entry in sorted(catalog, key=lambda e: (_rank(e.level), e.position)):
        if not allowed(entry):
            continue
        for direction in directions:
            key = CardKey(entry.item_id, direction)
            if key not in states:
                yield key


def _take(candidates: Iterator[CardKey], limit: int | None) -> list[CardKey]:
    return list(candidates) if limit is None else list(islice(candidates, max(limit, 0)))


class StrictOrderPolicy:
    """N5 first, then N4 and so on; a level starts once the earlier ones are all introduced."""

    def select(
        self,
        item_type: ItemType,
        catalog: Sequence[CatalogEntry],
        states: Mapping[CardKey, SchedState],
        limit: int | None,
    ) -> list[CardKey]:
        """Return the next unintroduced cards in strict level order."""
        return _take(_candidates(item_type, catalog, states, lambda _entry: True), limit)


class MasteryUnlockPolicy:
    """Strict order, but a level also waits for the previous one to be mostly learned.

    Level N+1 is offered only when at least ``threshold`` of **all** cards at level N are in
    the FSRS Review state. Measuring against all cards (not just introduced ones) stops a
    handful of easy early cards from unlocking the next level.
    """

    def __init__(self, threshold: float) -> None:
        """Create the policy.

        Args:
            threshold: Share (0-1) of a level's cards that must be in Review to unlock the next.
        """
        self._threshold = threshold

    def select(
        self,
        item_type: ItemType,
        catalog: Sequence[CatalogEntry],
        states: Mapping[CardKey, SchedState],
        limit: int | None,
    ) -> list[CardKey]:
        """Return the next unintroduced cards from the levels that are unlocked."""
        unlocked = self._unlocked_levels(item_type, catalog, states)
        return _take(
            _candidates(
                item_type,
                catalog,
                states,
                lambda entry: entry.level is None or entry.level in unlocked,
            ),
            limit,
        )

    def _unlocked_levels(
        self,
        item_type: ItemType,
        catalog: Sequence[CatalogEntry],
        states: Mapping[CardKey, SchedState],
    ) -> set[JlptLevel]:
        directions = DIRECTIONS_BY_TYPE[item_type]
        total: Counter[JlptLevel] = Counter()
        mastered: Counter[JlptLevel] = Counter()
        for entry in catalog:
            if entry.level is None:
                continue
            for direction in directions:
                total[entry.level] += 1
                if states.get(CardKey(entry.item_id, direction)) is SchedState.REVIEW:
                    mastered[entry.level] += 1
        unlocked: set[JlptLevel] = set()
        for level in _STUDY_ORDER:
            unlocked.add(level)
            if total[level] and mastered[level] / total[level] < self._threshold:
                break
        return unlocked


class PinnedLevelsPolicy:
    """Only the levels chosen in the settings, in order."""

    def __init__(self, levels: Iterable[JlptLevel]) -> None:
        """Create the policy.

        Args:
            levels: The levels new cards may come from.
        """
        self._levels = frozenset(levels)

    def select(
        self,
        item_type: ItemType,
        catalog: Sequence[CatalogEntry],
        states: Mapping[CardKey, SchedState],
        limit: int | None,
    ) -> list[CardKey]:
        """Return the next unintroduced cards from the pinned levels."""
        return _take(
            _candidates(
                item_type,
                catalog,
                states,
                lambda entry: entry.level is None or entry.level in self._levels,
            ),
            limit,
        )
