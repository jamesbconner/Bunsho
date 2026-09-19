"""Static hiragana and katakana tables."""

from __future__ import annotations

from collections.abc import Callable

from bunsho.models.content import Kana, KanaKind, KanaScript, kana_id

_Row = tuple[str, str]

_BASIC: tuple[tuple[str, tuple[_Row, ...]], ...] = (
    ("vowels", (("あ", "a"), ("い", "i"), ("う", "u"), ("え", "e"), ("お", "o"))),
    ("k", (("か", "ka"), ("き", "ki"), ("く", "ku"), ("け", "ke"), ("こ", "ko"))),
    ("s", (("さ", "sa"), ("し", "shi"), ("す", "su"), ("せ", "se"), ("そ", "so"))),
    ("t", (("た", "ta"), ("ち", "chi"), ("つ", "tsu"), ("て", "te"), ("と", "to"))),
    ("n", (("な", "na"), ("に", "ni"), ("ぬ", "nu"), ("ね", "ne"), ("の", "no"))),
    ("h", (("は", "ha"), ("ひ", "hi"), ("ふ", "fu"), ("へ", "he"), ("ほ", "ho"))),
    ("m", (("ま", "ma"), ("み", "mi"), ("む", "mu"), ("め", "me"), ("も", "mo"))),
    ("y", (("や", "ya"), ("ゆ", "yu"), ("よ", "yo"))),
    ("r", (("ら", "ra"), ("り", "ri"), ("る", "ru"), ("れ", "re"), ("ろ", "ro"))),
    ("w", (("わ", "wa"), ("を", "wo"))),
    ("n-final", (("ん", "n"),)),
)

_DAKUTEN: tuple[tuple[str, tuple[_Row, ...]], ...] = (
    ("g", (("が", "ga"), ("ぎ", "gi"), ("ぐ", "gu"), ("げ", "ge"), ("ご", "go"))),
    ("z", (("ざ", "za"), ("じ", "ji"), ("ず", "zu"), ("ぜ", "ze"), ("ぞ", "zo"))),
    ("d", (("だ", "da"), ("ぢ", "ji"), ("づ", "zu"), ("で", "de"), ("ど", "do"))),
    ("b", (("ば", "ba"), ("び", "bi"), ("ぶ", "bu"), ("べ", "be"), ("ぼ", "bo"))),
    ("p", (("ぱ", "pa"), ("ぴ", "pi"), ("ぷ", "pu"), ("ぺ", "pe"), ("ぽ", "po"))),
)

_SMALL_Y = ("ゃ", "ゅ", "ょ")
_YOUON: tuple[tuple[str, tuple[str, str, str]], ...] = (
    ("き", ("kya", "kyu", "kyo")),
    ("し", ("sha", "shu", "sho")),
    ("ち", ("cha", "chu", "cho")),
    ("に", ("nya", "nyu", "nyo")),
    ("ひ", ("hya", "hyu", "hyo")),
    ("み", ("mya", "myu", "myo")),
    ("り", ("rya", "ryu", "ryo")),
    ("ぎ", ("gya", "gyu", "gyo")),
    ("じ", ("ja", "ju", "jo")),
    ("び", ("bya", "byu", "byo")),
    ("ぴ", ("pya", "pyu", "pyo")),
)

_Entry = tuple[str, str, str, KanaKind]


def _hiragana_entries() -> list[_Entry]:
    entries: list[_Entry] = []
    for kind, table in ((KanaKind.BASIC, _BASIC), (KanaKind.DAKUTEN, _DAKUTEN)):
        for group, rows in table:
            entries.extend((char, romaji, group, kind) for char, romaji in rows)
    for base, romaji_forms in _YOUON:
        for small, romaji in zip(_SMALL_Y, romaji_forms, strict=True):
            entries.append((base + small, romaji, "youon", KanaKind.YOUON))
    return entries


def _to_katakana(text: str) -> str:
    """Shift hiragana code points (U+3041..U+3096) to katakana (+0x60)."""
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in text)


def _identity(text: str) -> str:
    return text


class KanaSource:
    """Provides the full hiragana and katakana study set."""

    def all_kana(self) -> list[Kana]:
        """Return 104 hiragana followed by 104 katakana."""
        entries = _hiragana_entries()
        converters: tuple[tuple[KanaScript, Callable[[str], str]], ...] = (
            (KanaScript.HIRAGANA, _identity),
            (KanaScript.KATAKANA, _to_katakana),
        )
        return [
            Kana(
                id=kana_id(script, glyph),
                script=script,
                char=glyph,
                romaji=romaji,
                kind=kind,
                group=group,
            )
            for script, convert in converters
            for char, romaji, group, kind in entries
            for glyph in (convert(char),)
        ]
