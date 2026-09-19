"""Kanji lookups backed by jamdict (KANJIDIC2 in the jamdict-data-fix database)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from jamdict import Jamdict

from bunsho.models.content import KanjiDetails

_PROBE_KANJI = "日"


class JamdictUnavailableError(RuntimeError):
    """The jamdict database is missing or has no KANJIDIC2 data."""


class JamdictService:
    """Read-only access to kanji facts. Not thread-safe; use from one thread at a time."""

    def __init__(self, db_file: Path | None = None, *, jam: Any | None = None) -> None:
        """Open the database.

        Args:
            db_file: Explicit database path; ``None`` uses the ``jamdict-data-fix`` package.
            jam: A pre-built ``Jamdict``-like object (test seam). It is only checked with
                ``is_available()`` and ``has_kd2()``; no probe lookup is made.

        Raises:
            JamdictUnavailableError: The file is missing, jamdict reports the database as
                unavailable or without KANJIDIC2, or (for a database opened here) a probe
                lookup of one kanji fails or finds nothing. jamdict itself fails silently
                in these cases, so availability is checked explicitly.
        """
        probe = jam is None
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
        if probe:
            self._probe(jam)
        self._jam = jam

    @staticmethod
    def _probe(jam: Any) -> None:
        """Confirm a real database answers a kanji lookup.

        The availability flags only reflect that a path is configured, so an empty or
        corrupt file passes them; one lookup of a common kanji catches those cases.

        Raises:
            JamdictUnavailableError: The lookup raised a sqlite error or found nothing.
        """
        message = (
            "jamdict database is unreadable or has no KANJIDIC2 data "
            f"(probe lookup of {_PROBE_KANJI} failed); "
            "reinstall jamdict-data-fix or set paths.jamdict_db"
        )
        try:
            found = jam.get_char(_PROBE_KANJI)
        except sqlite3.Error as exc:
            raise JamdictUnavailableError(message) from exc
        if found is None:
            raise JamdictUnavailableError(message)

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
