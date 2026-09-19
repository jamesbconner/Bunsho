"""Load layered configuration: TOML file < ``.env`` file < real environment."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from bunsho.config.normalizer import ConfigNormalizer


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
    """
    file_values: dict[str, Any] = {}
    if config_file is not None:
        with config_file.open("rb") as handle:
            file_values = tomllib.load(handle)
    merged_env: dict[str, str] = {}
    if env_file is not None:
        merged_env.update({k: v for k, v in dotenv_values(env_file).items() if v is not None})
    merged_env.update(os.environ if environ is None else environ)
    return ConfigNormalizer(file_values).merge_env(merged_env)
