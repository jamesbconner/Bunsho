"""Kanji lookups backed by jamdict (KANJIDIC2 in the jamdict-data-fix database)."""

from __future__ import annotations

import os
import sqlite3
import threading
from collections.abc import Callable
from contextlib import closing
from functools import partial
from pathlib import Path
from typing import Any

from jamdict import Jamdict

from bunsho.models.content import KanjiDetails
from bunsho.text import is_kanji

_PROBE_KANJI = "日"

GRADED_KANJI_MIN = 1
GRADED_KANJI_MAX = 10
"""KANJIDIC2 grades that count as "graded" (inclusive bounds).

1-6 are the kyōiku kanji taught in elementary school, 8 the remaining jōyō kanji taught
in secondary school, 9 and 10 the jinmeiyō kanji allowed in names (10 being variants of
jōyō kanji). Grade 7 is unused.
"""


def _identity(value: Any) -> Any:
    return value


class JamdictUnavailableError(RuntimeError):
    """The jamdict database is missing or has no KANJIDIC2 data."""


class JamdictService:
    """Read-only access to kanji facts.

    Implements both ``KanjiInfoSource`` (``get_kanji``) and ``KanjiCatalog``
    (``graded_kanji``). Safe to call from any thread. jamdict keeps a cached sqlite
    connection that may only be used on the thread that opened it, so when the service
    builds the ``Jamdict`` itself, each thread lazily opens its own read-only connection
    on first use (the constructing thread reuses the instance used for the
    construction-time checks). A ``jam`` object injected through the test seam is used
    as-is by every thread; its thread-safety is the caller's responsibility.
    """

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
        self._local = threading.local()
        factory: Callable[[], Any]
        if jam is None:
            if db_file is None:
                factory = Jamdict
            else:
                if not db_file.is_file():
                    raise JamdictUnavailableError(f"jamdict database not found: {db_file}")
                path = str(db_file)
                factory = partial(
                    Jamdict, db_file=path, kd2_file=path, jmnedict_file=path, auto_config=False
                )
            jam = factory()
        else:
            factory = partial(_identity, jam)  # injected object is shared by all threads
        if not (jam.is_available() and jam.has_kd2()):
            raise JamdictUnavailableError(
                "jamdict database is not available or has no KANJIDIC2 data; "
                "install jamdict-data-fix or set paths.jamdict_db"
            )
        if probe:
            self._probe(jam)
        self._factory = factory
        self._local.jam = jam
        db_path = getattr(jam, "db_file", None)
        self._db_path: Path | None = (
            Path(db_path) if isinstance(db_path, str | os.PathLike) else None
        )

    def _jam_for_current_thread(self) -> Any:
        """Return this thread's ``Jamdict``, creating it on first use.

        Returns:
            The injected ``jam`` when there is one, otherwise the calling thread's own
            instance.
        """
        jam = getattr(self._local, "jam", None)
        if jam is None:
            jam = self._factory()
            self._local.jam = jam
        return jam

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
        character = self._jam_for_current_thread().get_char(char)
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

    def graded_kanji(self) -> list[str]:
        """List every kanji the dictionary assigns a grade of 1-10.

        Uses a short-lived read-only sqlite connection to the database file, opened on the
        calling thread, so it is safe from any thread and independent of the per-thread
        ``Jamdict`` instances. Compatibility ideographs (U+F900-U+FAFF) are excluded; their
        standard forms are already in the dictionary.

        Returns:
            Kanji literals in ascending code point order, without duplicates.

        Raises:
            JamdictUnavailableError: The service has no database path (injected ``jam``
                without a ``db_file``) or the database could not be queried.
        """
        if self._db_path is None:
            raise JamdictUnavailableError(
                "the graded kanji catalog needs a database path: the jamdict object has no "
                "usable db_file; pass db_file= or use the jamdict-data-fix package"
            )
        uri = f"{self._db_path.resolve().as_uri()}?mode=ro"
        try:
            with closing(sqlite3.connect(uri, uri=True)) as con:
                rows = con.execute(
                    "SELECT literal FROM Character "
                    "WHERE CAST(grade AS INTEGER) BETWEEN ? AND ? ORDER BY literal",
                    (GRADED_KANJI_MIN, GRADED_KANJI_MAX),
                ).fetchall()
        except sqlite3.Error as exc:
            raise JamdictUnavailableError(
                f"could not read graded kanji from {self._db_path}; "
                "reinstall jamdict-data-fix or set paths.jamdict_db"
            ) from exc
        return sorted({row[0] for row in rows if is_kanji(row[0])})
