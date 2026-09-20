"""Review routes: fetch the next card and answer it."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from bunsho.api.deps import ServicesDep, require_user
from bunsho.api.responses import CONFLICT, NOT_FOUND, UNAUTHORIZED, UNAVAILABLE
from bunsho.api.schemas import AnswerRequest
from bunsho.models.review import CardKey
from bunsho.models.review_session import NextCard, ReviewCounts

router = APIRouter(
    prefix="/reviews",
    tags=["reviews"],
    dependencies=[Depends(require_user)],
    responses={**UNAUTHORIZED, **UNAVAILABLE},
)


@router.get("/next", response_model=NextCard, operation_id="getNextReview")
async def next_review(services: ServicesDep) -> NextCard:
    """The next card to study, or none (with the time the next one comes due).

    Fetching a card creates nothing: an unanswered new card is offered again next time.

    Raises:
        ContentNotReadyError: Mapped to 503 by the app.
    """
    return await services.reviews.next_card()


@router.post(
    "/answer",
    response_model=ReviewCounts,
    operation_id="answerReview",
    responses={**NOT_FOUND, **CONFLICT},
)
async def answer_review(body: AnswerRequest, services: ServicesDep) -> ReviewCounts:
    """Grade a card. Returns the counts of what is left.

    Raises:
        UnknownItemError: Mapped to 404 by the app.
        StaleReviewError: Mapped to 409 by the app.
        ContentNotReadyError: Mapped to 503 by the app.
    """
    return await services.reviews.answer(
        CardKey(body.item_id, body.direction),
        body.grade,
        expected_last_review=body.expected_last_review,
        duration_ms=body.duration_ms,
    )
