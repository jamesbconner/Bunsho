import pytest

from bunsho.models.content import RubySegment
from bunsho.services.furigana import parse_furigana, plain_reading, plain_text

SENTENCE = "我々[われわれ]は 別[わか]れて<mark>別々[べつべつ]</mark>の 道[みち]を 行[い]った。"


def test_word_with_okurigana() -> None:
    assert parse_furigana("体[からだ]つき") == (
        RubySegment(base="体", reading="からだ"),
        RubySegment(base="つき"),
    )


def test_kana_only_word_is_one_plain_segment() -> None:
    assert parse_furigana("ユニフォーム") == (RubySegment(base="ユニフォーム"),)


def test_sentence_with_highlight() -> None:
    assert parse_furigana(SENTENCE) == (
        RubySegment(base="我々", reading="われわれ"),
        RubySegment(base="は"),
        RubySegment(base="別", reading="わか"),
        RubySegment(base="れて"),
        RubySegment(base="別々", reading="べつべつ", highlighted=True),
        RubySegment(base="の"),
        RubySegment(base="道", reading="みち"),
        RubySegment(base="を"),
        RubySegment(base="行", reading="い"),
        RubySegment(base="った。"),
    )


def test_plain_projections() -> None:
    segments = parse_furigana(SENTENCE)
    assert plain_reading(segments) == "われわれはわかれてべつべつのみちをいった。"
    assert plain_text(segments) == "我々は別れて別々の道を行った。"


def test_adjacent_rubies_without_space() -> None:
    assert parse_furigana("漢[かん]字[じ]") == (
        RubySegment(base="漢", reading="かん"),
        RubySegment(base="字", reading="じ"),
    )


def test_other_tags_are_stripped_and_do_not_highlight() -> None:
    assert parse_furigana("<b>猫[ねこ]</b>") == (RubySegment(base="猫", reading="ねこ"),)


@pytest.mark.parametrize("text", ["", "<mark></mark>"])
def test_empty_input(text: str) -> None:
    assert parse_furigana(text) == ()


def test_unbalanced_bracket_is_kept_literally() -> None:
    assert parse_furigana("a[b") == (RubySegment(base="a[b"),)
