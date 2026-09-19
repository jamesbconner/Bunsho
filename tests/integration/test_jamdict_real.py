from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from bunsho.services.jamdict_service import JamdictService, JamdictUnavailableError


@pytest.fixture(scope="module")
def service() -> JamdictService:
    try:
        return JamdictService()
    except JamdictUnavailableError as exc:
        pytest.skip(f"jamdict-data-fix database unavailable: {exc}")


@pytest.mark.integration
def test_real_lookup_of_nichi(service: JamdictService) -> None:
    details = service.get_kanji("日")
    assert details is not None
    assert details.stroke_count == 4
    assert "day" in details.meanings
    assert {"ニチ", "ジツ"} <= set(details.on_readings)
    assert "ひ" in details.kun_readings
    assert details.radical == 72


@pytest.mark.integration
def test_real_lookup_of_non_kanji_is_none(service: JamdictService) -> None:
    assert service.get_kanji("あ") is None


@pytest.mark.integration
def test_real_lookup_with_explicit_db_path() -> None:
    import jamdict_data

    try:
        service = JamdictService(Path(jamdict_data.JAMDICT_DB_PATH))
    except JamdictUnavailableError as exc:
        pytest.skip(f"jamdict-data-fix database unavailable: {exc}")
    details = service.get_kanji("日")
    assert details is not None
    assert details.stroke_count == 4


@pytest.mark.integration
def test_real_lookup_from_worker_thread() -> None:
    try:
        service = JamdictService()
    except JamdictUnavailableError as exc:
        pytest.skip(f"jamdict-data-fix database unavailable: {exc}")
    with ThreadPoolExecutor(max_workers=1) as pool:
        worker_details = pool.submit(service.get_kanji, "日").result()
    assert worker_details is not None
    assert worker_details.stroke_count == 4
    main_details = service.get_kanji("日")
    assert main_details is not None
    assert main_details.stroke_count == 4


# Verified with an independent one-off query against jamdict_data.JAMDICT_DB_PATH:
# SELECT literal FROM Character WHERE CAST(grade AS INTEGER) BETWEEN 1 AND 10
# returns 2,998 rows; keeping only bunsho.text.is_kanji characters leaves 2,941
# (the other 57 are CJK compatibility ideographs).
REAL_GRADED_KANJI_COUNT = 2941


@pytest.mark.integration
def test_real_graded_kanji_catalog(service: JamdictService) -> None:
    graded = service.graded_kanji()
    assert len(graded) == REAL_GRADED_KANJI_COUNT
    assert "日" in graded
    assert "\ufa19" not in graded
    assert graded == sorted(graded)
    assert len(set(graded)) == len(graded)


@pytest.mark.integration
def test_real_graded_kanji_from_worker_thread(service: JamdictService) -> None:
    with ThreadPoolExecutor(max_workers=1) as pool:
        worker_result = pool.submit(service.graded_kanji).result()
    assert len(worker_result) == REAL_GRADED_KANJI_COUNT
    assert worker_result == service.graded_kanji()
