"""The API's OpenAPI document as the frontend's committed type source.

``frontend/openapi.json`` is generated from the app itself, so the TypeScript client can never
describe an API that does not exist. ``scripts/export_openapi.py`` writes the file; a unit test
fails when the committed copy is stale.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from bunsho.api.app import create_app
from bunsho.config.service import AuthSettings, ServerSettings, ServiceConfig
from bunsho.config.settings import DEFAULT_DECK_FILENAME, DEFAULT_DECK_SHA256, AppConfig

# Never used: the lifespan does not run, so nothing ever logs in.
_PLACEHOLDER_HASH = "$argon2id$placeholder"


def _placeholder_config(root: Path) -> ServiceConfig:
    """A configuration that only has to satisfy the constructors: the lifespan never runs."""
    return ServiceConfig(
        app=AppConfig(
            data_dir=root / "data",
            resources_dir=root / "resources",
            deck_filename=DEFAULT_DECK_FILENAME,
            deck_sha256=DEFAULT_DECK_SHA256,
            jamdict_db=None,
            log_level="INFO",
        ),
        server=ServerSettings(host="127.0.0.1", port=8192, cors_origins=()),
        auth=AuthSettings(
            username="openapi",
            password_hash=_PLACEHOLDER_HASH,
            jwt_secret="x" * 32,
            access_ttl_minutes=15,
            refresh_ttl_days=30,
        ),
    )


def openapi_document() -> dict[str, Any]:
    """Build the app (without starting it) and return its OpenAPI document."""
    with tempfile.TemporaryDirectory() as tmp:
        return create_app(_placeholder_config(Path(tmp))).openapi()


def render_openapi_snapshot() -> str:
    """The document as stable text: sorted keys, two-space indent, UTF-8, trailing newline."""
    return json.dumps(openapi_document(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
