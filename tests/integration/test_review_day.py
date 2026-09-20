from datetime import timedelta
from pathlib import Path

import pytest

from bunsho.db.engine import ProgressDatabase
from bunsho.models.review import CardKey, Grade, ItemType
from bunsho.models.review_settings import ReviewSettings
from bunsho.orchestration.content_build import BuildReport
from bunsho.services.content_repository import ContentRepository
from tests.base import run_with_database
from tests.review_stack import START, stack_for_repository


@pytest.mark.integration
def test_a_study_day_on_the_real_content(
    tmp_path: Path, real_content: tuple[BuildReport, ContentRepository]
) -> None:
    _, repo = real_content
    limits = ReviewSettings().new_limits

    async def scenario(db: ProgressDatabase) -> None:
        stack = stack_for_repository(tmp_path, db, repo)
        orchestrator = stack.orchestrator
        introduced: dict[ItemType, int] = {}
        seen: set[CardKey] = set()
        while (card := (await orchestrator.next_card()).card) is not None:
            key = CardKey(card.item_id, card.direction)
            assert card.is_new, "nothing is due within a single study day after Easy answers"
            assert key not in seen, "a new card must never be offered twice"
            seen.add(key)
            introduced[card.item_type] = introduced.get(card.item_type, 0) + 1
            await orchestrator.answer(
                key, Grade.EASY, expected_last_review=card.expected_last_review
            )

        assert introduced == {
            ItemType.KANA: limits.kana,
            ItemType.KANJI: limits.kanji,
            ItemType.VOCAB: limits.vocab,
        }
        finished = await orchestrator.next_card()
        assert finished.card is None
        assert finished.counts.new_remaining.kana == 0
        assert finished.counts.new_remaining.kanji == 0
        assert finished.counts.new_remaining.vocab == 0
        assert finished.next_due_at is not None
        assert finished.next_due_at >= START + timedelta(days=1)  # Easy graduates to Review

        stack.clock.advance(days=1)  # the next study day: the allowance is back
        tomorrow = await orchestrator.next_card()
        assert tomorrow.card is not None
        assert tomorrow.card.is_new
        assert tomorrow.counts.new_remaining.kana == limits.kana
        assert tomorrow.counts.new_remaining.kanji == limits.kanji
        assert tomorrow.counts.new_remaining.vocab == limits.vocab

        summary = await stack.stats.summary()
        assert summary.reviewed_today == 0
        assert sum(day.reviews for day in summary.daily_reviews) == len(seen)

    run_with_database(tmp_path, scenario)
