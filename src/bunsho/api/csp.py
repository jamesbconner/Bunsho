"""Content-Security-Policy strings, the docs paths and the per-request nonce.

A pure module (no I/O, no framework imports) so the policies are read and tested in one place.
"""

from __future__ import annotations

import base64
import re
import secrets

CSP_HEADER = "Content-Security-Policy"
CSP_REPORT_ONLY_HEADER = "Content-Security-Policy-Report-Only"

NONCE_SCOPE_KEY = "bunsho.csp_nonce"
"""Where the static layer leaves the nonce on the ASGI scope for the security-headers middleware."""

DEFAULT_POLICY = "default-src 'none'; frame-ancestors 'none'"
"""For everything that is not the app shell or a docs page: JSON and hashed assets have no active
content, and this also stops a file such as an SVG from running script if opened as a page."""

DOCS_PATHS = frozenset({"/docs", "/redoc", "/docs/oauth2-redirect"})
"""FastAPI's default documentation URLs; a test fails if the app's real URLs differ."""

DOCS_POLICY = "; ".join(
    [
        "default-src 'none'",
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com",
        "img-src 'self' data: https://fastapi.tiangolo.com",
        "font-src https://fonts.gstatic.com",
        "worker-src blob:",
        "connect-src 'self'",
        "frame-ancestors 'none'",
    ]
)
"""Swagger UI and Redoc load scripts, styles, fonts and a favicon from CDNs and run an inline
bootstrap script, so they cannot work under the shell policy. Confined to ``DOCS_PATHS``."""

_NONCE = re.compile(r"[A-Za-z0-9+/]+={0,2}")


def generate_nonce() -> str:
    """Return a fresh nonce: 16 random bytes, base64 encoded (what the CSP grammar requires).

    Returns:
        A new random nonce value.
    """
    return base64.b64encode(secrets.token_bytes(16)).decode("ascii")


def shell_policy(nonce: str) -> str:
    """Build the strict policy for the app shell with ``nonce`` allowed for styles.

    Args:
        nonce: A base64 nonce, normally from ``generate_nonce``.

    Returns:
        The ``Content-Security-Policy`` header value.

    Raises:
        ValueError: ``nonce`` is not base64 (a value with quotes or semicolons could otherwise
            inject further directives).
    """
    if _NONCE.fullmatch(nonce) is None:
        raise ValueError(f"nonce must be base64, got {nonce!r}")
    return "; ".join(
        [
            "default-src 'none'",
            "script-src 'self'",
            f"style-src 'self' 'nonce-{nonce}'",
            "img-src 'self'",
            "font-src 'self'",
            "connect-src 'self'",
            "base-uri 'none'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
    )


def header_name(report_only: bool) -> str:
    """Return the CSP header name: enforcing, or report-only when ``report_only`` is set."""
    return CSP_REPORT_ONLY_HEADER if report_only else CSP_HEADER
