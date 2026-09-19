"""Build tiny synthetic ``.apkg`` files for importer tests."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

DECK_FIELDS = (
    "Expression",
    "English definition",
    "Reading",
    "Grammar",
    "Additional definitions",
    "Example JP",
    "Example EN",
)


@dataclass(frozen=True)
class SyntheticNote:
    """One note: field values in ``DECK_FIELDS`` order plus tags."""

    fields: tuple[str, ...]
    tags: tuple[str, ...]


def note(
    expression: str,
    reading: str,
    level_tag: str = "jlpt_N5",
    *,
    meaning: str = "meaning",
    grammar: str = "noun",
    example_jp: str = "",
    example_en: str = "",
    extra_tags: tuple[str, ...] = (),
) -> SyntheticNote:
    """Convenience constructor for a note with the deck's field layout."""
    return SyntheticNote(
        fields=(expression, meaning, reading, grammar, "", example_jp, example_en),
        tags=(level_tag, *extra_tags),
    )


def build_apkg(
    path: Path,
    notes: Sequence[SyntheticNote],
    *,
    member: str = "collection.anki21",
    fields: Sequence[str] = DECK_FIELDS,
    model_count: int = 1,
) -> str:
    """Write a minimal ``.apkg`` and return its sha256 hex digest."""
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE col (models TEXT, decks TEXT)")
    models = {
        str(i): {"name": f"model{i}", "flds": [{"name": n, "ord": o} for o, n in enumerate(fields)]}
        for i in range(model_count)
    }
    con.execute("INSERT INTO col VALUES (?, ?)", (json.dumps(models), "{}"))
    con.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, flds TEXT, tags TEXT)")
    for index, item in enumerate(notes, start=1):
        con.execute(
            "INSERT INTO notes VALUES (?, ?, ?)",
            (index, "\x1f".join(item.fields), f" {' '.join(item.tags)} "),
        )
    data = con.serialize()
    con.close()
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(member, data)
    return hashlib.sha256(path.read_bytes()).hexdigest()
