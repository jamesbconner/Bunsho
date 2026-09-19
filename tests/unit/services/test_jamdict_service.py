import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
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


def test_empty_db_file_is_an_error(tmp_path: Path) -> None:
    empty = tmp_path / "empty.db"
    empty.write_bytes(b"")
    with pytest.raises(JamdictUnavailableError):
        JamdictService(empty)


def test_corrupt_db_file_is_an_error(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"not a sqlite database")
    with pytest.raises(JamdictUnavailableError):
        JamdictService(corrupt)


class _CountingJam(_FakeJam):
    """Fake ``Jamdict`` class that records how many instances were constructed."""

    instances: list["_CountingJam"] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__({"日": _character(), "月": _character(literal="月")})
        self.args, self.kwargs = args, kwargs
        self.db_file = kwargs.get("db_file")
        type(self).instances.append(self)


@pytest.fixture
def counting_jam(monkeypatch: pytest.MonkeyPatch) -> type[_CountingJam]:
    _CountingJam.instances = []
    monkeypatch.setattr("bunsho.services.jamdict_service.Jamdict", _CountingJam)
    return _CountingJam


def _lookup_on_new_thread(service: JamdictService, char: str) -> Any:
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(service.get_kanji, char).result()


def test_each_thread_gets_its_own_jamdict_for_explicit_path(
    tmp_path: Path, counting_jam: type[_CountingJam]
) -> None:
    db_file = tmp_path / "jam.db"
    db_file.write_bytes(b"placeholder")
    service = JamdictService(db_file)
    assert len(counting_jam.instances) == 1  # constructed once, on this thread
    assert counting_jam.instances[0].kwargs["db_file"] == str(db_file)

    assert service.get_kanji("日") is not None
    assert service.get_kanji("月") is not None
    assert len(counting_jam.instances) == 1  # same thread: no new instance

    assert _lookup_on_new_thread(service, "日") is not None
    assert len(counting_jam.instances) == 2  # other thread: its own instance
    assert counting_jam.instances[1].kwargs == counting_jam.instances[0].kwargs

    assert service.get_kanji("日") is not None
    assert len(counting_jam.instances) == 2


def test_each_thread_gets_its_own_jamdict_for_default_database(
    counting_jam: type[_CountingJam],
) -> None:
    service = JamdictService()
    assert len(counting_jam.instances) == 1
    assert service.get_kanji("日") is not None
    assert len(counting_jam.instances) == 1
    assert _lookup_on_new_thread(service, "日") is not None
    assert len(counting_jam.instances) == 2
    assert counting_jam.instances[1].args == counting_jam.instances[0].args == ()
    assert counting_jam.instances[1].kwargs == counting_jam.instances[0].kwargs == {}


def test_injected_jam_is_shared_by_all_threads(counting_jam: type[_CountingJam]) -> None:
    service = JamdictService(jam=_FakeJam({"日": _character()}))
    assert service.get_kanji("日") is not None
    assert _lookup_on_new_thread(service, "日") is not None
    assert counting_jam.instances == []


_GRADED_ROWS: list[tuple[str, str | None]] = [
    ("犬", "1"),
    ("猫", "8"),
    ("龘", "9"),
    ("鼠", "10"),
    ("一", "11"),  # above the graded range
    ("二", None),  # no grade
    ("三", "n/a"),  # non-numeric grade
    ("\ufa19", "10"),  # CJK compatibility ideograph: excluded
    ("あ", "1"),  # not a kanji: excluded
    ("日", "1"),
]


def _make_character_db(path: Path, rows: list[tuple[str, str | None]] = _GRADED_ROWS) -> Path:
    with closing(sqlite3.connect(path)) as con, con:
        con.execute(
            "CREATE TABLE Character (ID INTEGER PRIMARY KEY, literal TEXT NOT NULL, "
            "stroke_count INTEGER, grade TEXT, freq TEXT, jlpt TEXT)"
        )
        con.executemany("INSERT INTO Character (literal, grade) VALUES (?, ?)", rows)
    return path


def _service_with_db_file(db_file: Path | str | None) -> JamdictService:
    jam = _FakeJam({})
    jam.db_file = db_file  # type: ignore[attr-defined]
    return JamdictService(jam=jam)


def test_graded_kanji_returns_grades_one_to_ten_sorted_without_compatibility_forms(
    tmp_path: Path,
) -> None:
    service = _service_with_db_file(_make_character_db(tmp_path / "jam.db"))
    result = service.graded_kanji()
    assert result == sorted(["犬", "猫", "龘", "鼠", "日"])
    assert result == sorted(result)
    assert "\ufa19" not in result
    assert "あ" not in result


def test_graded_kanji_accepts_a_path_object_or_string(tmp_path: Path) -> None:
    db_file = _make_character_db(tmp_path / "jam.db")
    assert (
        _service_with_db_file(str(db_file)).graded_kanji()
        == _service_with_db_file(db_file).graded_kanji()
    )


def test_graded_kanji_uses_the_explicit_database_path(
    tmp_path: Path, counting_jam: type[_CountingJam]
) -> None:
    db_file = _make_character_db(tmp_path / "jam.db")
    service = JamdictService(db_file)
    assert "犬" in service.graded_kanji()
    assert len(counting_jam.instances) == 1  # no extra Jamdict instance is needed


def test_graded_kanji_works_from_a_worker_thread(tmp_path: Path) -> None:
    service = _service_with_db_file(_make_character_db(tmp_path / "jam.db"))
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(service.graded_kanji).result() == service.graded_kanji()


@pytest.mark.parametrize("db_file", [None, 42])
def test_graded_kanji_needs_a_database_path(db_file: object) -> None:
    jam = _FakeJam({})
    if db_file is not None:
        jam.db_file = db_file  # type: ignore[attr-defined]
    with pytest.raises(JamdictUnavailableError, match="database path"):
        JamdictService(jam=jam).graded_kanji()


def test_graded_kanji_with_a_corrupt_database_is_an_error(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"not a sqlite database")
    with pytest.raises(JamdictUnavailableError, match="graded kanji"):
        _service_with_db_file(corrupt).graded_kanji()


def test_graded_kanji_with_a_missing_database_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(JamdictUnavailableError, match="graded kanji"):
        _service_with_db_file(tmp_path / "missing.db").graded_kanji()


def test_graded_kanji_with_a_database_lacking_the_character_table_is_an_error(
    tmp_path: Path,
) -> None:
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    with pytest.raises(JamdictUnavailableError, match="graded kanji"):
        _service_with_db_file(empty).graded_kanji()


def test_graded_kanji_does_not_modify_the_database(tmp_path: Path) -> None:
    db_file = _make_character_db(tmp_path / "jam.db")
    before = db_file.read_bytes()
    _service_with_db_file(db_file).graded_kanji()
    assert db_file.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["jam.db"]  # no journal left behind
