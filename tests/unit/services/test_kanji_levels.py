from bunsho.models.content import JlptLevel
from bunsho.services.kanji_levels import derive_kanji_levels
from tests.base import make_vocab


def test_kanji_gets_easiest_level_of_any_word() -> None:
    vocab = [
        make_vocab("日曜日", "にちようび", JlptLevel.N4),
        make_vocab("日本", "にほん", JlptLevel.N5),
    ]
    levels = derive_kanji_levels(vocab)
    assert levels == {"日": JlptLevel.N5, "曜": JlptLevel.N4, "本": JlptLevel.N5}


def test_result_is_order_independent() -> None:
    vocab = [
        make_vocab("日本", "にほん", JlptLevel.N5),
        make_vocab("日曜日", "にちようび", JlptLevel.N4),
    ]
    assert derive_kanji_levels(vocab) == derive_kanji_levels(list(reversed(vocab)))


def test_kana_only_words_contribute_nothing() -> None:
    assert derive_kanji_levels([make_vocab("ユニフォーム", "ゆにふぉーむ")]) == {}


def test_hard_word_alone_keeps_its_level() -> None:
    assert derive_kanji_levels([make_vocab("憂鬱", "ゆううつ", JlptLevel.N1)]) == {
        "憂": JlptLevel.N1,
        "鬱": JlptLevel.N1,
    }
