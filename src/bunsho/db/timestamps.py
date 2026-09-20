"""Fixed-width UTC timestamp strings for ``progress.db``.

The width is fixed so that ``due <= :now`` comparisons in SQL are ordinary string comparisons.
"""

from __future__ import annotations

from datetime import UTC, datetime

_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def format_timestamp(value: datetime) -> str:
    """Format ``value`` as a UTC string such as ``2026-09-20T12:00:00.000000Z``.

    Args:
        value: A timezone-aware datetime.

    Returns:
        The 27-character UTC string.

    Raises:
        ValueError: ``value`` is naive.
    """
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware (a naive datetime has no timezone)")
    return value.astimezone(UTC).strftime(_FORMAT)


def parse_timestamp(text: str) -> datetime:
    """Parse a string written by ``format_timestamp`` into an aware UTC datetime.

    Raises:
        ValueError: ``text`` is not in the stored format.
    """
    return datetime.strptime(text, _FORMAT).replace(tzinfo=UTC)
