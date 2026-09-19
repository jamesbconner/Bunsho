"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from bunsho import APP_NAME, __version__
from bunsho.api import API_PREFIX
from bunsho.api.routers import admin, auth, content, health, ws
from bunsho.api.services import ServiceOverrides, build_services
from bunsho.config.service import ServiceConfig
from bunsho.logging_setup import configure_logging


async def _validation_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Answer 422 with ``loc``/``msg``/``type`` only.

    FastAPI's default body echoes the submitted ``input`` (a login password, for one)
    and ``ctx``; neither belongs in a response.
    """
    errors = cast(RequestValidationError, exc).errors()  # registered for this type only
    detail = [
        {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]} for error in errors
    ]
    return JSONResponse(status_code=422, content={"detail": detail})


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
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(admin.router, prefix=API_PREFIX)
    app.include_router(content.router, prefix=API_PREFIX)
    app.include_router(ws.router, prefix=API_PREFIX)
    return app
