"""Documented error responses, shared by the routers so the OpenAPI schema stays uniform."""

from __future__ import annotations

from typing import Any

from bunsho.api.schemas import ErrorResponse

Responses = dict[int | str, dict[str, Any]]

UNAUTHORIZED: Responses = {
    401: {"model": ErrorResponse, "description": "Missing, invalid or expired access token."}
}
NOT_FOUND: Responses = {
    404: {"model": ErrorResponse, "description": "The item or task does not exist."}
}
CONFLICT: Responses = {
    409: {
        "model": ErrorResponse,
        "description": "The request conflicts with the current state (for example a stale card).",
    }
}
TOO_MANY_REQUESTS: Responses = {
    429: {
        "model": ErrorResponse,
        "description": "Too many failed logins; wait for the number of seconds in Retry-After.",
    }
}
UNAVAILABLE: Responses = {
    503: {
        "model": ErrorResponse,
        "description": "Content has not been built, or content.db cannot be used.",
    }
}
