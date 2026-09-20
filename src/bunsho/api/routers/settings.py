"""Review settings routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from bunsho.api.deps import ServicesDep, require_user
from bunsho.api.responses import UNAUTHORIZED
from bunsho.models.review_settings import ReviewSettings

router = APIRouter(
    prefix="/settings",
    tags=["settings"],
    dependencies=[Depends(require_user)],
    responses=UNAUTHORIZED,
)


@router.get("", response_model=ReviewSettings, operation_id="getSettings")
async def get_settings(services: ServicesDep) -> ReviewSettings:
    """The current review settings (defaults until they are first saved)."""
    return await services.review_settings.load()


@router.put("", response_model=ReviewSettings, operation_id="updateSettings")
async def update_settings(body: ReviewSettings, services: ServicesDep) -> ReviewSettings:
    """Replace the review settings. All fields are validated together; nothing is saved on error.

    Omitted fields take their defaults (this is a full replacement, not a patch).
    """
    return await services.review_settings.save(body)
