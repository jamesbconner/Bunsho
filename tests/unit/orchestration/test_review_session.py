import logging
from datetime import timedelta
from pathlib import Path

import pytest

from bunsho.db.engine import ProgressDatabase
from bunsho.models.content import JlptLevel
from bunsho.models.review import (
    CardDirection,
    CardKey,
    ContentNotReadyError,
    Grade,
    ItemType,
    SchedState,
    StaleReviewError,
    UnknownItemError,
)
from bunsho.models.review_session import CardView, TypeCounts
from bunsho.models.review_settings import NewCardPolicyName, NewLimits, ReviewSettings
from bunsho.services.fsrs_scheduler import FSRSScheduler
from tests.base import make_kana, make_kanji, make_vocab, run_with_database
from tests.review_stack import LOGGER_NAME, START, ReviewStack, build_review_stack

A = make_vocab("日本", "にほん")
B = make_vocab("学生", "がくせい")
REC, RECALL = CardDirection.RECOGNITION, CardDirection.RECALL


def key_of(card: CardView) -> CardKey:
    return CardKey(card.item_id, card.direction)


async def answer(stack: ReviewStack, card: CardView, grade: Grade = Grade.GOOD) -> None:
    await stack.orchestrator.answer(
        key_of(card), grade, expected_last_review=card.expected_last_review
    )


async def next_card(stack: ReviewStack) -> CardView:
    card = (await stack.orchestrator.next_card()).card
    assert card is not None
    return card


def test_the_first_new_card_is_the_first_vocab_recognition(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A, B])
        result = await stack.orchestrator.next_card()
        card = result.card
        assert card is not None
        assert (card.item_type, card.direction) == (ItemType.VOCAB, REC)
        assert card.is_new is True
        assert card.state is SchedState.NEW
        assert card.expected_last_review is None
        assert card.vocab is not None
        assert card.vocab.id == A.id
        assert card.kana is None
        assert card.kanji is None
        intervals = card.intervals
        assert intervals.again <= intervals.hard <= intervals.good <= intervals.easy
        assert result.counts.new_remaining == TypeCounts(kana=0, kanji=0, vocab=4)
        assert result.counts.due == TypeCounts()
        assert result.next_due_at is None

    run_with_database(tmp_path, scenario)


def test_next_is_stable_until_the_card_is_answered(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A, B])
        first = await next_card(stack)
        again = await next_card(stack)
        assert key_of(first) == key_of(again)
        assert await stack.progress.get_card(key_of(first)) is None  # next created nothing

    run_with_database(tmp_path, scenario)


def test_answering_a_new_card_advances_to_its_sibling_direction(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A, B])
        first = await next_card(stack)
        counts = await stack.orchestrator.answer(
            key_of(first), Grade.GOOD, expected_last_review=None
        )
        assert counts.new_remaining.vocab == 3
        assert counts.due.vocab == 0  # the learning step is minutes away
        second = await next_card(stack)
        assert (second.item_id, second.direction) == (A.id, RECALL)

    run_with_database(tmp_path, scenario)


def test_a_due_card_comes_before_new_cards(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A, B])
        first = await next_card(stack)
        await answer(stack, first)
        stack.clock.advance(minutes=11)
        result = await stack.orchestrator.next_card()
        card = result.card
        assert card is not None
        assert (card.item_id, card.direction) == (A.id, REC)
        assert card.is_new is False
        assert card.state is SchedState.LEARNING
        assert card.expected_last_review == START
        assert result.counts.due.vocab == 1

    run_with_database(tmp_path, scenario)


def test_reaching_the_daily_limit_leaves_only_scheduled_cards(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A, B])
        await stack.settings.save(ReviewSettings(new_limits=NewLimits(vocab=1)))
        await answer(stack, await next_card(stack))
        result = await stack.orchestrator.next_card()
        assert result.card is None
        assert result.counts.new_remaining.vocab == 0
        assert result.next_due_at is not None
        assert START < result.next_due_at <= START + timedelta(hours=1)

    run_with_database(tmp_path, scenario)


def test_the_limit_resets_after_the_rollover_hour(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A, B])
        await stack.settings.save(ReviewSettings(new_limits=NewLimits(vocab=1)))
        await answer(stack, await next_card(stack))
        assert (await stack.orchestrator.next_card()).counts.new_remaining.vocab == 0
        stack.clock.advance(hours=23)  # 11:00 the next day, after the 04:00 rollover
        assert (await stack.orchestrator.next_card()).counts.new_remaining.vocab == 1

    run_with_database(tmp_path, scenario)


