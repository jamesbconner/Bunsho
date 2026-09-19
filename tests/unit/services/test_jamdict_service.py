from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from bunsho.services.jamdict_service import JamdictService, JamdictUnavailableError


def _reading(kind: str, value: str) -> SimpleNamespace:
    return SimpleNamespace(r_type=kind, value=value)


def _character(**overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "literal": "日",
        "stroke_count": 4,
        "grade": 1,
        "freq": 1,
        "jlpt": 4,
        "rm_groups": [
            SimpleNamespace(
                readings=[
                    _reading("pinyin", "ri4"),
                    _reading("ja_on", "ニチ"),
                    _reading("ja_on", "ジツ"),
                    _reading("ja_kun", "ひ"),
                    _reading("ja_kun", "-び"),
                ]
            )
        ],
        "radicals": [SimpleNamespace(rad_type="classical", value="72")],
        "meanings": lambda english_only=False: ["day", "sun"] if english_only else ["day", "jour"],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _FakeJam:
    def __init__(self, chars: dict[str, Any], *, available: bool = True, kd2: bool = True) -> None:
        self._chars, self._available, self._kd2 = chars, available, kd2

    def is_available(self) -> bool:
        return self._available

    def has_kd2(self) -> bool:
        return self._kd2

    def get_char(self, literal: str) -> Any:
        return self._chars.get(literal)


def test_maps_character_to_details() -> None:
    service = JamdictService(jam=_FakeJam({"日": _character()}))
    details = service.get_kanji("日")
    assert details is not None
    assert details.meanings == ("day", "sun")  # English only
    assert details.on_readings == ("ニチ", "ジツ")
    assert details.kun_readings == ("ひ", "-び")
    assert details.stroke_count == 4
    assert details.grade == 1
    assert details.frequency == 1
    assert details.radical == 72


def test_unknown_character_returns_none() -> None:
    assert JamdictService(jam=_FakeJam({})).get_kanji("あ") is None


def test_optional_fields_may_be_missing() -> None:
    character = _character(grade=None, freq=None, radicals=[], stroke_count=0)
    details = JamdictService(jam=_FakeJam({"日": character})).get_kanji("日")
    assert details is not None
    assert (details.grade, details.frequency, details.radical, details.stroke_count) == (
        None,
        None,
        None,
        None,
    )


@pytest.mark.parametrize(("available", "kd2"), [(False, True), (True, False)])
def test_unavailable_database_is_an_error(available: bool, kd2: bool) -> None:
    with pytest.raises(JamdictUnavailableError, match="KANJIDIC2"):
        JamdictService(jam=_FakeJam({}, available=available, kd2=kd2))


def test_missing_db_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(JamdictUnavailableError, match="not found"):
        JamdictService(tmp_path / "missing.db")
