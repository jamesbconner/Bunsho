import pytest

from bunsho.text import extract_kanji, is_kanji


@pytest.mark.parametrize(
    ("char", "expected"),
    [("日", True), ("あ", False), ("A", False), ("々", False), ("", False), ("日本", False)],
)
def test_is_kanji(char: str, expected: bool) -> None:
    assert is_kanji(char) is expected


def test_extract_kanji_keeps_order_and_repeats() -> None:
    assert extract_kanji("日本の日曜日") == ["日", "本", "日", "曜", "日"]
    assert extract_kanji("ユニフォーム") == []
