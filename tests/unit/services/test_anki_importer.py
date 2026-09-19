import json
import logging
import sqlite3
import zipfile
from pathlib import Path

import pytest

from bunsho.models.content import JlptLevel
from bunsho.services.anki_importer import (
    AnkiDeckImporter,
    DeckFormatError,
    DeckImportError,
    DeckIntegrityError,
    DuplicateContentIdError,
    sha256_of,
)
from tests.apkg_builder import DECK_FIELDS, build_apkg, note

SENTENCE_JP = "我々[われわれ]は 別[わか]れて<mark>別々[べつべつ]</mark>の 道[みち]を 行[い]った。"


def _importer(sha: str) -> AnkiDeckImporter:
    return AnkiDeckImporter(sha, logging.getLogger("bunsho.tests"))


def test_imports_fields_levels_tags_and_sentence(tmp_path: Path) -> None:
    deck = tmp_path / "deck.apkg"
    sha = build_apkg(
        deck,
        [
            note(
                "別々",
                "別々[べつべつ]",
                "jlpt_N2",
                meaning="separate",
                grammar="no adjective, noun",
                example_jp=SENTENCE_JP,
                example_en="We went our own ways.",
                extra_tags=("usually_kana", "polite/丁寧語"),
            ),
            note("体", "体[からだ]つき", "jlpt_N4"),
        ],
    )
    imported = _importer(sha).import_vocab(deck)
    assert imported.sha256 == sha
    first, second = imported.vocab
    assert first.id == "vocab:別々:べつべつ"
    assert first.level is JlptLevel.N2
    assert first.meaning == "separate"
    assert first.part_of_speech == ("no adjective", "noun")
    assert first.tags == ("usually_kana", "polite/丁寧語")
    assert first.usually_kana
    assert first.sentence is not None
    assert first.sentence.english == "We went our own ways."
    assert any(s.highlighted and s.base == "別々" for s in first.sentence.segments)
    assert second.reading == "からだつき"
    assert second.sentence is None


def test_wrong_checksum_is_rejected(tmp_path: Path) -> None:
    deck = tmp_path / "deck.apkg"
    build_apkg(deck, [note("日", "にち")])
    with pytest.raises(DeckIntegrityError, match="sha256"):
        _importer("0" * 64).import_vocab(deck)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(DeckImportError, match="not found"):
        _importer("0" * 64).import_vocab(tmp_path / "nope.apkg")


def test_falls_back_to_legacy_collection_member(tmp_path: Path) -> None:
    deck = tmp_path / "deck.apkg"
    sha = build_apkg(deck, [note("日", "にち")], member="collection.anki2")
    assert len(_importer(sha).import_vocab(deck).vocab) == 1


def test_unsupported_collection_format(tmp_path: Path) -> None:
    deck = tmp_path / "deck.apkg"
    with zipfile.ZipFile(deck, "w") as archive:
        archive.writestr("collection.anki21b", b"zstd")
    with pytest.raises(DeckFormatError, match="older Anki"):
        _importer(sha256_of(deck)).import_vocab(deck)


def test_missing_required_field(tmp_path: Path) -> None:
    deck = tmp_path / "deck.apkg"
    sha = build_apkg(deck, [], fields=[f for f in DECK_FIELDS if f != "Reading"])
    with pytest.raises(DeckFormatError, match="Reading"):
        _importer(sha).import_vocab(deck)


def test_multiple_models_rejected(tmp_path: Path) -> None:
    deck = tmp_path / "deck.apkg"
    sha = build_apkg(deck, [note("日", "にち")], model_count=2)
    with pytest.raises(DeckFormatError, match="one note type"):
        _importer(sha).import_vocab(deck)


@pytest.mark.parametrize("tag_set", [(), ("jlpt_N5", "jlpt_N4")])
def test_exactly_one_level_tag_required(tmp_path: Path, tag_set: tuple[str, ...]) -> None:
    deck = tmp_path / "deck.apkg"
    item = note("日", "にち")
    item = type(item)(fields=item.fields, tags=tag_set)
    sha = build_apkg(deck, [item])
    with pytest.raises(DeckFormatError, match="JLPT tag"):
        _importer(sha).import_vocab(deck)


