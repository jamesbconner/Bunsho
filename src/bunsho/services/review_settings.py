"""Loading and saving the review settings document."""

from __future__ import annotations

import logging

from pydantic import ValidationError

from bunsho.db.progress_repository import ProgressRepository
from bunsho.models.review_settings import ReviewSettings

SETTINGS_KEY = "review_settings"
"""The ``app_setting`` row that holds the whole settings document as JSON."""


class ReviewSettingsService:
    """Stores the review settings as one JSON document, so a save is atomic."""

    def __init__(self, progress: ProgressRepository, logger: logging.Logger) -> None:
        """Create the service.

        Args:
            progress: Repository for ``app_setting`` rows.
            logger: Logger for key=value messages.
        """
        self._progress = progress
        self._logger = logger

    async def load(self) -> ReviewSettings:
        """Return the saved settings, or the defaults if none are saved or the row is invalid.

        An invalid stored document (for example written by a newer version) is logged at
        WARNING and ignored rather than blocking every review.
        """
        raw = await self._progress.get_setting(SETTINGS_KEY)
        if raw is None:
            return ReviewSettings()
        try:
            return ReviewSettings.model_validate_json(raw)
        except ValidationError as exc:
            self._logger.warning(
                "review_settings_invalid using=defaults errors=%d", exc.error_count()
            )
            return ReviewSettings()

    async def save(self, settings: ReviewSettings) -> ReviewSettings:
        """Store ``settings`` (a full replacement) and return them."""
        await self._progress.set_setting(SETTINGS_KEY, settings.model_dump_json())
        return settings
