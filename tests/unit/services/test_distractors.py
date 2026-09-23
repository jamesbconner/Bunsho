"""Tests for multiple-choice distractor selection."""

import random
from pathlib import Path

from bunsho.models.content import JlptLevel
from bunsho.models.review import CardDirection, CardKey
from bunsho.models.review_settings import ReviewSettings
from bunsho.services.distractors import choices_for
from tests.base import make_kanji, write_content

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
