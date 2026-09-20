"""``GET /health`` (unauthenticated)."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from bunsho.api.deps import ServicesDep
from bunsho.api.schemas import HealthResponse, health_response

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def get_health(services: ServicesDep, response: Response) -> HealthResponse:
    """Report the health of the service's dependencies (503 when one is in error)."""
    report = await services.health.check()
    if report.status == "error":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return health_response(report)
