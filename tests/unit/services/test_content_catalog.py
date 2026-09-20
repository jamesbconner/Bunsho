from pathlib import Path

from bunsho.models.content import JlptLevel
from bunsho.models.review import CatalogEntry, ItemType
from bunsho.services.content_catalog import ContentCatalog
from tests.base import make_kana, make_kanji, make_vocab, write_content


def test_entries_carry_type_level_and_position(tmp_path: Path) -> None:
    repo = write_content(
        tmp_path / "content.db",
        kana=[make_kana("あ", "a")],
        kanji=[make_kanji("日", JlptLevel.N5), make_kanji("犬", None)],
        vocab=[
            make_vocab("日本", "にほん", JlptLevel.N5),
            make_vocab("学生", "がくせい", JlptLevel.N4),
        ],
    )
    catalog = ContentCatalog(repo)
    assert catalog.entries(ItemType.VOCAB) == [
        CatalogEntry("vocab:日本:にほん", ItemType.VOCAB, JlptLevel.N5, 0),
        CatalogEntry("vocab:学生:がくせい", ItemType.VOCAB, JlptLevel.N4, 1),
    ]
    assert catalog.entries(ItemType.KANA) == [CatalogEntry("kana:hira:あ", ItemType.KANA, None, 0)]
    assert [e.item_id for e in catalog.entries(ItemType.KANJI)] == ["kanji:日"]  # 犬 is unleveled
