"""Multiple-choice distractor selection, sourced from ``content.db``."""

from __future__ import annotations

import random
from collections.abc import Sequence

from bunsho.models.content import Item, JlptLevel, Kana
from bunsho.models.review import CardKey, CatalogEntry
from bunsho.models.review_settings import ReviewSettings
from bunsho.services.answer_key import accepted_answers_for
from bunsho.services.content_catalog import ContentCatalog
from bunsho.services.content_repository import ContentRepository

_WANTED = 3
"""How many distractors to look for, alongside the correct answer."""


def _level_of(item: Item) -> JlptLevel | None:
    return None if isinstance(item, Kana) else item.level


def _ranked_pool(
    entries: Sequence[CatalogEntry],
    exclude_item_id: str,
    level: JlptLevel | None,
    active: frozenset[JlptLevel],
) -> list[CatalogEntry]:
    """``entries`` split into same-level, other-active-level and everything-else bands.

    Kana (``level is None``) always land in the same-level band together, since kana are
    never leveled; that mirrors how the rest of the app treats kana as one pool.
    """
    same_level: list[CatalogEntry] = []
    active_level: list[CatalogEntry] = []
    rest: list[CatalogEntry] = []
    for entry in entries:
        if entry.item_id == exclude_item_id:
            continue
        if entry.level == level:
            same_level.append(entry)
        elif entry.level is None or entry.level in active:
            active_level.append(entry)
        else:
            rest.append(entry)
    return same_level + active_level + rest


def choices_for(
    key: CardKey,
    item: Item,
    settings: ReviewSettings,
    repo: ContentRepository,
    rng: random.Random | None = None,
) -> list[str]:
    """Shuffled multiple-choice options for ``key``: the correct answer plus up to 3 distractors.

    Distractors are other content of the same item type, preferring the same JLPT level, then
    any level in ``settings.active_levels``, then anything else. Kana have no level and are
    treated as one pool. A thin content pool is not an error: the result may have fewer than 4
    entries (a minimum of 1, the correct answer itself).

    Blocking (SQLite via ``ContentCatalog``/``ContentRepository``); call it through
    ``asyncio.to_thread`` from async code.

    Args:
        key: The card being answered.
        item: The card's content item (already loaded).
        settings: The current review settings (for the active-levels fallback).
        repo: The content repository to sample distractors from.
        rng: Source of randomness (a fixed seed makes tests deterministic).

    Returns:
        The correct answer and its distractors, shuffled together.
    """
    rng = rng or random.Random()  # noqa: S311 # nosec B311 -- shuffling quiz choices, not crypto
    answers = accepted_answers_for(key.direction, item)
    correct = answers[0]
    catalog = ContentCatalog(repo)
    entries = catalog.entries(key.item_type)
    pool = _ranked_pool(entries, key.item_id, _level_of(item), settings.levels())

    seen = {correct}
    distractors: list[str] = []
    for entry in pool:
        if len(distractors) >= _WANTED:
            break
        candidate = repo.get_item(entry.item_type, entry.item_id)
        if candidate is None:
            continue
        candidate_answers = accepted_answers_for(key.direction, candidate)
        if not candidate_answers or candidate_answers[0] in seen:
            continue
        seen.add(candidate_answers[0])
        distractors.append(candidate_answers[0])

    choices = [correct, *distractors]
    rng.shuffle(choices)
    return choices
