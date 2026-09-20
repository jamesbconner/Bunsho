"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from bunsho import APP_NAME, __version__
from bunsho.api import API_PREFIX
from bunsho.api.routers import admin, auth, content, health, reviews, settings, stats, ws
from bunsho.api.schemas import WsAuthMessage, WsEvent, WsReady, WsSnapshot
from bunsho.api.services import ServiceOverrides, build_services
from bunsho.config.service import ServiceConfig
from bunsho.logging_setup import configure_logging
from bunsho.models.review import (
    ContentNotReadyError,
    ReviewError,
    StaleReviewError,
    UnknownItemError,
)


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


_REVIEW_ERROR_STATUS: dict[type[ReviewError], int] = {
    ContentNotReadyError: 503,
    UnknownItemError: 404,
    StaleReviewError: 409,
}


async def _review_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Map review-engine errors to their HTTP status with a string ``detail``."""
    status_code = next(
        (code for kind, code in _REVIEW_ERROR_STATUS.items() if isinstance(exc, kind)), 500
    )
    return JSONResponse(status_code=status_code, content={"detail": str(exc)})


_WS_MESSAGE_MODELS = (WsAuthMessage, WsReady, WsSnapshot, WsEvent)


def _publish_websocket_schemas(app: FastAPI) -> None:
    """Add the WebSocket message models to ``/openapi.json``.

    FastAPI documents only HTTP routes, so without this the typed frontend client could not
    generate types for the messages on ``/ws/tasks``.
    """

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        for model in _WS_MESSAGE_MODELS:
            message = model.model_json_schema(ref_template="#/components/schemas/{model}")
            for name, definition in message.pop("$defs", {}).items():
                components.setdefault(name, definition)
            components[model.__name__] = message
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]


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
            allow_methods=["GET", "POST", "PUT"],
            allow_headers=["Authorization", "Content-Type"],
            expose_headers=["Retry-After"],  # lets browser code read the login throttle's wait
        )
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(ReviewError, _review_error_handler)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(admin.router, prefix=API_PREFIX)
    app.include_router(content.router, prefix=API_PREFIX)
    app.include_router(reviews.router, prefix=API_PREFIX)
    app.include_router(stats.router, prefix=API_PREFIX)
    app.include_router(settings.router, prefix=API_PREFIX)
    app.include_router(ws.router, prefix=API_PREFIX)
    _publish_websocket_schemas(app)
    return app
