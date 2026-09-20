"""Load layered configuration: TOML file < ``.env`` file < real environment."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from bunsho.config.normalizer import ConfigError, ConfigNormalizer


def load_config(
    *,
    config_file: Path | None = None,
    env_file: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> ConfigNormalizer:
    """Build a normalized configuration from all sources.

    Args:
        config_file: Optional TOML file with the lowest precedence.
        env_file: Optional ``.env`` file; overrides the TOML file.
        environ: Environment mapping (defaults to ``os.environ``); highest precedence.

    Returns:
        The merged configuration. ``os.environ`` is never mutated.

    Raises:
        ConfigError: ``config_file`` or ``env_file`` does not exist, or ``config_file`` is
            not valid TOML.
    """
    file_values: dict[str, Any] = {}
    if config_file is not None:
        try:
            with config_file.open("rb") as handle:
                file_values = tomllib.load(handle)
        except FileNotFoundError as exc:
            raise ConfigError(f"config file not found: {config_file}") from exc
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"config file {config_file} is not valid TOML: {exc}") from exc
    merged_env: dict[str, str] = {}
    if env_file is not None:
        if not env_file.is_file():
            raise ConfigError(f"env file not found: {env_file}")
        merged_env.update({k: v for k, v in dotenv_values(env_file).items() if v is not None})
    merged_env.update(os.environ if environ is None else environ)
    return ConfigNormalizer(file_values).merge_env(merged_env)
