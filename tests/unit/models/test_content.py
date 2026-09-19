import pytest
from pydantic import ValidationError

from bunsho.models.content import (
    JlptLevel,
    KanaScript,
    RubySegment,
    Sentence,
    kana_id,
    kanji_id,
    vocab_id,
)
from tests.base import make_vocab


@pytest.mark.parametrize(
    ("tag", "level"),
    [
        ("jlpt_N5", JlptLevel.N5),
        ("jlpt_N1", JlptLevel.N1),
        ("jlpt_N6", None),
        ("usually_kana", None),
        ("jlpt_n3", None),
    ],
)
def test_level_from_tag(tag: str, level: JlptLevel | None) -> None:
    assert JlptLevel.from_tag(tag) is level


def test_level_order_and_label() -> None:
    assert JlptLevel.study_order() == (
        JlptLevel.N5,
        JlptLevel.N4,
        JlptLevel.N3,
        JlptLevel.N2,
        JlptLevel.N1,
    )
    assert JlptLevel.N5 > JlptLevel.N1  # higher number = easier
    assert JlptLevel.N3.label == "N3"


def test_stable_ids() -> None:
    assert kana_id(KanaScript.HIRAGANA, "あ") == "kana:hira:あ"
    assert kanji_id("漢") == "kanji:漢"
    assert vocab_id("体", "からだ") == "vocab:体:からだ"


def test_vocab_usually_kana_and_json_round_trip() -> None:
    assert make_vocab(tags=("usually_kana",)).usually_kana is True
    assert make_vocab().usually_kana is False
    sentence = Sentence(
        segments=(RubySegment(base="猫", reading="ねこ", highlighted=True),),
        english="cat",
    )
    vocab = make_vocab(sentence=sentence)
    assert type(vocab).model_validate_json(vocab.model_dump_json()) == vocab


def test_models_are_frozen() -> None:
    vocab = make_vocab()
    with pytest.raises(ValidationError):
        vocab.expression = "x"  # type: ignore[misc]
