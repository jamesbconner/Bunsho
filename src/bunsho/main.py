"""Process entry points: build the app from the environment and run uvicorn."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from bunsho.api.app import create_app
from bunsho.config.loader import load_config
from bunsho.config.normalizer import ConfigError
from bunsho.config.service import ServiceConfig, load_service_config
from bunsho.logging_setup import configure_logging

CONFIG_FILE_ENV = "BUNSHO_CONFIG_FILE"
ENV_FILE_ENV = "BUNSHO_ENV_FILE"


def build_service_config(environ: Mapping[str, str] | None = None) -> ServiceConfig:
    """Load and validate the service configuration.

    Layers, lowest to highest precedence: the TOML file named by ``BUNSHO_CONFIG_FILE``,
    the ``.env`` file named by ``BUNSHO_ENV_FILE`` (default ``./.env`` when it exists),
    then the environment.

    Args:
        environ: Environment mapping to read (defaults to ``os.environ``).

    Returns:
        The validated service configuration.

    Raises:
        ConfigError: Listing every problem found.
    """
    env = os.environ if environ is None else environ
    config_file = Path(env[CONFIG_FILE_ENV]) if env.get(CONFIG_FILE_ENV) else None
    if env.get(ENV_FILE_ENV):
        env_file: Path | None = Path(env[ENV_FILE_ENV])
    else:
        env_file = Path(".env") if Path(".env").is_file() else None
    return load_service_config(load_config(config_file=config_file, env_file=env_file, environ=env))


def create_app_from_env() -> FastAPI:
    """Application factory for ``uvicorn --factory bunsho.main:create_app_from_env``.

    Returns:
        The FastAPI app configured from the environment.

    Raises:
        ConfigError: If the configuration is invalid.
    """
    return create_app(build_service_config())


def main() -> None:  # pragma: no cover - thin process wrapper, exercised by hand
    """Run the service (the ``bunsho`` console script).

    Exits with status 2 when the configuration is invalid.
    """
    configure_logging("INFO")
    try:
        config = build_service_config()
    except ConfigError as exc:
        logging.getLogger("bunsho").error("configuration_invalid\n%s", exc)
        raise SystemExit(2) from exc
    configure_logging(config.app.log_level)
    uvicorn.run(
        create_app(config), host=config.server.host, port=config.server.port, log_config=None
    )
