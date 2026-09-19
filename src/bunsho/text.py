"""Small Japanese text helpers."""

from __future__ import annotations


def is_kanji(char: str) -> bool:
    """Return whether ``char`` is a single CJK ideograph (iteration mark ``々`` excluded)."""
    return len(char) == 1 and ("一" <= char <= "鿿" or "㐀" <= char <= "䶿")


def extract_kanji(text: str) -> list[str]:
    """Return every kanji in ``text`` in order, keeping repeats."""
    return [char for char in text if is_kanji(char)]
