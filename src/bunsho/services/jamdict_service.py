"""Kanji lookups backed by jamdict (KANJIDIC2 in the jamdict-data-fix database)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jamdict import Jamdict

from bunsho.models.content import KanjiDetails


class JamdictUnavailableError(RuntimeError):
    """The jamdict database is missing or has no KANJIDIC2 data."""


class JamdictService:
    """Read-only access to kanji facts. Not thread-safe; use from one thread at a time."""

    def __init__(self, db_file: Path | None = None, *, jam: Any | None = None) -> None:
        """Open the database.

        Args:
            db_file: Explicit database path; ``None`` uses the ``jamdict-data-fix`` package.
            jam: A pre-built ``Jamdict``-like object (test seam).

        Raises:
            JamdictUnavailableError: The file is missing or lacks KANJIDIC2 data. jamdict
                itself fails silently in these cases, so availability is checked explicitly.
        """
        if jam is None:
            if db_file is None:
                jam = Jamdict()
            else:
                if not db_file.is_file():
                    raise JamdictUnavailableError(f"jamdict database not found: {db_file}")
                path = str(db_file)
                jam = Jamdict(db_file=path, kd2_file=path, jmnedict_file=path, auto_config=False)
        if not (jam.is_available() and jam.has_kd2()):
            raise JamdictUnavailableError(
                "jamdict database is not available or has no KANJIDIC2 data; "
                "install jamdict-data-fix or set paths.jamdict_db"
            )
        self._jam = jam

    def get_kanji(self, char: str) -> KanjiDetails | None:
        """Look up one kanji.

        Args:
            char: A single character.

        Returns:
            Details, or ``None`` when the dictionary has no such kanji.
        """
        character = self._jam.get_char(char)
        if character is None:
            return None
        readings = [r for group in character.rm_groups for r in group.readings]
        radical = next(
            (int(r.value) for r in character.radicals if r.rad_type == "classical"), None
        )
        return KanjiDetails(
            meanings=tuple(character.meanings(english_only=True)),
            on_readings=tuple(r.value for r in readings if r.r_type == "ja_on"),
            kun_readings=tuple(r.value for r in readings if r.r_type == "ja_kun"),
            stroke_count=character.stroke_count or None,
            grade=character.grade,
            frequency=character.freq,
            radical=radical,
        )
