"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bunsho import APP_NAME, __version__
from bunsho.api import API_PREFIX
from bunsho.api.routers import admin, auth, content, health
from bunsho.api.services import ServiceOverrides, build_services
from bunsho.config.service import ServiceConfig
from bunsho.logging_setup import configure_logging


def create_app(config: ServiceConfig, *, overrides: ServiceOverrides | None = None) -> FastAPI:
    """Build the FastAPI app.

    The lifespan migrates ``progress.db`` and wires the services; a failure there
    aborts startup.

    Args:
        config: Validated service configuration.
        overrides: Optional test seams.

    Returns:
        The application (routers are mounted under ``/api/v1``).
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(config.app.log_level, force=False)
        services = await build_services(config, overrides)
        app.state.services = services
        try:
            yield
        finally:
            await services.aclose()

    app = FastAPI(title=APP_NAME, version=__version__, lifespan=lifespan)
    if config.server.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(config.server.cors_origins),
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
        )
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(admin.router, prefix=API_PREFIX)
    app.include_router(content.router, prefix=API_PREFIX)
    return app