def test_duplicate_expression_and_reading_is_rejected(tmp_path: Path) -> None:
    deck = tmp_path / "deck.apkg"
    sha = build_apkg(deck, [note("日", "にち"), note("日", "にち", "jlpt_N4")])
    with pytest.raises(DuplicateContentIdError, match="vocab:日:にち"):
        _importer(sha).import_vocab(deck)


def test_same_expression_different_reading_is_allowed(tmp_path: Path) -> None:
    deck = tmp_path / "deck.apkg"
    sha = build_apkg(deck, [note("日", "ひ"), note("日", "にち")])
    assert len(_importer(sha).import_vocab(deck).vocab) == 2


def _write_collection_deck(path: Path, data: bytes) -> str:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("collection.anki21", data)
    return sha256_of(path)


def _sqlite_bytes(*statements: tuple[str, tuple[str, ...]]) -> bytes:
    con = sqlite3.connect(":memory:")
    for sql, params in statements:
        con.execute(sql, params)
    data = con.serialize()
    con.close()
    return data


def test_invalid_zip_raises_deck_format_error(tmp_path: Path) -> None:
    deck = tmp_path / "deck.apkg"
    deck.write_bytes(b"not a zip")
    with pytest.raises(DeckFormatError, match="zip") as excinfo:
        _importer(sha256_of(deck)).import_vocab(deck)
    assert excinfo.value.__cause__ is not None


def test_invalid_sqlite_raises_deck_format_error(tmp_path: Path) -> None:
    deck = tmp_path / "deck.apkg"
    sha = _write_collection_deck(deck, b"not sqlite")
    with pytest.raises(DeckFormatError):
        _importer(sha).import_vocab(deck)


def test_non_json_models_raises_deck_format_error(tmp_path: Path) -> None:
    deck = tmp_path / "deck.apkg"
    data = _sqlite_bytes(
        ("CREATE TABLE col (models TEXT, decks TEXT)", ()),
        ("INSERT INTO col VALUES (?, ?)", ("not json", "{}")),
    )
    with pytest.raises(DeckFormatError):
        _importer(_write_collection_deck(deck, data)).import_vocab(deck)


def test_model_without_fields_raises_deck_format_error(tmp_path: Path) -> None:
    deck = tmp_path / "deck.apkg"
    data = _sqlite_bytes(
        ("CREATE TABLE col (models TEXT, decks TEXT)", ()),
        ("INSERT INTO col VALUES (?, ?)", (json.dumps({"0": {"name": "m"}}), "{}")),
    )
    with pytest.raises(DeckFormatError):
        _importer(_write_collection_deck(deck, data)).import_vocab(deck)


def test_empty_col_table_raises_deck_format_error(tmp_path: Path) -> None:
    deck = tmp_path / "deck.apkg"
    data = _sqlite_bytes(("CREATE TABLE col (models TEXT, decks TEXT)", ()))
    with pytest.raises(DeckFormatError):
        _importer(_write_collection_deck(deck, data)).import_vocab(deck)


def test_models_as_list_raises_deck_format_error(tmp_path: Path) -> None:
    deck = tmp_path / "deck.apkg"
    data = _sqlite_bytes(
        ("CREATE TABLE col (models TEXT, decks TEXT)", ()),
        ("INSERT INTO col VALUES (?, ?)", (json.dumps([{"flds": []}]), "{}")),
    )
    with pytest.raises(DeckFormatError):
        _importer(_write_collection_deck(deck, data)).import_vocab(deck)


def test_null_note_fields_raise_deck_format_error(tmp_path: Path) -> None:
    deck = tmp_path / "deck.apkg"
    fields = [{"name": name, "ord": ordinal} for ordinal, name in enumerate(DECK_FIELDS)]
    models = json.dumps({"0": {"name": "m", "flds": fields}})
    data = _sqlite_bytes(
        ("CREATE TABLE col (models TEXT, decks TEXT)", ()),
        ("INSERT INTO col VALUES (?, ?)", (models, "{}")),
        ("CREATE TABLE notes (id INTEGER PRIMARY KEY, flds TEXT, tags TEXT)", ()),
        ("INSERT INTO notes VALUES (1, NULL, ' jlpt_N5 ')", ()),
    )
    with pytest.raises(DeckFormatError):
        _importer(_write_collection_deck(deck, data)).import_vocab(deck)
