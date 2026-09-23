"""SQLite storage for rebuildable study content (``content.db``)."""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import time
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

from bunsho.models.content import Item, JlptLevel, Kana, KanaScript, Kanji, Vocab
from bunsho.models.review import ItemType

_SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE kana (id TEXT PRIMARY KEY, script TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE kanji (id TEXT PRIMARY KEY, level INTEGER, data TEXT NOT NULL);
CREATE TABLE vocab (id TEXT PRIMARY KEY, level INTEGER NOT NULL, data TEXT NOT NULL);
CREATE INDEX idx_kanji_level ON kanji (level);
CREATE INDEX idx_vocab_level ON vocab (level);
"""

CONTENT_SCHEMA_VERSION = "2"
"""Version stamped into ``meta`` by the build and checked by ``verify_schema``.

Version 2 made ``kanji.level`` nullable (unleveled kanji); version 1 databases must be
rebuilt.
"""


class ContentSchemaError(RuntimeError):
    """``content.db`` was written with a different (or unknown) schema version."""


_TEMP_SUFFIX = re.compile(r"\.[0-9a-f]{32}\.tmp$")


def remove_stale_temp_files(target: Path, logger: logging.Logger | None = None) -> int:
    """Delete ``<target>.<uuid hex>.tmp`` files left by a build that was killed mid-write.

    Call only while no build can be running (at startup). Files that do not match the
    exact temp-name pattern of ``ContentWriter`` are never touched.

    Args:
        target: The final ``content.db`` path; its folder is scanned.
        logger: Logger for ``key=value`` messages.

    Returns:
        How many files were removed.
    """
    log = logger or logging.getLogger(__name__)
    if not target.parent.is_dir():
        return 0
    removed = 0
    for path in target.parent.iterdir():
        if not path.name.startswith(f"{target.name}.") or not _TEMP_SUFFIX.search(path.name):
            continue
        try:
            path.unlink()
        except OSError as exc:
            log.warning("content_tmp_remove_failed path=%s error=%s", path, type(exc).__name__)
        else:
            removed += 1
    if removed:
        log.info("content_tmp_removed count=%d dir=%s", removed, target.parent)
    return removed


_REPLACE_ATTEMPTS = 5
_REPLACE_DELAY_SECONDS = 0.1


def _replace_with_retry(source: Path, target: Path) -> None:
    """Move ``source`` over ``target``, retrying briefly on ``PermissionError``.

    On Windows ``os.replace`` fails while another connection has ``target`` open; the
    repository opens short-lived connections, so a few short retries almost always succeed.
    """
    for attempt in range(1, _REPLACE_ATTEMPTS + 1):
        try:
            os.replace(source, target)
        except PermissionError:
            if attempt == _REPLACE_ATTEMPTS:
                raise
            time.sleep(_REPLACE_DELAY_SECONDS * attempt)
        else:
            return


class ContentWriter:
    """Writes a complete content database atomically."""

    def write(
        self,
        target: Path,
        *,
        kana: Sequence[Kana],
        kanji: Sequence[Kanji],
        vocab: Sequence[Vocab],
        meta: Mapping[str, str],
    ) -> None:
        """Build ``target`` from scratch.

        The data is written to a uniquely named ``<target>.<random>.tmp`` file next to
        ``target`` and moved over it only after every insert succeeded. On failure
        (including a failed move) the temp file is removed and any existing ``target`` is
        untouched. Because every call has its own temp file, concurrent builds cannot
        clobber each other's temp data; the last ``os.replace`` wins, so callers should
        still serialize builds.

        On Windows ``os.replace`` raises ``PermissionError`` while another connection has
        ``target`` open; the move is retried a few times (about a second in total) before
        the error is raised.

        Args:
            target: Destination ``content.db`` path (parent directories are created).
            kana: Kana to store.
            kanji: Kanji to store, in study order.
            vocab: Vocabulary to store, in deck order.
            meta: Build metadata (schema version, deck checksum, counts, ...).

        Raises:
            sqlite3.Error: If any insert fails (for example a duplicate ID).
            OSError: If moving the finished database over ``target`` fails (for example
                ``PermissionError`` on Windows while ``target`` is open elsewhere).
        """
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f"{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            with closing(sqlite3.connect(tmp)) as con:
                con.executescript(_SCHEMA)
                with con:
                    con.executemany(
                        "INSERT INTO meta (key, value) VALUES (?, ?)", list(meta.items())
                    )
                    con.executemany(
                        "INSERT INTO kana (id, script, data) VALUES (?, ?, ?)",
                        [(k.id, k.script.value, k.model_dump_json()) for k in kana],
                    )
                    con.executemany(
                        "INSERT INTO kanji (id, level, data) VALUES (?, ?, ?)",
                        [
                            (k.id, None if k.level is None else int(k.level), k.model_dump_json())
                            for k in kanji
                        ],
                    )
                    con.executemany(
                        "INSERT INTO vocab (id, level, data) VALUES (?, ?, ?)",
                        [(v.id, int(v.level), v.model_dump_json()) for v in vocab],
                    )
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        try:
            _replace_with_retry(tmp, target)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise


@dataclass(frozen=True, slots=True)
class ContentCounts:
    """Row counts per content type."""

    kana: int
    kanji: int
    vocab: int


@dataclass(frozen=True, slots=True)
class LevelCounts:
    """Row counts per JLPT level (``"N5"`` first, every level present)."""

    vocab_by_level: dict[str, int]
    kanji_by_level: dict[str, int]
    unleveled_kanji: int


class ContentRepository:
    """Read-only queries over ``content.db``."""

    def __init__(self, path: Path) -> None:
        """Open a repository.

        Args:
            path: Location of ``content.db``.

        Raises:
            FileNotFoundError: If the database does not exist.
        """
        if not path.is_file():
            raise FileNotFoundError(f"content database not found: {path}")
        self._uri = f"{path.resolve().as_uri()}?mode=ro"

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self._uri, uri=True)
        try:
            yield con
        finally:
            con.close()

    def counts(self) -> ContentCounts:
        """Return the number of stored items per type."""
        with self._connect() as con:
            return ContentCounts(
                kana=con.execute("SELECT COUNT(*) FROM kana").fetchone()[0],
                kanji=con.execute("SELECT COUNT(*) FROM kanji").fetchone()[0],
                vocab=con.execute("SELECT COUNT(*) FROM vocab").fetchone()[0],
            )

    def level_counts(self) -> LevelCounts:
        """Return vocab and kanji counts per JLPT level plus the unleveled kanji count."""
        with self._connect() as con:
            vocab = dict(con.execute("SELECT level, COUNT(*) FROM vocab GROUP BY level").fetchall())
            kanji = dict(
                con.execute(
                    "SELECT level, COUNT(*) FROM kanji WHERE level IS NOT NULL GROUP BY level"
                ).fetchall()
            )
            unleveled = con.execute("SELECT COUNT(*) FROM kanji WHERE level IS NULL").fetchone()[0]
        order = JlptLevel.study_order()
        return LevelCounts(
            vocab_by_level={level.label: vocab.get(int(level), 0) for level in order},
            kanji_by_level={level.label: kanji.get(int(level), 0) for level in order},
            unleveled_kanji=unleveled,
        )

    def meta(self) -> dict[str, str]:
        """Return build metadata."""
        with self._connect() as con:
            return dict(con.execute("SELECT key, value FROM meta").fetchall())

    def verify_schema(self) -> None:
        """Check that the database was built with the current schema version.

        Raises:
            ContentSchemaError: ``meta`` has no ``schema_version`` or it differs from
                ``CONTENT_SCHEMA_VERSION``; the content must be rebuilt.
        """
        found = self.meta().get("schema_version")
        if found != CONTENT_SCHEMA_VERSION:
            raise ContentSchemaError(
                f"content database schema_version={found!r} does not match the expected "
                f"{CONTENT_SCHEMA_VERSION!r}; rebuild the content database"
            )

    def list_kana(self, script: KanaScript | None = None) -> list[Kana]:
        """List kana in insertion order, optionally for one script."""
        with self._connect() as con:
            if script is None:
                rows = con.execute("SELECT data FROM kana ORDER BY rowid").fetchall()
            else:
                rows = con.execute(
                    "SELECT data FROM kana WHERE script = ? ORDER BY rowid", (script.value,)
                ).fetchall()
        return [Kana.model_validate_json(row[0]) for row in rows]

    def list_kanji(self, level: JlptLevel | None = None, *, unleveled: bool = False) -> list[Kanji]:
        """List kanji in study (insertion) order.

        With no arguments every row is returned: leveled kanji first, then unleveled ones.

        Args:
            level: Return only kanji of this JLPT level.
            unleveled: Return only kanji without a level (not used by the deck).

        Returns:
            The matching kanji.

        Raises:
            ValueError: If both ``level`` and ``unleveled`` are given.
        """
        if level is not None and unleveled:
            raise ValueError("pass either level or unleveled=True, not both")
        with self._connect() as con:
            if unleveled:
                rows = con.execute(
                    "SELECT data FROM kanji WHERE level IS NULL ORDER BY rowid"
                ).fetchall()
            elif level is None:
                rows = con.execute("SELECT data FROM kanji ORDER BY rowid").fetchall()
            else:
                rows = con.execute(
                    "SELECT data FROM kanji WHERE level = ? ORDER BY rowid", (int(level),)
                ).fetchall()
        return [Kanji.model_validate_json(row[0]) for row in rows]

    def list_vocab(self, level: JlptLevel | None = None) -> list[Vocab]:
        """List vocabulary in deck order, optionally for one level."""
        with self._connect() as con:
            if level is None:
                rows = con.execute("SELECT data FROM vocab ORDER BY rowid").fetchall()
            else:
                rows = con.execute(
                    "SELECT data FROM vocab WHERE level = ? ORDER BY rowid", (int(level),)
                ).fetchall()
        return [Vocab.model_validate_json(row[0]) for row in rows]

    def get_kanji(self, item_id: str) -> Kanji | None:
        """Return the kanji with this stable ID, if any."""
        with self._connect() as con:
            row = con.execute("SELECT data FROM kanji WHERE id = ?", (item_id,)).fetchone()
        return Kanji.model_validate_json(row[0]) if row else None

    def get_vocab(self, item_id: str) -> Vocab | None:
        """Return the vocab item with this stable ID, if any."""
        with self._connect() as con:
            row = con.execute("SELECT data FROM vocab WHERE id = ?", (item_id,)).fetchone()
        return Vocab.model_validate_json(row[0]) if row else None

    def get_kana(self, item_id: str) -> Kana | None:
        """Return the kana with this stable ID, if any."""
        with self._connect() as con:
            row = con.execute("SELECT data FROM kana WHERE id = ?", (item_id,)).fetchone()
        return Kana.model_validate_json(row[0]) if row else None

    def get_item(self, item_type: ItemType, item_id: str) -> Item | None:
        """Return the item with this stable ID, dispatching on its type."""
        match item_type:
            case ItemType.KANA:
                return self.get_kana(item_id)
            case ItemType.KANJI:
                return self.get_kanji(item_id)
            case ItemType.VOCAB:
                return self.get_vocab(item_id)

    def catalog(self, item_type: ItemType) -> list[tuple[str, JlptLevel | None]]:
        """List item ids and levels in study order without parsing the item payloads.

        Kanji without a level (not used by the deck) are excluded: they are not offered as
        lessons. Kana have no level. Ids are opaque; use them only as given.

        Args:
            item_type: Which content table to list.

        Returns:
            ``(item_id, level)`` pairs in ``content.db`` order.
        """
        with self._connect() as con:
            match item_type:
                case ItemType.KANA:
                    rows = con.execute("SELECT id, NULL FROM kana ORDER BY rowid").fetchall()
                case ItemType.KANJI:
                    rows = con.execute(
                        "SELECT id, level FROM kanji WHERE level IS NOT NULL ORDER BY rowid"
                    ).fetchall()
                case ItemType.VOCAB:
                    rows = con.execute("SELECT id, level FROM vocab ORDER BY rowid").fetchall()
        return [(row[0], None if row[1] is None else JlptLevel(row[1])) for row in rows]
