"""Shared test builders and fixtures for Bunshō."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from bunsho.config.settings import DEFAULT_DECK_FILENAME, DEFAULT_DECK_SHA256, AppConfig
from bunsho.models.content import (
    JlptLevel,
    KanjiDetails,
    RubySegment,
    Sentence,
    Vocab,
    vocab_id,
)


def make_vocab(
    expression: str = "日本",
    reading: str = "にほん",
    level: JlptLevel = JlptLevel.N5,
    *,
    tags: tuple[str, ...] = (),
    sentence: Sentence | None = None,
) -> Vocab:
    """Build a ``Vocab`` with sensible defaults for tests."""
    return Vocab(
        id=vocab_id(expression, reading),
        expression=expression,
        reading=reading,
        reading_segments=(RubySegment(base=expression, reading=reading),),
        meaning="test meaning",
        part_of_speech=("noun",),
        tags=tags,
        level=level,
        sentence=sentence,
    )


def make_kanji_details(**overrides: object) -> KanjiDetails:
    """Build ``KanjiDetails`` with defaults, overriding any field by keyword."""
    values: dict[str, object] = {
        "meanings": ("day",),
        "on_readings": ("ニチ",),
        "kun_readings": ("ひ",),
        "stroke_count": 4,
        "grade": 1,
        "frequency": 1,
        "radical": 72,
    }
    values.update(overrides)
    return KanjiDetails.model_validate(values)


class FakeKanjiSource:
    """In-memory kanji source for unit tests (duck-types ``KanjiInfoSource``)."""

    def __init__(self, details: dict[str, KanjiDetails] | None = None) -> None:
        self.details = details or {}
        self.calls: list[str] = []

    def get_kanji(self, char: str) -> KanjiDetails | None:
        """Return canned details, recording each lookup."""
        self.calls.append(char)
        return self.details.get(char)


@pytest.fixture
def app_config(tmp_path: Path) -> AppConfig:
    """An ``AppConfig`` rooted in a temporary directory."""
    return AppConfig(
        data_dir=tmp_path / "data",
        resources_dir=tmp_path / "resources",
        deck_filename=DEFAULT_DECK_FILENAME,
        deck_sha256=DEFAULT_DECK_SHA256,
        jamdict_db=None,
        log_level="INFO",
    )


@pytest.fixture
def quiet_logger() -> logging.Logger:
    """A logger that stays out of test output."""
    logger = logging.getLogger("bunsho.tests")
    logger.setLevel(logging.CRITICAL)
    return logger
