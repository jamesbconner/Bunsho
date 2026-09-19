"""Parser for Anki-style furigana markup, e.g. ``漢字[かんじ]``."""

from __future__ import annotations

import re
from collections.abc import Sequence

from bunsho.models.content import RubySegment

_TAG = re.compile(r"(<[^>]*>)")
_RUBY = re.compile(r"(?:^|\s|(?<=]))([^\s\[\]]+)\[([^\]]+)\]")


def parse_furigana(text: str) -> tuple[RubySegment, ...]:
    """Split furigana markup into ruby segments.

    ``<mark>`` regions produce ``highlighted`` segments; all other HTML tags are dropped.

    Args:
        text: Markup such as ``体[からだ]つき``.

    Returns:
        Segments in reading order; empty for empty input.

    Examples:
        >>> parse_furigana("体[からだ]つき")[0].reading
        'からだ'
    """
    segments: list[RubySegment] = []
    highlighted = False
    for part in _TAG.split(text):
        if part == "<mark>":
            highlighted = True
        elif part == "</mark>":
            highlighted = False
        elif not part or _TAG.fullmatch(part):
            continue
        else:
            segments.extend(_parse_chunk(part, highlighted))
    return tuple(segments)


def _parse_chunk(chunk: str, highlighted: bool) -> list[RubySegment]:
    segments: list[RubySegment] = []
    cursor = 0
    for match in _RUBY.finditer(chunk):
        if match.start() > cursor:
            segments.append(
                RubySegment(base=chunk[cursor : match.start()], highlighted=highlighted)
            )
        segments.append(
            RubySegment(base=match.group(1), reading=match.group(2), highlighted=highlighted)
        )
        cursor = match.end()
    if cursor < len(chunk):
        segments.append(RubySegment(base=chunk[cursor:], highlighted=highlighted))
    return segments


def plain_reading(segments: Sequence[RubySegment]) -> str:
    """Return the all-kana reading (rubies replaced by their readings)."""
    return "".join(segment.reading or segment.base for segment in segments)


def plain_text(segments: Sequence[RubySegment]) -> str:
    """Return the text as written, without furigana."""
    return "".join(segment.base for segment in segments)
