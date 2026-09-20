from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from bunsho.models.review import CardSchedule, Grade, SchedState
from bunsho.services.fsrs_scheduler import FSRSScheduler

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def make(retention: float = 0.9) -> FSRSScheduler:
    return FSRSScheduler(desired_retention=retention, enable_fuzzing=False)


def test_initial_card_is_new_and_due_now() -> None:
    card = make().initial(NOW)
    assert card.state is SchedState.NEW
    assert card.due == NOW
    assert card.last_review is None
    assert card.stability is None


def test_good_on_a_new_card_records_the_review() -> None:
    scheduler = make()
    after = scheduler.schedule(scheduler.initial(NOW), Grade.GOOD, NOW)
    assert after.state in {SchedState.LEARNING, SchedState.REVIEW}
    assert after.last_review == NOW
    assert after.due > NOW
    assert after.stability is not None
    assert after.difficulty is not None


def test_again_on_a_new_card_comes_back_within_the_hour() -> None:
    scheduler = make()
    after = scheduler.schedule(scheduler.initial(NOW), Grade.AGAIN, NOW)
    assert after.state is SchedState.LEARNING
    assert NOW < after.due <= NOW + timedelta(hours=1)


def test_easy_on_a_new_card_graduates_to_review_a_day_or_more_out() -> None:
    scheduler = make()
    after = scheduler.schedule(scheduler.initial(NOW), Grade.EASY, NOW)
    assert after.state is SchedState.REVIEW
    assert after.due >= NOW + timedelta(days=1)


def test_again_on_a_review_card_relearns() -> None:
    scheduler = make()
    review = scheduler.schedule(scheduler.initial(NOW), Grade.EASY, NOW)
    lapsed = scheduler.schedule(review, Grade.AGAIN, review.due)
    assert lapsed.state is SchedState.RELEARNING
    assert lapsed.due > review.due


@pytest.mark.parametrize("first_grade", [None, Grade.EASY])
def test_a_better_grade_never_schedules_sooner(first_grade: Grade | None) -> None:
    scheduler = make()
    card = scheduler.initial(NOW)
    moment = NOW
    if first_grade is not None:
        card = scheduler.schedule(card, first_grade, NOW)
        moment = card.due
    preview = scheduler.preview(card, moment)
    dues = [preview[grade].due for grade in (Grade.AGAIN, Grade.HARD, Grade.GOOD, Grade.EASY)]
    assert dues == sorted(dues)


def test_preview_matches_actual_scheduling_when_fuzzing_is_off() -> None:
    scheduler = make()
    card = scheduler.initial(NOW)
    preview = scheduler.preview(card, NOW)
    for grade in Grade:
        assert preview[grade] == scheduler.schedule(card, grade, NOW)


def test_a_higher_target_retention_schedules_sooner() -> None:
    base = make()
    review = base.schedule(base.initial(NOW), Grade.EASY, NOW)
    high = make(0.97).schedule(review, Grade.GOOD, review.due)
    low = make(0.80).schedule(review, Grade.GOOD, review.due)
    assert high.due < low.due


def test_a_naive_now_is_rejected() -> None:
    scheduler = make()
    with pytest.raises(ValueError, match="timezone"):
        scheduler.schedule(scheduler.initial(NOW), Grade.GOOD, datetime(2026, 9, 20, 12, 0))


def test_a_non_utc_now_is_normalised_to_utc() -> None:
    scheduler = make()
    tokyo = NOW.astimezone(ZoneInfo("Asia/Tokyo"))
    after = scheduler.schedule(scheduler.initial(NOW), Grade.GOOD, tokyo)
    assert after.last_review == NOW
    assert after.due.utcoffset() == timedelta(0)


def test_schedule_does_not_mutate_its_input() -> None:
    scheduler = make()
    card = scheduler.initial(NOW)
    snapshot = card.model_copy()
    scheduler.schedule(card, Grade.GOOD, NOW)
    assert card == snapshot


def test_states_round_trip_through_card_schedule() -> None:
    scheduler = make()
    review = scheduler.schedule(scheduler.initial(NOW), Grade.EASY, NOW)
    assert CardSchedule.model_validate(review.model_dump()) == review
