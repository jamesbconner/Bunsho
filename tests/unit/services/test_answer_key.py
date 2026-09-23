"""Tests for the accepted-answers builder that backs typed-answer and multiple-choice modes."""

from bunsho.models.review import CardDirection
from bunsho.services.answer_key import accepted_answers_for
from tests.base import make_kana, make_kanji, make_vocab


def test_glyph_to_sound_accepts_the_romaji_and_its_known_variants() -> None:
    shi = make_kana("し", "shi")
    assert accepted_answers_for(CardDirection.GLYPH_TO_SOUND, shi) == ["shi", "si"]


def test_glyph_to_sound_with_no_known_variant_accepts_only_the_romaji() -> None:
    a = make_kana("あ", "a")
    assert accepted_answers_for(CardDirection.GLYPH_TO_SOUND, a) == ["a"]


def test_sound_to_glyph_accepts_ji_and_zi_dakuten_kana_interchangeably() -> None:
    ji = make_kana("じ", "ji")
    ji_answers = accepted_answers_for(CardDirection.SOUND_TO_GLYPH, ji)
    assert ji_answers[0] == "じ"
    assert "ぢ" in ji_answers

    chi_dakuten = make_kana("ぢ", "ji")
    assert accepted_answers_for(CardDirection.SOUND_TO_GLYPH, chi_dakuten)[0] == "ぢ"
    assert "じ" in accepted_answers_for(CardDirection.SOUND_TO_GLYPH, chi_dakuten)


def test_sound_to_glyph_with_no_homophone_accepts_only_its_own_glyph() -> None:
    a = make_kana("あ", "a")
    assert accepted_answers_for(CardDirection.SOUND_TO_GLYPH, a) == ["あ"]


def test_kanji_to_meaning_accepts_every_listed_meaning() -> None:
    day = make_kanji("日")  # meanings=("day",) by default
    assert accepted_answers_for(CardDirection.KANJI_TO_MEANING, day) == ["day"]


def test_kanji_to_meaning_is_empty_when_the_kanji_has_no_meanings_on_file() -> None:
    bare = make_kanji("日").model_copy(update={"meanings": ()})
    assert accepted_answers_for(CardDirection.KANJI_TO_MEANING, bare) == []


def test_kanji_to_reading_accepts_on_then_kun_readings() -> None:
    day = make_kanji("日")  # on_readings=("ニチ",), kun_readings=("ひ",) by default
    assert accepted_answers_for(CardDirection.KANJI_TO_READING, day) == ["ニチ", "ひ"]


def test_meaning_to_kanji_accepts_the_character() -> None:
    day = make_kanji("日")
    assert accepted_answers_for(CardDirection.MEANING_TO_KANJI, day) == ["日"]


def test_vocab_recognition_accepts_the_meaning_and_the_additional_definitions() -> None:
    with_extra = make_vocab().model_copy(update={"additional_definitions": "to live on"})
    assert accepted_answers_for(CardDirection.RECOGNITION, with_extra) == [
        "test meaning",
        "to live on",
    ]


def test_vocab_recognition_without_additional_definitions_accepts_only_the_meaning() -> None:
    plain = make_vocab()
    assert accepted_answers_for(CardDirection.RECOGNITION, plain) == ["test meaning"]


def test_vocab_recall_accepts_the_expression() -> None:
    word = make_vocab("食べる", "たべる")
    assert accepted_answers_for(CardDirection.RECALL, word) == ["食べる"]
