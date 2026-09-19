"""Domain models for study content (kana, kanji, vocabulary, sentences)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum, StrEnum

from pydantic import BaseModel, ConfigDict

_LEVEL_TAG = re.compile(r"jlpt_N([1-5])")


class JlptLevel(IntEnum):
    """JLPT level. As on the exam, a higher number is easier (N5 is the easiest)."""

    N1 = 1
    N2 = 2
    N3 = 3
    N4 = 4
    N5 = 5

    @property
    def label(self) -> str:
        """Human-readable name such as ``N3``."""
        return f"N{self.value}"

    @classmethod
    def from_tag(cls, tag: str) -> JlptLevel | None:
        """Parse an Anki tag such as ``jlpt_N3``; return ``None`` for other tags."""
        match = _LEVEL_TAG.fullmatch(tag)
        return cls(int(match.group(1))) if match else None

    @classmethod
    def study_order(cls) -> tuple[JlptLevel, ...]:
        """Levels from easiest to hardest: N5, N4, N3, N2, N1."""
        return (cls.N5, cls.N4, cls.N3, cls.N2, cls.N1)


class KanaScript(StrEnum):
    """Kana writing system."""

    HIRAGANA = "hira"
    KATAKANA = "kata"


class KanaKind(StrEnum):
    """Kana category."""

    BASIC = "basic"
    DAKUTEN = "dakuten"
    YOUON = "youon"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class RubySegment(_Frozen):
    """A run of text, optionally with a furigana reading."""

    base: str
    reading: str | None = None
    highlighted: bool = False


class Sentence(_Frozen):
    """A Japanese example sentence with its English translation."""

    segments: tuple[RubySegment, ...]
    english: str


class Kana(_Frozen):
    """A single kana character (or yōon combination)."""

    id: str
    script: KanaScript
    char: str
    romaji: str
    kind: KanaKind
    group: str


class KanjiDetails(_Frozen):
    """Dictionary facts about a kanji (from KANJIDIC2 via jamdict)."""

    meanings: tuple[str, ...] = ()
    on_readings: tuple[str, ...] = ()
    kun_readings: tuple[str, ...] = ()
    stroke_count: int | None = None
    grade: int | None = None
    frequency: int | None = None
    radical: int | None = None


class Kanji(KanjiDetails):
    """A kanji with its derived JLPT level (``None`` when the deck does not use it)."""

    id: str
    char: str
    level: JlptLevel | None


class Vocab(_Frozen):
    """A vocabulary item imported from the JLPT deck."""

    id: str
    expression: str
    reading: str
    reading_segments: tuple[RubySegment, ...]
    meaning: str
    additional_definitions: str = ""
    part_of_speech: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    level: JlptLevel
    sentence: Sentence | None = None

    @property
    def usually_kana(self) -> bool:
        """Whether the deck marks this word as usually written in kana."""
        return "usually_kana" in self.tags


@dataclass(frozen=True, slots=True)
class ImportedDeck:
    """Result of importing a vocabulary deck."""

    vocab: list[Vocab]
    sha256: str


def kana_id(script: KanaScript, char: str) -> str:
    """Stable ID for a kana, e.g. ``kana:hira:あ``."""
    return f"kana:{script.value}:{char}"


def kanji_id(char: str) -> str:
    """Stable ID for a kanji, e.g. ``kanji:漢``."""
    return f"kanji:{char}"


def vocab_id(expression: str, reading: str) -> str:
    """Stable ID for a vocab item; ``reading`` is the plain kana reading.

    IDs are opaque strings. Homograph notes carry a ``#N`` suffix applied by the importer,
    so callers should obtain ids from ``ContentRepository`` rather than rebuilding them
    with this function.
    """
    return f"vocab:{expression}:{reading}"
