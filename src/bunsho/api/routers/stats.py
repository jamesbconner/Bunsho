"""Statistics route."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from bunsho.api.deps import ServicesDep, require_user
from bunsho.api.responses import UNAUTHORIZED, UNAVAILABLE
from bunsho.models.review_session import StatsSummary

router = APIRouter(
    prefix="/stats",
    tags=["stats"],
    dependencies=[Depends(require_user)],
    responses={**UNAUTHORIZED, **UNAVAILABLE},
)


@router.get("/summary", response_model=StatsSummary, operation_id="getStatsSummary")
async def stats_summary(services: ServicesDep) -> StatsSummary:
    """Today's work, 30 days of history, retention and progress per type and level."""
    return await services.stats.summary()
