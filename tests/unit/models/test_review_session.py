from bunsho.models.review import ItemType
from bunsho.models.review_session import TypeCounts


def test_type_counts_from_a_partial_mapping() -> None:
    counts = TypeCounts.from_mapping({ItemType.KANJI: 3, ItemType.VOCAB: 7})
    assert counts == TypeCounts(kana=0, kanji=3, vocab=7)


def test_type_counts_default_to_zero() -> None:
    assert TypeCounts() == TypeCounts.from_mapping({})
