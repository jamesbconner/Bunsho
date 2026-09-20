"""Case-insensitive configuration wrapper with typed accessors."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

ENV_PREFIX = "BUNSHO_"
_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})


class ConfigError(ValueError):
    """Raised when configuration is missing, malformed or invalid."""


class ConfigNormalizer:
    """Holds ``{section: {key: value}}`` with lowercase section and key names."""

    def __init__(self, raw: Mapping[str, Mapping[str, Any]] | None = None) -> None:
        """Normalize ``raw`` so lookups are case-insensitive.

        Args:
            raw: Nested mapping such as parsed TOML. Names may use any case.
        """
        self._data: dict[str, dict[str, Any]] = {}
        for section, values in (raw or {}).items():
            if not isinstance(values, Mapping):
                raise ConfigError(f"top-level key {section!r} must be a table, not {values!r}")
            bucket = self._data.setdefault(section.lower(), {})
            for key, value in values.items():
                bucket[key.lower()] = value

    def has_option(self, section: str, key: str) -> bool:
        """Return whether ``[section] key`` is present."""
        return key.lower() in self._data.get(section.lower(), {})

    def _lookup(self, section: str, key: str) -> Any | None:
        return self._data.get(section.lower(), {}).get(key.lower())

    def get_string(self, section: str, key: str, fallback: str = "") -> str:
        """Return the value as a string, or ``fallback`` when absent."""
        value = self._lookup(section, key)
        return fallback if value is None else str(value)

    def get_int(self, section: str, key: str, fallback: int = 0) -> int:
        """Return the value as an int.

        Raises:
            ConfigError: If the value cannot be parsed as an integer.
        """
        value = self._lookup(section, key)
        if value is None:
            return fallback
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"[{section}] {key}={value!r} is not a valid integer") from exc

    def get_float(self, section: str, key: str, fallback: float = 0.0) -> float:
        """Return the value as a float.

        Raises:
            ConfigError: If the value cannot be parsed as a float.
        """
        value = self._lookup(section, key)
        if value is None:
            return fallback
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"[{section}] {key}={value!r} is not a valid float") from exc

    def get_bool(self, section: str, key: str, fallback: bool = False) -> bool:
        """Return the value as a bool (true/false, yes/no, on/off, 1/0).

        Raises:
            ConfigError: If the value is not a recognized boolean spelling.
        """
        value = self._lookup(section, key)
        if value is None:
            return fallback
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
        raise ConfigError(f"[{section}] {key}={value!r} is not a valid boolean")

    def merge_env(self, environ: Mapping[str, str]) -> ConfigNormalizer:
        """Return a copy with ``BUNSHO_<SECTION>__<KEY>`` variables applied on top.

        Args:
            environ: Environment-style mapping. Unrelated or malformed names are ignored.

        Returns:
            A new normalizer; ``self`` is not modified.
        """
        merged = ConfigNormalizer(self._data)
        for name, value in environ.items():
            upper = name.upper()
            if not upper.startswith(ENV_PREFIX):
                continue
            section, sep, key = upper[len(ENV_PREFIX) :].partition("__")
            if not sep or not section or not key:
                continue
            merged._data.setdefault(section.lower(), {})[key.lower()] = value
        return merged
