from pathlib import Path

from bunsho.models.content import JlptLevel
from bunsho.models.review import ItemType
from bunsho.services.content_repository import ContentRepository
from tests.base import make_kana, make_kanji, make_vocab, write_content


def _repo(tmp_path: Path) -> ContentRepository:
    return write_content(
        tmp_path / "content.db",
        kana=[make_kana("あ", "a"), make_kana("い", "i")],
        kanji=[
            make_kanji("日", JlptLevel.N5),
            make_kanji("犬", None),
            make_kanji("曜", JlptLevel.N4),
        ],
        vocab=[
            make_vocab("日本", "にほん", JlptLevel.N5),
            make_vocab("学生", "がくせい", JlptLevel.N4),
            make_vocab("先生", "せんせい", JlptLevel.N5),
        ],
    )


def test_catalog_lists_kana_without_levels(tmp_path: Path) -> None:
    assert _repo(tmp_path).catalog(ItemType.KANA) == [
        ("kana:hira:あ", None),
        ("kana:hira:い", None),
    ]


def test_catalog_lists_vocab_in_deck_order_with_levels(tmp_path: Path) -> None:
    assert _repo(tmp_path).catalog(ItemType.VOCAB) == [
        ("vocab:日本:にほん", JlptLevel.N5),
        ("vocab:学生:がくせい", JlptLevel.N4),
        ("vocab:先生:せんせい", JlptLevel.N5),
    ]


def test_catalog_excludes_unleveled_kanji(tmp_path: Path) -> None:
    assert _repo(tmp_path).catalog(ItemType.KANJI) == [
        ("kanji:日", JlptLevel.N5),
        ("kanji:曜", JlptLevel.N4),
    ]


def test_catalog_agrees_with_an_unfiltered_list_vocab(tmp_path: Path) -> None:
    """Content ids are opaque: consumers must take them from the repository, in this order."""
    repo = _repo(tmp_path)
    assert repo.catalog(ItemType.VOCAB) == [(v.id, v.level) for v in repo.list_vocab()]


def test_get_kana_finds_a_kana_by_id(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    found = repo.get_kana("kana:hira:あ")
    assert found is not None
    assert found.char == "あ"
    assert repo.get_kana("kana:hira:missing") is None


def test_level_counts_cover_every_level_and_count_unleveled_kanji(tmp_path: Path) -> None:
    counts = _repo(tmp_path).level_counts()
    assert counts.vocab_by_level == {"N5": 2, "N4": 1, "N3": 0, "N2": 0, "N1": 0}
    assert counts.kanji_by_level == {"N5": 1, "N4": 1, "N3": 0, "N2": 0, "N1": 0}
    assert counts.unleveled_kanji == 1
