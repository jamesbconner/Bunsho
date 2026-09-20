from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from bunsho.db.engine import ProgressDatabase
from bunsho.db.progress_repository import ProgressRepository
from bunsho.models.review import (
    CardDirection,
    CardKey,
    Grade,
    ItemType,
    SchedState,
    StaleReviewError,
)
from bunsho.services.fsrs_scheduler import FSRSScheduler
from tests.base import run_with_database

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
KANA = CardKey("kana:hira:あ", CardDirection.GLYPH_TO_SOUND)
VOCAB = CardKey("vocab:日本:にほん", CardDirection.RECOGNITION)
SCHEDULER = FSRSScheduler(enable_fuzzing=False)


async def _review(repo: ProgressRepository, key: CardKey, grade: Grade, at: datetime) -> None:
    stored = await repo.get_card(key)
    before = stored.schedule if stored else SCHEDULER.initial(at)
    after = SCHEDULER.schedule(before, grade, at)
    await repo.record_review(
        key, before=before, after=after, grade=grade, mode="flip", duration_ms=1200
    )


def test_the_first_review_creates_the_card_and_logs_it(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        repo = ProgressRepository(db)
        assert await repo.get_card(KANA) is None
        await _review(repo, KANA, Grade.GOOD, NOW)
        stored = await repo.get_card(KANA)
        assert stored is not None
        assert stored.key == KANA
        assert stored.reps == 1
        assert stored.lapses == 0
        assert stored.schedule.last_review == NOW
        assert stored.schedule.state in {SchedState.LEARNING, SchedState.REVIEW}
        [record] = await repo.reviews_between(NOW - timedelta(days=1), NOW + timedelta(days=1))
        assert record.grade is Grade.GOOD
        assert record.state_before is SchedState.NEW
        assert record.direction is CardDirection.GLYPH_TO_SOUND
        assert record.reviewed_at == NOW

    run_with_database(tmp_path, scenario)


def test_later_reviews_update_the_card_and_count_lapses(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        repo = ProgressRepository(db)
        await _review(repo, VOCAB, Grade.EASY, NOW)
        first = await repo.get_card(VOCAB)
        assert first is not None
        assert first.schedule.state is SchedState.REVIEW
        await _review(repo, VOCAB, Grade.AGAIN, first.schedule.due)
        second = await repo.get_card(VOCAB)
        assert second is not None
        assert (second.reps, second.lapses) == (2, 1)
        assert second.schedule.state is SchedState.RELEARNING
        records = await repo.reviews_between(NOW - timedelta(days=1), NOW + timedelta(days=400))
        assert [r.state_before for r in records] == [SchedState.NEW, SchedState.REVIEW]

    run_with_database(tmp_path, scenario)


def test_recording_a_new_card_twice_is_a_stale_review(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        repo = ProgressRepository(db)
        before = SCHEDULER.initial(NOW)
        after = SCHEDULER.schedule(before, Grade.GOOD, NOW)
        await repo.record_review(
            KANA, before=before, after=after, grade=Grade.GOOD, mode="flip", duration_ms=None
        )
        with pytest.raises(StaleReviewError):
            await repo.record_review(
                KANA, before=before, after=after, grade=Grade.GOOD, mode="flip", duration_ms=None
            )
        records = await repo.reviews_between(NOW - timedelta(days=1), NOW + timedelta(days=1))
        assert len(records) == 1

    run_with_database(tmp_path, scenario)


def test_a_review_based_on_an_outdated_state_is_stale_and_leaves_no_log(
    tmp_path: Path,
) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        repo = ProgressRepository(db)
        await _review(repo, VOCAB, Grade.GOOD, NOW)
        outdated = await repo.get_card(VOCAB)
        assert outdated is not None
        await _review(repo, VOCAB, Grade.GOOD, NOW + timedelta(minutes=11))
        after = SCHEDULER.schedule(outdated.schedule, Grade.GOOD, NOW + timedelta(minutes=12))
        with pytest.raises(StaleReviewError):
            await repo.record_review(
                VOCAB,
                before=outdated.schedule,
                after=after,
                grade=Grade.GOOD,
                mode="flip",
                duration_ms=None,
            )
        records = await repo.reviews_between(NOW - timedelta(days=1), NOW + timedelta(days=1))
        assert len(records) == 2  # the rejected review was not logged

    run_with_database(tmp_path, scenario)


def test_a_failure_after_the_card_write_rolls_the_card_back(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        repo = ProgressRepository(db)
        before = SCHEDULER.initial(NOW)
        after = SCHEDULER.schedule(before, Grade.GOOD, NOW)
        # The card row is flushed first; building the log row then fails on ``int(grade)``.
        with pytest.raises(TypeError):
            await repo.record_review(
                KANA,
                before=before,
                after=after,
                grade=None,  # type: ignore[arg-type]
                mode="flip",
                duration_ms=None,
            )
        assert await repo.get_card(KANA) is None
        assert await repo.reviews_between(NOW - timedelta(days=1), NOW + timedelta(days=1)) == []

    run_with_database(tmp_path, scenario)


def test_due_cards_are_ordered_and_limited(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        repo = ProgressRepository(db)
        await _review(repo, VOCAB, Grade.GOOD, NOW)  # due in about ten minutes
        await _review(repo, KANA, Grade.AGAIN, NOW)  # due in about one minute
        later = NOW + timedelta(hours=1)
        due = await repo.due_cards(later, limit=10)
        assert [c.key for c in due] == [KANA, VOCAB]
        assert [c.key for c in await repo.due_cards(later, limit=1)] == [KANA]
        assert await repo.due_cards(NOW, limit=10) == []
        assert await repo.due_counts(later) == {ItemType.KANA: 1, ItemType.VOCAB: 1}
        assert await repo.due_counts(NOW) == {}

    run_with_database(tmp_path, scenario)


def test_next_due_after_finds_the_soonest_future_card(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        repo = ProgressRepository(db)
        assert await repo.next_due_after(NOW) is None
        await _review(repo, VOCAB, Grade.GOOD, NOW)
        await _review(repo, KANA, Grade.AGAIN, NOW)
        soonest = await repo.next_due_after(NOW)
        kana = await repo.get_card(KANA)
        assert kana is not None
        assert soonest == kana.schedule.due
        assert await repo.next_due_after(NOW + timedelta(days=30)) is None

    run_with_database(tmp_path, scenario)


def test_card_states_and_new_cards_introduced(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        repo = ProgressRepository(db)
        await _review(repo, KANA, Grade.GOOD, NOW)
        await _review(repo, VOCAB, Grade.EASY, NOW)
        await _review(repo, VOCAB, Grade.GOOD, NOW + timedelta(days=30))  # not a new card
        states = await repo.card_states()
        assert set(states) == {KANA, VOCAB}
        assert states[VOCAB] is SchedState.REVIEW
        today = (NOW - timedelta(hours=8), NOW + timedelta(hours=16))
        assert await repo.new_cards_introduced(*today) == {ItemType.KANA: 1, ItemType.VOCAB: 1}
        tomorrow = (today[1], today[1] + timedelta(days=1))
        assert await repo.new_cards_introduced(*tomorrow) == {}

    run_with_database(tmp_path, scenario)


def test_reviews_between_treats_the_end_as_exclusive(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        repo = ProgressRepository(db)
        await _review(repo, KANA, Grade.GOOD, NOW)
        assert len(await repo.reviews_between(NOW, NOW + timedelta(seconds=1))) == 1
        assert await repo.reviews_between(NOW - timedelta(seconds=1), NOW) == []

    run_with_database(tmp_path, scenario)


def test_settings_are_upserted(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        repo = ProgressRepository(db)
        assert await repo.get_setting("k") is None
        await repo.set_setting("k", "one")
        await repo.set_setting("k", "two")
        assert await repo.get_setting("k") == "two"

    run_with_database(tmp_path, scenario)
