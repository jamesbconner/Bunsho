from datetime import date
from pathlib import Path

from bunsho.db.engine import ProgressDatabase
from bunsho.models.content import JlptLevel
from bunsho.models.review import CardKey, Grade, ItemType
from bunsho.models.review_session import CardView, TypeCounts
from tests.base import make_kanji, make_vocab, run_with_database
from tests.review_stack import build_review_stack

A = make_vocab("日本", "にほん")
B = make_vocab("学生", "がくせい")


def test_an_empty_history_has_zero_counts_and_no_retention(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A, B], kanji=[make_kanji("日")])
        summary = await stack.stats.summary()
        assert summary.reviewed_today == 0
        assert summary.introduced_today == TypeCounts()
        assert summary.retention_30d is None
        assert len(summary.daily_reviews) == 30
        assert all(day.reviews == 0 for day in summary.daily_reviews)
        assert summary.daily_reviews[-1].day == date(2026, 9, 20)
        vocab = summary.by_type[ItemType.VOCAB]
        assert (vocab.total, vocab.learning, vocab.review, vocab.relearning) == (4, 0, 0, 0)
        assert summary.by_type[ItemType.KANJI].total == 3
        assert summary.by_type[ItemType.KANA].total == 0

    run_with_database(tmp_path, scenario)


def test_summary_reflects_reviews_over_several_weeks(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A, B])
        orchestrator = stack.orchestrator

        async def grade_next(grade: Grade) -> CardView:
            card = (await orchestrator.next_card()).card
            assert card is not None
            await orchestrator.answer(
                CardKey(card.item_id, card.direction),
                grade,
                expected_last_review=card.expected_last_review,
            )
            return card

        await grade_next(Grade.EASY)  # A recognition -> Review
        await grade_next(Grade.EASY)  # A recall -> Review
        today = await stack.stats.summary()
        assert today.reviewed_today == 2
        assert today.introduced_today == TypeCounts(kana=0, kanji=0, vocab=2)

        stack.clock.advance(days=25)  # both cards are due (an Easy first review is ~16 days)
        first = await grade_next(Grade.GOOD)  # stays in Review
        second = await grade_next(Grade.AGAIN)  # lapses into Relearning
        assert (first.direction.value, second.direction.value) == ("recognition", "recall")

        summary = await stack.stats.summary()
        assert summary.reviewed_today == 2
        by_day = {d.day: d.reviews for d in summary.daily_reviews}
        assert by_day[date(2026, 9, 20)] == 2
        assert by_day[date(2026, 10, 15)] == 2
        assert summary.retention_30d == 0.5  # one of the two Review-state answers was Again
        vocab = summary.by_type[ItemType.VOCAB]
        assert (vocab.total, vocab.review, vocab.relearning) == (4, 1, 1)
        n5 = next(p for p in summary.by_level if p.item_type is ItemType.VOCAB and p.level == "N5")
        assert (n5.total, n5.introduced, n5.review) == (4, 2, 1)

    run_with_database(tmp_path, scenario)


def test_levels_are_listed_for_kanji_and_vocab_but_not_kana(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A], kanji=[make_kanji("日")])
        summary = await stack.stats.summary()
        pairs = {(p.item_type, p.level) for p in summary.by_level}
        assert pairs == {
            (t, lvl.label) for t in (ItemType.KANJI, ItemType.VOCAB) for lvl in JlptLevel
        }

    run_with_database(tmp_path, scenario)
