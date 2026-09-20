from datetime import UTC, datetime

import pytest

from bunsho.factories import create_scheduler
from bunsho.models.review import Grade
from bunsho.services.fsrs_scheduler import FSRSScheduler


def test_create_scheduler_builds_the_fsrs_scheduler_by_default() -> None:
    assert isinstance(create_scheduler(), FSRSScheduler)


def test_create_scheduler_passes_the_retention_through() -> None:
    now = datetime(2026, 9, 20, 12, tzinfo=UTC)
    high = create_scheduler("fsrs", desired_retention=0.97, enable_fuzzing=False)
    low = create_scheduler("fsrs", desired_retention=0.80, enable_fuzzing=False)
    review = high.schedule(high.initial(now), Grade.EASY, now)
    assert (
        high.schedule(review, Grade.GOOD, review.due).due
        < low.schedule(review, Grade.GOOD, review.due).due
    )


def test_create_scheduler_rejects_unknown_kinds() -> None:
    with pytest.raises(ValueError, match="sm2"):
        create_scheduler("sm2")
