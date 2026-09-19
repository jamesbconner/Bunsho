import sqlite3
from pathlib import Path

import pytest

from bunsho.models.content import (
    JlptLevel,
    KanaScript,
    Kanji,
    kanji_id,
)
from bunsho.services.content_repository import (
    CONTENT_SCHEMA_VERSION,
    ContentCounts,
    ContentRepository,
    ContentSchemaError,
    ContentWriter,
)
from bunsho.services.kana_source import KanaSource
from tests.base import make_kanji_details, make_vocab


def _kanji(char: str, level: JlptLevel) -> Kanji:
    details = make_kanji_details()
    return Kanji.model_validate(
        {"id": kanji_id(char), "char": char, "level": level, **details.model_dump()}
    )


def _write(target: Path) -> None:
    ContentWriter().write(
        target,
        kana=KanaSource().all_kana(),
        kanji=[_kanji("日", JlptLevel.N5), _kanji("曜", JlptLevel.N4)],
        vocab=[make_vocab("日本", "にほん"), make_vocab("日曜日", "にちようび", JlptLevel.N4)],
        meta={"schema_version": "1", "deck_sha256": "abc"},
    )


def test_round_trip(tmp_path: Path) -> None:
    target = tmp_path / "data" / "content.db"
    _write(target)
    repo = ContentRepository(target)
    assert repo.counts() == ContentCounts(kana=208, kanji=2, vocab=2)
    assert repo.meta() == {"schema_version": "1", "deck_sha256": "abc"}
    assert [k.char for k in repo.list_kanji()] == ["日", "曜"]
    assert [k.char for k in repo.list_kanji(JlptLevel.N4)] == ["曜"]
    assert [v.expression for v in repo.list_vocab(JlptLevel.N5)] == ["日本"]
    assert len(repo.list_kana(KanaScript.KATAKANA)) == 104
    assert len(repo.list_kana()) == 208
    assert repo.get_kanji("kanji:日") is not None
    assert repo.get_vocab("vocab:日本:にほん") == make_vocab("日本", "にほん")
    assert repo.get_kanji("kanji:無") is None
    assert repo.get_vocab("vocab:x:y") is None


def test_no_temp_file_left_behind(tmp_path: Path) -> None:
    target = tmp_path / "content.db"
    _write(target)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["content.db"]


def test_rebuild_replaces_previous_content(tmp_path: Path) -> None:
    target = tmp_path / "content.db"
    _write(target)
    ContentWriter().write(target, kana=[], kanji=[], vocab=[], meta={"schema_version": "2"})
    repo = ContentRepository(target)
    assert repo.counts() == ContentCounts(0, 0, 0)
    assert repo.meta() == {"schema_version": "2"}


def test_failed_build_keeps_existing_database(tmp_path: Path) -> None:
    target = tmp_path / "content.db"
    _write(target)
    duplicate = KanaSource().all_kana()[:1] * 2  # same primary key twice
    with pytest.raises(sqlite3.IntegrityError):
        ContentWriter().write(target, kana=duplicate, kanji=[], vocab=[], meta={})
    assert ContentRepository(target).counts().kana == 208
    assert [p.name for p in tmp_path.iterdir()] == ["content.db"]


def test_repository_requires_existing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="content database"):
        ContentRepository(tmp_path / "nope.db")


def test_list_vocab_unfiltered_returns_all_in_insertion_order(tmp_path: Path) -> None:
    target = tmp_path / "content.db"
    _write(target)
    vocab = ContentRepository(target).list_vocab()
    assert [v.expression for v in vocab] == ["日本", "日曜日"]


def test_verify_schema_accepts_current_version(tmp_path: Path) -> None:
    target = tmp_path / "content.db"
    ContentWriter().write(
        target,
        kana=[],
        kanji=[],
        vocab=[],
        meta={"schema_version": CONTENT_SCHEMA_VERSION},
    )
    ContentRepository(target).verify_schema()


@pytest.mark.parametrize("meta", [{}, {"schema_version": "0"}, {"deck_sha256": "abc"}])
def test_verify_schema_rejects_missing_or_different_version(
    tmp_path: Path, meta: dict[str, str]
) -> None:
    target = tmp_path / "content.db"
    ContentWriter().write(target, kana=[], kanji=[], vocab=[], meta=meta)
    with pytest.raises(ContentSchemaError, match="rebuild"):
        ContentRepository(target).verify_schema()


def test_replace_failure_cleans_up_and_keeps_existing_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "content.db"
    _write(target)

    def _deny(src: object, dst: object) -> None:
        raise PermissionError("target is open elsewhere")

    monkeypatch.setattr("bunsho.services.content_repository.os.replace", _deny)
    with pytest.raises(PermissionError, match="open elsewhere"):
        ContentWriter().write(target, kana=[], kanji=[], vocab=[], meta={})
    assert ContentRepository(target).counts() == ContentCounts(kana=208, kanji=2, vocab=2)
    assert [p.name for p in tmp_path.iterdir()] == ["content.db"]


def test_temp_file_name_is_unique_per_call(tmp_path: Path) -> None:
    target = tmp_path / "content.db"
    legacy = tmp_path / "content.db.tmp"
    legacy.write_bytes(b"legacy leftover")
    _write(target)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["content.db", "content.db.tmp"]
    assert legacy.read_bytes() == b"legacy leftover"
