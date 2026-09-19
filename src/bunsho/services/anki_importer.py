"""Importer for the community JLPT vocabulary Anki deck (``.apkg``)."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import zipfile
from contextlib import closing
from pathlib import Path

from bunsho.models.content import ImportedDeck, JlptLevel, Sentence, Vocab, vocab_id
from bunsho.services.furigana import parse_furigana, plain_reading

REQUIRED_FIELDS = ("Expression", "English definition", "Reading")
_COLLECTION_MEMBERS = ("collection.anki21", "collection.anki2")
_FIELD_SEPARATOR = "\x1f"


class DeckImportError(Exception):
    """Base class for deck import failures."""


class DeckIntegrityError(DeckImportError):
    """The deck file does not match the pinned checksum."""


class DeckFormatError(DeckImportError):
    """The deck structure is not what the importer expects."""


class DuplicateContentIdError(DeckImportError):
    """Two notes map to the same stable content ID."""


def sha256_of(path: Path) -> str:
    """Return the hex SHA-256 digest of a file, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class AnkiDeckImporter:
    """Reads vocabulary notes from a checksum-pinned ``.apkg`` file."""

    def __init__(self, expected_sha256: str, logger: logging.Logger | None = None) -> None:
        """Create an importer.

        Args:
            expected_sha256: Lowercase hex digest the deck must match.
            logger: Logger for structured progress messages.
        """
        self._expected_sha256 = expected_sha256
        self._logger = logger or logging.getLogger(__name__)

    def import_vocab(self, deck_path: Path) -> ImportedDeck:
        """Import every note as a ``Vocab`` in deck order.

        Args:
            deck_path: Path to the ``.apkg`` file.

        Returns:
            The vocabulary plus the verified checksum.

        Raises:
            DeckImportError: The file is missing.
            DeckIntegrityError: The checksum differs from the pinned value.
            DeckFormatError: The archive or its notes are malformed.
            DuplicateContentIdError: Two notes share ``expression`` and reading.
        """
        if not deck_path.is_file():
            raise DeckImportError(f"deck file not found: {deck_path}")
        digest = sha256_of(deck_path)
        if digest != self._expected_sha256:
            raise DeckIntegrityError(
                f"deck sha256 mismatch for {deck_path.name}: expected {self._expected_sha256}, "
                f"got {digest}. If you replaced the deck on purpose, update paths.deck_sha256."
            )
        try:
            with zipfile.ZipFile(deck_path) as archive:
                collection = _read_collection(archive)
        except zipfile.BadZipFile as exc:
            raise DeckFormatError(
                f"{deck_path.name} is not a valid .apkg (zip) archive; "
                "re-download or re-export the deck"
            ) from exc
        vocab: list[Vocab] = []
        seen: dict[str, str] = {}
        for fields, tags in _read_notes(collection):
            item = _to_vocab(fields, tags)
            if item.id in seen:
                raise DuplicateContentIdError(f"duplicate content id {item.id}")
            seen[item.id] = item.expression
            vocab.append(item)
        self._logger.info(
            "deck_import path=%s notes=%d sha256=%s", deck_path.name, len(vocab), digest
        )
        return ImportedDeck(vocab=vocab, sha256=digest)


def _read_collection(archive: zipfile.ZipFile) -> bytes:
    names = set(archive.namelist())
    for member in _COLLECTION_MEMBERS:
        if member in names:
            return archive.read(member)
    raise DeckFormatError(
        "no readable collection found (looked for "
        f"{', '.join(_COLLECTION_MEMBERS)}); re-export the deck with "
        "'Support older Anki versions' enabled"
    )


def _read_notes(collection: bytes) -> list[tuple[dict[str, str], list[str]]]:
    try:
        with closing(sqlite3.connect(":memory:")) as con:
            con.deserialize(collection)
            row = con.execute("SELECT models FROM col").fetchone()
            models = json.loads(row[0])
            if len(models) != 1:
                raise DeckFormatError(f"expected one note type, found {len(models)}")
            model = next(iter(models.values()))
            names = [f["name"] for f in sorted(model["flds"], key=lambda f: f["ord"])]
            missing = [name for name in REQUIRED_FIELDS if name not in names]
            if missing:
                raise DeckFormatError(f"deck is missing required field(s): {', '.join(missing)}")
            notes: list[tuple[dict[str, str], list[str]]] = []
            for flds, tags in con.execute("SELECT flds, tags FROM notes ORDER BY id"):
                values = flds.split(_FIELD_SEPARATOR)
                if len(values) != len(names):
                    raise DeckFormatError(
                        f"note has {len(values)} fields, expected {len(names)}: {flds[:40]!r}"
                    )
                notes.append((dict(zip(names, values, strict=True)), tags.split()))
            return notes
    except (sqlite3.DatabaseError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise DeckFormatError(
            "deck collection is malformed (unreadable database, note types or notes "
            f"table): {exc}; re-export the deck from Anki"
        ) from exc


def _to_vocab(fields: dict[str, str], tags: list[str]) -> Vocab:
    expression = fields["Expression"].strip()
    levels = [level for tag in tags if (level := JlptLevel.from_tag(tag)) is not None]
    if len(levels) != 1:
        raise DeckFormatError(
            f"note {expression!r} has {len(levels)} JLPT tag(s); expected exactly 1"
        )
    segments = parse_furigana(fields["Reading"].strip())
    reading = plain_reading(segments)
    example_jp = fields.get("Example JP", "").strip()
    sentence = (
        Sentence(segments=parse_furigana(example_jp), english=fields.get("Example EN", "").strip())
        if example_jp
        else None
    )
    return Vocab(
        id=vocab_id(expression, reading),
        expression=expression,
        reading=reading,
        reading_segments=segments,
        meaning=fields["English definition"].strip(),
        additional_definitions=fields.get("Additional definitions", "").strip(),
        part_of_speech=tuple(
            part.strip() for part in fields.get("Grammar", "").split(",") if part.strip()
        ),
        tags=tuple(tag for tag in tags if JlptLevel.from_tag(tag) is None),
        level=levels[0],
        sentence=sentence,
    )
