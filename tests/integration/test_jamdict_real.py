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
