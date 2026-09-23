"""Tests for multiple-choice distractor selection."""

import random
from pathlib import Path

from bunsho.models.content import JlptLevel, KanaScript
from bunsho.models.review import CardDirection, CardKey
from bunsho.models.review_settings import ReviewSettings
from bunsho.services.distractors import choices_for
from tests.base import make_kana, make_kanji, write_content

MEANING = CardDirection.KANJI_TO_MEANING


def _repo(tmp_path: Path, kanji: list) -> object:
    return write_content(tmp_path / "content.db", kanji=kanji)


def test_choices_include_the_correct_answer_and_up_to_three_distractors(tmp_path: Path) -> None:
    kanji = [
        make_kanji("日").model_copy(update={"meanings": ("day",)}),
        make_kanji("月").model_copy(update={"meanings": ("moon",)}),
        make_kanji("火").model_copy(update={"meanings": ("fire",)}),
        make_kanji("水").model_copy(update={"meanings": ("water",)}),
    ]
    repo = _repo(tmp_path, kanji)
    key = CardKey(kanji[0].id, MEANING)
    choices = choices_for(
        key,
        kanji[0],
        ReviewSettings(),
        repo,
        rng=random.Random(0),  # noqa: S311
    )
    assert len(choices) == 4
    assert "day" in choices
    assert set(choices) == {"day", "moon", "fire", "water"}


def test_choices_degrade_gracefully_when_the_pool_is_too_small(tmp_path: Path) -> None:
    kanji = [
        make_kanji("日").model_copy(update={"meanings": ("day",)}),
        make_kanji("月").model_copy(update={"meanings": ("moon",)}),
    ]
    repo = _repo(tmp_path, kanji)
    key = CardKey(kanji[0].id, MEANING)
    choices = choices_for(
        key,
        kanji[0],
        ReviewSettings(),
        repo,
        rng=random.Random(0),  # noqa: S311
    )
    assert choices == ["day", "moon"] or choices == ["moon", "day"]


def test_choices_never_include_the_target_item_itself(tmp_path: Path) -> None:
    kanji = [make_kanji("日").model_copy(update={"meanings": ("day",)})]
    repo = _repo(tmp_path, kanji)
    key = CardKey(kanji[0].id, MEANING)
    choices = choices_for(
        key,
        kanji[0],
        ReviewSettings(),
        repo,
        rng=random.Random(0),  # noqa: S311
    )
    assert choices == ["day"]


def test_choices_never_include_a_duplicate_of_the_correct_text(tmp_path: Path) -> None:
    kanji = [
        make_kanji("日").model_copy(update={"meanings": ("day",)}),
        make_kanji("陽").model_copy(update={"meanings": ("day",), "level": JlptLevel.N5}),
        make_kanji("月").model_copy(update={"meanings": ("moon",)}),
    ]
    repo = _repo(tmp_path, kanji)
    key = CardKey(kanji[0].id, MEANING)
    choices = choices_for(
        key,
        kanji[0],
        ReviewSettings(),
        repo,
        rng=random.Random(0),  # noqa: S311
    )
    assert choices.count("day") == 1


def test_choices_prefer_the_same_level_before_widening(tmp_path: Path) -> None:
    kanji = [
        make_kanji("日", level=JlptLevel.N5).model_copy(update={"meanings": ("day",)}),
        make_kanji("愛", level=JlptLevel.N3).model_copy(update={"meanings": ("love",)}),
        *[
            make_kanji(char, level=JlptLevel.N5).model_copy(update={"meanings": (word,)})
            for char, word in [("月", "moon"), ("火", "fire"), ("水", "water")]
        ],
    ]
    repo = _repo(tmp_path, kanji)
    key = CardKey(kanji[0].id, MEANING)
    choices = choices_for(
        key,
        kanji[0],
        ReviewSettings(),
        repo,
        rng=random.Random(0),  # noqa: S311
    )
    assert "love" not in choices  # the N3 item loses to three same-level N5 candidates


_GOJUON = [
    ("あ", "a"), ("い", "i"), ("う", "u"), ("え", "e"), ("お", "o"),
    ("か", "ka"), ("き", "ki"), ("く", "ku"), ("け", "ke"), ("こ", "ko"),
    ("さ", "sa"), ("し", "shi"), ("す", "su"), ("せ", "se"), ("そ", "so"),
]  # fmt: skip


def _kana_repo(tmp_path: Path) -> object:
    hiragana = [make_kana(char, romaji) for char, romaji in _GOJUON]
    katakana = [
        make_kana(chr(ord(char) + 0x60), romaji, KanaScript.KATAKANA) for char, romaji in _GOJUON
    ]
    return write_content(tmp_path / "content.db", kana=[*hiragana, *katakana])


def test_distractors_are_not_always_the_first_items_in_study_order(tmp_path: Path) -> None:
    """Regression: every card used to get the same first-in-catalog distractors ("a", "i", "u")."""
    repo = _kana_repo(tmp_path)
    ko = make_kana("こ", "ko")
    key = CardKey(ko.id, CardDirection.GLYPH_TO_SOUND)
    seen: set[str] = set()
    for seed in range(30):
        choices = choices_for(key, ko, ReviewSettings(), repo, rng=random.Random(seed))  # noqa: S311
        seen.update(choices)
    assert len(seen - {"ko"}) > 3
    assert {"ka", "ki", "ku", "ke"} & seen


def test_distractor_selection_varies_with_the_rng_not_only_the_order(tmp_path: Path) -> None:
    repo = _kana_repo(tmp_path)
    ko = make_kana("こ", "ko")
    key = CardKey(ko.id, CardDirection.GLYPH_TO_SOUND)
    picks = {
        frozenset(choices_for(key, ko, ReviewSettings(), repo, rng=random.Random(seed)))  # noqa: S311
        for seed in range(20)
    }
    assert len(picks) > 1


def test_kana_glyph_distractors_stay_in_the_cards_script(tmp_path: Path) -> None:
    repo = _kana_repo(tmp_path)
    ko = make_kana("こ", "ko")
    key = CardKey(ko.id, CardDirection.SOUND_TO_GLYPH)
    hiragana = {char for char, _ in _GOJUON}
    for seed in range(30):
        choices = choices_for(key, ko, ReviewSettings(), repo, rng=random.Random(seed))  # noqa: S311
        assert set(choices) <= hiragana


def test_katakana_cards_do_not_get_hiragana_distractors(tmp_path: Path) -> None:
    repo = _kana_repo(tmp_path)
    ko = make_kana("コ", "ko", KanaScript.KATAKANA)
    key = CardKey(ko.id, CardDirection.SOUND_TO_GLYPH)
    hiragana = {char for char, _ in _GOJUON}
    for seed in range(30):
        choices = choices_for(key, ko, ReviewSettings(), repo, rng=random.Random(seed))  # noqa: S311
        assert not set(choices) & hiragana
