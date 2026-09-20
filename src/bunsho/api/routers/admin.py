"""Administrative routes: environment check and content builds."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status

from bunsho.api.deps import ServicesDep, require_user
from bunsho.api.schemas import (
    BuildRequest,
    BuildStatusResponse,
    ConfigCheckResponse,
    build_status,
    config_check_response,
)
from bunsho.orchestration.build_tasks import BuildAlreadyRunningError
from bunsho.services.config_check import run_config_checks

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_user)])


@router.get("/config-check", response_model=ConfigCheckResponse)
async def config_check(services: ServicesDep) -> ConfigCheckResponse:
    """Check that the deck, data directory and dictionary are usable."""
    results = await asyncio.to_thread(run_config_checks, services.config, services.ctx)
    return config_check_response(results)


@router.post(
    "/content/build", response_model=BuildStatusResponse, status_code=status.HTTP_202_ACCEPTED
)
async def start_build(body: BuildRequest, services: ServicesDep) -> BuildStatusResponse:
    """Start a content build in the background.

    Raises:
        HTTPException: 409 when another build is already running.
    """
    try:
        task = services.tasks.start(dry_run=body.dry_run)
    except BuildAlreadyRunningError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return build_status(task)


@router.get("/content/build", response_model=BuildStatusResponse)
async def latest_build(services: ServicesDep) -> BuildStatusResponse:
    """The most recent build.

    Raises:
        HTTPException: 404 when no build has run yet.
    """
    task = services.tasks.latest()
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no build has run yet")
    return build_status(task)


@router.get("/content/build/{task_id}", response_model=BuildStatusResponse)
async def get_build(task_id: str, services: ServicesDep) -> BuildStatusResponse:
    """A build by id (only recent builds are remembered).

    Raises:
        HTTPException: 404 when the build is unknown.
    """
    task = services.tasks.get(task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown build")
    return build_status(task)
