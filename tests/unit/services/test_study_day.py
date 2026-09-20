import logging
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from bunsho.services.study_day import resolve_timezone, study_date, study_day_window

NEW_YORK = ZoneInfo("America/New_York")


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def test_the_window_starts_at_the_rollover_hour_of_the_current_day() -> None:
    start, end = study_day_window(utc(2026, 9, 20, 12), 4, UTC)
    assert (start, end) == (utc(2026, 9, 20, 4), utc(2026, 9, 21, 4))


def test_before_the_rollover_hour_belongs_to_the_previous_day() -> None:
    start, end = study_day_window(utc(2026, 9, 20, 3, 59), 4, UTC)
    assert (start, end) == (utc(2026, 9, 19, 4), utc(2026, 9, 20, 4))


def test_the_boundary_instant_starts_the_new_day() -> None:
    start, _ = study_day_window(utc(2026, 9, 20, 4), 4, UTC)
    assert start == utc(2026, 9, 20, 4)


def test_the_window_follows_the_timezone() -> None:
    # 12:00 UTC on 20 Sep is 08:00 in New York (EDT, UTC-4): the day began at 04:00 EDT.
    start, end = study_day_window(utc(2026, 9, 20, 12), 4, NEW_YORK)
    assert (start, end) == (utc(2026, 9, 20, 8), utc(2026, 9, 21, 8))


def test_the_spring_forward_day_is_23_hours_long() -> None:
    # New York clocks jump forward at 02:00 EST (07:00 UTC) on 2026-03-08. 07:30 UTC is
    # 03:30 EDT, still before that day's 04:00 rollover, so it belongs to the 7th.
    start, end = study_day_window(utc(2026, 3, 8, 7, 30), 4, NEW_YORK)
    assert (start, end) == (utc(2026, 3, 7, 9), utc(2026, 3, 8, 8))  # 04:00 EST to 04:00 EDT
    assert end - start == timedelta(hours=23)


def test_the_fall_back_day_is_25_hours_long() -> None:
    # Clocks go back at 02:00 EDT on 2026-11-01. The day that starts at 04:00 EDT on 31 Oct
    # ends at 04:00 EST on 1 Nov, one hour later than 24 hours.
    start, end = study_day_window(utc(2026, 10, 31, 20), 4, NEW_YORK)
    assert (start, end) == (utc(2026, 10, 31, 8), utc(2026, 11, 1, 9))
    assert end - start == timedelta(hours=25)


def test_consecutive_windows_tile_without_gaps() -> None:
    moment = utc(2026, 3, 6, 12)
    windows = []
    for _ in range(5):
        start, end = study_day_window(moment, 4, NEW_YORK)
        windows.append((start, end))
        moment = end
    for (_, previous_end), (next_start, _) in zip(windows, windows[1:], strict=False):
        assert previous_end == next_start


def test_study_date_uses_the_rollover_hour() -> None:
    assert study_date(utc(2026, 9, 20, 3, 59), 4, UTC) == date(2026, 9, 19)
    assert study_date(utc(2026, 9, 20, 4, 0), 4, UTC) == date(2026, 9, 20)
    assert study_date(utc(2026, 9, 20, 12), 4, NEW_YORK) == date(2026, 9, 20)


def test_a_naive_instant_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone"):
        study_day_window(datetime(2026, 9, 20, 12), 4, UTC)


def test_resolve_timezone_uses_an_explicit_name() -> None:
    assert resolve_timezone("America/New_York") == NEW_YORK


def test_resolve_timezone_reads_the_tz_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    assert resolve_timezone() == ZoneInfo("Asia/Tokyo")


def test_resolve_timezone_falls_back_to_utc_with_a_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("TZ", raising=False)
    logger = logging.getLogger("bunsho.tests.tz")
    with caplog.at_level(logging.WARNING, logger=logger.name):
        assert resolve_timezone(logger=logger) == UTC
        assert resolve_timezone("Not/AZone", logger=logger) == UTC
    assert "study_timezone_not_set" in caplog.text
    assert "study_timezone_unknown" in caplog.text
