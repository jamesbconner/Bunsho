"""Shared application context passed explicitly instead of using globals."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from bunsho.config.settings import AppConfig
from bunsho.services.content_repository import ContentRepository
from bunsho.services.protocols import KanjiInfoSource


@dataclass(slots=True)
class Context:
    """Configuration, logger, operational flags and shared services.

    Services that failed to initialize are ``None``; callers must check before use.
    """

    config: AppConfig
    logger: logging.Logger
    dry_run: bool = False
    kanji_source: KanjiInfoSource | None = None
    content_repo: ContentRepository | None = None