def test_a_limit_of_zero_means_unlimited(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A, B])
        await stack.settings.save(ReviewSettings(new_limits=NewLimits(vocab=0)))
        for _ in range(4):
            await answer(stack, await next_card(stack), Grade.EASY)
        assert (await stack.orchestrator.next_card()).card is None  # all 4 cards introduced

    run_with_database(tmp_path, scenario)


def test_new_cards_alternate_between_types_by_remaining_allowance(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(
            tmp_path, db, kana=[make_kana("あ", "a"), make_kana("い", "i")], vocab=[A, B]
        )
        seen: list[ItemType] = []
        for _ in range(3):
            card = await next_card(stack)
            seen.append(card.item_type)
            await answer(stack, card)
        # Both types start at 100% of their allowance; ties go to kana, then the type that has
        # used less of its allowance goes first.
        assert seen == [ItemType.KANA, ItemType.VOCAB, ItemType.KANA]

    run_with_database(tmp_path, scenario)


def test_kanji_are_offered_in_level_order_and_unleveled_kanji_never(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(
            tmp_path,
            db,
            kanji=[
                make_kanji("曜", JlptLevel.N4),
                make_kanji("日", JlptLevel.N5),
                make_kanji("犬", None),
            ],
        )
        result = await stack.orchestrator.next_card()
        card = result.card
        assert card is not None
        assert card.kanji is not None
        assert (card.kanji.char, card.direction) == ("日", CardDirection.KANJI_TO_MEANING)
        assert result.counts.new_remaining.kanji == 6  # 2 leveled kanji x 3 directions

    run_with_database(tmp_path, scenario)


def test_the_active_policy_comes_from_the_settings(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        n4_word = make_vocab("先生", "せんせい", JlptLevel.N4)
        stack = build_review_stack(tmp_path, db, vocab=[A, n4_word])
        await stack.settings.save(
            ReviewSettings(new_card_policy=NewCardPolicyName.PINNED_LEVELS, active_levels=["N4"])
        )
        card = await next_card(stack)
        assert card.vocab is not None
        assert card.vocab.id == n4_word.id

    run_with_database(tmp_path, scenario)


def test_a_stale_answer_is_rejected_and_changes_nothing(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A])
        card = await next_card(stack)
        with pytest.raises(StaleReviewError):
            await stack.orchestrator.answer(key_of(card), Grade.GOOD, expected_last_review=START)
        assert await stack.progress.get_card(key_of(card)) is None
        await answer(stack, card)
        with pytest.raises(StaleReviewError):  # a double submit of the same answer
            await answer(stack, card)

    run_with_database(tmp_path, scenario)


def test_answering_an_unknown_item_is_an_error(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A])
        with pytest.raises(UnknownItemError):
            await stack.orchestrator.answer(
                CardKey("vocab:nope:nope", REC), Grade.GOOD, expected_last_review=None
            )

    run_with_database(tmp_path, scenario)


def test_no_content_means_not_ready(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, built=False)
        with pytest.raises(ContentNotReadyError):
            await stack.orchestrator.next_card()
        with pytest.raises(ContentNotReadyError):
            await stack.orchestrator.answer(
                CardKey(A.id, REC), Grade.GOOD, expected_last_review=None
            )

    run_with_database(tmp_path, scenario)


def test_a_content_schema_mismatch_means_not_ready(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A], schema_version="1")
        with pytest.raises(ContentNotReadyError, match="schema_version"):
            await stack.orchestrator.next_card()

    run_with_database(tmp_path, scenario)


def test_a_due_card_whose_item_disappeared_is_skipped_with_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A])
        scheduler = FSRSScheduler(enable_fuzzing=False)
        orphan = CardKey("vocab:gone:gone", REC)
        before = scheduler.initial(START)
        after = scheduler.schedule(before, Grade.GOOD, START)
        await stack.progress.record_review(
            orphan, before=before, after=after, grade=Grade.GOOD, mode="flip", duration_ms=None
        )
        stack.clock.advance(minutes=11)  # the orphan is now due
        card = await next_card(stack)
        assert card.item_id == A.id
        assert card.is_new is True

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        run_with_database(tmp_path, scenario)
    assert "review_card_orphaned" in caplog.text
