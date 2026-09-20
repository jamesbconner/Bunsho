"""The "study day": daily limits reset at a rollover hour in the server's timezone."""

from __future__ import annotations

import logging
import os
from datetime import UTC, date, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def study_day_window(now: datetime, rollover_hour: int, tz: tzinfo) -> tuple[datetime, datetime]:
    """Return the study day containing ``now`` as UTC instants ``[start, end)``.

    A study day starts at ``rollover_hour`` o'clock wall time in ``tz`` and ends at the
    next such moment, so it is 23 or 25 hours long across a DST change.

    Args:
        now: A timezone-aware instant.
        rollover_hour: Hour of the day (0-23) at which a new study day begins.
        tz: The timezone in which the rollover hour is read.

    Returns:
        The window start (inclusive) and end (exclusive), both in UTC.

    Raises:
        ValueError: ``now`` is naive.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware (a naive datetime has no timezone)")
    local = now.astimezone(tz)
    # fold=0: an ambiguous rollover hour (DST fall-back) starts on its first occurrence, whatever
    # fold ``now`` carries, so every instant in a study day agrees on where the day began.
    start = local.replace(hour=rollover_hour, minute=0, second=0, microsecond=0, fold=0)
    if local < start:
        start -= timedelta(days=1)
    end = start + timedelta(days=1)  # wall-clock arithmetic: keeps the rollover hour across DST
    return start.astimezone(UTC), end.astimezone(UTC)


def study_date(instant: datetime, rollover_hour: int, tz: tzinfo) -> date:
    """Return the calendar date of the study day containing ``instant``."""
    start, _ = study_day_window(instant, rollover_hour, tz)
    return start.astimezone(tz).date()


def resolve_timezone(name: str | None = None, *, logger: logging.Logger | None = None) -> tzinfo:
    """Return the timezone for study days.

    Args:
        name: An IANA name such as ``America/New_York``. ``None`` reads the ``TZ``
            environment variable.
        logger: Logger for the fallback warnings.

    Returns:
        The named zone, or UTC (with a WARNING) when none is set or the name is unknown.
    """
    log = logger or logging.getLogger(__name__)
    chosen = os.environ.get("TZ", "") if name is None else name
    if not chosen:
        log.warning("study_timezone_not_set using=UTC hint='set TZ, e.g. TZ=America/New_York'")
        return UTC
    try:
        return ZoneInfo(chosen)
    except (ZoneInfoNotFoundError, ValueError):
        log.warning("study_timezone_unknown name=%s using=UTC", chosen)
        return UTC
