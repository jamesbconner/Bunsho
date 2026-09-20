from datetime import UTC, datetime, timedelta, timezone

import pytest

from bunsho.db.timestamps import format_timestamp, parse_timestamp


def test_format_is_fixed_width_utc() -> None:
    assert (
        format_timestamp(datetime(2026, 9, 20, 12, 0, tzinfo=UTC)) == "2026-09-20T12:00:00.000000Z"
    )
    assert len(format_timestamp(datetime(2026, 1, 2, 3, 4, 5, 6, tzinfo=UTC))) == 27


def test_round_trip_keeps_microseconds() -> None:
    moment = datetime(2026, 9, 20, 12, 0, 1, 123456, tzinfo=UTC)
    assert parse_timestamp(format_timestamp(moment)) == moment


def test_other_offsets_are_converted_to_utc() -> None:
    tokyo = timezone(timedelta(hours=9))
    assert format_timestamp(datetime(2026, 9, 20, 21, 0, tzinfo=tokyo)) == (
        "2026-09-20T12:00:00.000000Z"
    )


def test_lexicographic_order_matches_time_order() -> None:
    earlier = format_timestamp(datetime(2026, 9, 20, 12, 0, 0, 5, tzinfo=UTC))
    later = format_timestamp(datetime(2026, 9, 20, 12, 0, 1, tzinfo=UTC))
    assert earlier < later


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValueError, match="timezone"):
        format_timestamp(datetime(2026, 9, 20, 12, 0))
