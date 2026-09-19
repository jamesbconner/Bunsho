"""SQLite storage for rebuildable study content (``content.db``)."""

from __future__ import annotations

import os
import sqlite3
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

from bunsho.models.content import JlptLevel, Kana, KanaScript, Kanji, Vocab

_SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE kana (id TEXT PRIMARY KEY, script TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE kanji (id TEXT PRIMARY KEY, level INTEGER NOT NULL, data TEXT NOT NULL);
CREATE TABLE vocab (id TEXT PRIMARY KEY, level INTEGER NOT NULL, data TEXT NOT NULL);
CREATE INDEX idx_kanji_level ON kanji (level);
CREATE INDEX idx_vocab_level ON vocab (level);
"""

CONTENT_SCHEMA_VERSION = "1"
"""Version stamped into ``meta`` by the build and checked by ``verify_schema``."""


class ContentSchemaError(RuntimeError):
    """``content.db`` was written with a different (or unknown) schema version."""


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
        ``target`` open; callers must handle or retry that.

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
                        [(k.id, int(k.level), k.model_dump_json()) for k in kanji],
                    )
                    con.executemany(
                        "INSERT INTO vocab (id, level, data) VALUES (?, ?, ?)",
                        [(v.id, int(v.level), v.model_dump_json()) for v in vocab],
                    )
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        try:
            os.replace(tmp, target)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise


@dataclass(frozen=True, slots=True)
class ContentCounts:
    """Row counts per content type."""

    kana: int
    kanji: int
    vocab: int


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

    def list_kanji(self, level: JlptLevel | None = None) -> list[Kanji]:
        """List kanji in study order, optionally for one level."""
        with self._connect() as con:
            if level is None:
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
