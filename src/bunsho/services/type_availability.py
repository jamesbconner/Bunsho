"""Which item types may introduce new cards right now: the enable switches and the kana gate.

Pure and synchronous, so the rule is testable without a database. The review session asks it
once per daily plan; policies never see it (a policy only sees its own type's catalog, so it
could not measure kana while choosing kanji).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from bunsho.models.review import DIRECTIONS_BY_TYPE, CardKey, CatalogEntry, ItemType, SchedState
from bunsho.models.review_settings import ReviewSettings


class BlockReason(StrEnum):
    """Why a type may not introduce new cards."""

    DISABLED = "disabled"
    WAITING_FOR_KANA = "waiting_for_kana"


@dataclass(frozen=True, slots=True)
class Availability:
    """Whether a type may introduce new cards and, when it may not, why."""

    allowed: bool
    reason: BlockReason | None = None
    kana_share: float | None = None
    """The kana share the gate compared with its threshold; ``None`` when no gate was checked."""


_OPEN = Availability(allowed=True)


def kana_share(
    kana_entries: Sequence[CatalogEntry], states: Mapping[CardKey, SchedState]
) -> float | None:
    """Return the share of kana cards in the Review state, or ``None`` when there are none.

    Kana is one stage: every entry, both directions, hiragana and katakana together.

    Args:
        kana_entries: Every kana catalog entry.
        states: Scheduling state of every card that has one.

    Returns:
        A fraction from 0 to 1, or ``None`` if the catalog has no kana cards.
    """
    directions = DIRECTIONS_BY_TYPE[ItemType.KANA]
    total = len(kana_entries) * len(directions)
    if total == 0:
        return None
    learned = sum(
        1
        for entry in kana_entries
        for direction in directions
        if states.get(CardKey(entry.item_id, direction)) is SchedState.REVIEW
    )
    return learned / total


def type_availability(
    settings: ReviewSettings,
    kana_entries: Sequence[CatalogEntry],
    states: Mapping[CardKey, SchedState],
) -> dict[ItemType, Availability]:
    """Decide, per item type, whether it may introduce new cards.

    A type is blocked when it is switched off, or when its kana gate is on and the kana share is
    below the threshold. An empty kana catalog leaves a gate open so a missing kana deck cannot
    block kanji and vocabulary forever. The share is measured at most once, and only when a gate
    is on. Due reviews are not this function's concern and are never affected.

    Args:
        settings: The review settings (switches, gate and threshold).
        kana_entries: Every kana catalog entry (only read when a gate is on).
        states: Scheduling state of every card that has one.

    Returns:
        An ``Availability`` for every item type.
    """
    result: dict[ItemType, Availability] = {}
    share: float | None = None
    measured = False
    for item_type in ItemType:
        if not settings.type_enabled.for_type(item_type):
            result[item_type] = Availability(False, BlockReason.DISABLED)
            continue
        if not settings.kana_gate.gates(item_type):
            result[item_type] = _OPEN
            continue
        if not measured:
            share, measured = kana_share(kana_entries, states), True
        if share is None or share >= settings.kana_gate.threshold:
            result[item_type] = Availability(True, kana_share=share)
        else:
            result[item_type] = Availability(False, BlockReason.WAITING_FOR_KANA, share)
    return result
