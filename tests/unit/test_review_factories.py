from datetime import UTC, datetime

import pytest

from bunsho.factories import (
    create_new_card_policy,
    create_scheduler,
    create_scheduler_from_settings,
)
from bunsho.models.content import JlptLevel
from bunsho.models.review import CardDirection, CardKey, CatalogEntry, Grade, ItemType
from bunsho.models.review_settings import NewCardPolicyName, ReviewSettings
from bunsho.services.fsrs_scheduler import FSRSScheduler
from bunsho.services.new_card_policies import (
    MasteryUnlockPolicy,
    PinnedLevelsPolicy,
    StrictOrderPolicy,
)


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


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (NewCardPolicyName.STRICT_ORDER, StrictOrderPolicy),
        (NewCardPolicyName.MASTERY_UNLOCK, MasteryUnlockPolicy),
        (NewCardPolicyName.PINNED_LEVELS, PinnedLevelsPolicy),
    ],
)
def test_create_new_card_policy_picks_the_policy_by_name(
    name: NewCardPolicyName, expected: type
) -> None:
    assert isinstance(create_new_card_policy(ReviewSettings(new_card_policy=name)), expected)


def test_the_pinned_policy_uses_the_active_levels_setting() -> None:
    settings = ReviewSettings(new_card_policy=NewCardPolicyName.PINNED_LEVELS, active_levels=["N4"])
    catalog = [
        CatalogEntry("n5-word", ItemType.VOCAB, JlptLevel.N5, 0),
        CatalogEntry("n4-word", ItemType.VOCAB, JlptLevel.N4, 1),
    ]
    chosen = create_new_card_policy(settings).select(ItemType.VOCAB, catalog, {}, None)
    assert chosen == [
        CardKey("n4-word", CardDirection.RECOGNITION),
        CardKey("n4-word", CardDirection.RECALL),
    ]


def test_an_unknown_policy_name_is_rejected() -> None:
    settings = ReviewSettings.model_construct(new_card_policy="bogus")
    with pytest.raises(ValueError, match="bogus"):
        create_new_card_policy(settings)


def test_the_scheduler_follows_the_target_retention_setting() -> None:
    now = datetime(2026, 9, 20, 12, tzinfo=UTC)
    high = create_scheduler_from_settings(ReviewSettings(target_retention=0.97))
    low = create_scheduler_from_settings(ReviewSettings(target_retention=0.80))
    assert isinstance(high, FSRSScheduler)
    base = create_scheduler("fsrs", enable_fuzzing=False)
    review = base.schedule(base.initial(now), Grade.EASY, now)
    high_due = high.preview(review, review.due)[Grade.GOOD].due
    low_due = low.preview(review, review.due)[Grade.GOOD].due
    assert high_due < low_due
