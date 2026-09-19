"""Logging configuration."""

from __future__ import annotations

import logging

LOG_FORMAT = "%(asctime)s level=%(levelname)s logger=%(name)s %(message)s"


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger with a logfmt-style line format.

    Args:
        level: A standard level name such as ``INFO`` or ``DEBUG``.
    """
    logging.basicConfig(level=level.upper(), format=LOG_FORMAT, force=True)
