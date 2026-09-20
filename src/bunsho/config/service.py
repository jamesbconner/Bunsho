"""Service-level configuration: HTTP server and authentication."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

from bunsho.config.normalizer import ConfigError, ConfigNormalizer
from bunsho.config.settings import AppConfig, validate_config

MIN_JWT_SECRET_LENGTH = 32
RESERVED_PORT = 8000
_ARGON2_PREFIX = "$argon2"


@dataclass(frozen=True, slots=True)
class ServerSettings:
    """HTTP server settings."""

    host: str
    port: int
    cors_origins: tuple[str, ...]
    trusted_proxies: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AuthSettings:
    """Single-user authentication settings."""

    username: str
    password_hash: str
    jwt_secret: str
    access_ttl_minutes: int
    refresh_ttl_days: int


@dataclass(frozen=True, slots=True)
class ServiceConfig:
    """Everything the API service needs: library config plus server and auth."""

    app: AppConfig
    server: ServerSettings
    auth: AuthSettings


def _int(cfg: ConfigNormalizer, section: str, key: str, fallback: int, errors: list[str]) -> int:
    try:
        return cfg.get_int(section, key, fallback)
    except ConfigError as exc:
        errors.append(str(exc))
        return fallback


def _origins(cfg: ConfigNormalizer) -> tuple[str, ...]:
    raw = cfg.get_string("server", "cors_origins")
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _trusted_proxies(cfg: ConfigNormalizer) -> tuple[str, ...]:
    raw = cfg.get_string("server", "trusted_proxies")
    return tuple(part.strip() for part in raw.split(",") if part.strip())


_WILDCARD_HINT = "a wildcard would let any client choose its own login-throttle bucket"


def _trusted_proxy_problem(entry: str) -> str | None:
    """Describe what is wrong with a trusted-proxy entry, or return ``None`` if it is fine.

    Validation is strict, like uvicorn's own parsing: an entry uvicorn would silently treat
    as a literal string (for example one with host bits set) is rejected here instead.
    """
    try:
        network = ipaddress.ip_network(entry, strict=True)
    except ValueError:
        try:
            ipaddress.ip_network(entry, strict=False)
        except ValueError:
            reason = "is not an IP address or network"
            return f"{reason} ({_WILDCARD_HINT})" if entry == "*" else reason
        return "has host bits set; write the network address (for example 127.0.0.0/8)"
    if network.prefixlen == 0:
        return f"matches every address ({_WILDCARD_HINT})"
    return None


def validate_service_config(cfg: ConfigNormalizer) -> list[str]:
    """Validate library, server and auth settings; return every problem found."""
    errors = validate_config(cfg)
    if not cfg.get_string("server", "host", "127.0.0.1").strip():
        errors.append("[server] host must not be empty")
    port = _int(cfg, "server", "port", 8192, errors)
    if port == RESERVED_PORT or not 1024 <= port <= 65535:
        errors.append(
            f"[server] port={port} must be between 1024 and 65535 and not {RESERVED_PORT}"
        )
    for origin in _origins(cfg):
        if not origin.startswith(("http://", "https://")):
            errors.append(
                f"[server] cors_origins entry {origin!r} must start with http:// or https://"
            )
    for proxy in _trusted_proxies(cfg):
        if problem := _trusted_proxy_problem(proxy):
            errors.append(f"[server] trusted_proxies entry {proxy!r} {problem}")
    if not cfg.get_string("auth", "username").strip():
        errors.append("[auth] username is required")
    if not cfg.get_string("auth", "password_hash").startswith(_ARGON2_PREFIX):
        errors.append("[auth] password_hash is required and must be an argon2 hash")
    if len(cfg.get_string("auth", "jwt_secret")) < MIN_JWT_SECRET_LENGTH:
        errors.append(
            f"[auth] jwt_secret is required and must be at least {MIN_JWT_SECRET_LENGTH} characters"
        )
    access = _int(cfg, "auth", "access_ttl_minutes", 15, errors)
    if not 1 <= access <= 1440:
        errors.append(f"[auth] access_ttl_minutes={access} must be between 1 and 1440")
    refresh = _int(cfg, "auth", "refresh_ttl_days", 30, errors)
    if not 1 <= refresh <= 365:
        errors.append(f"[auth] refresh_ttl_days={refresh} must be between 1 and 365")
    return errors


def load_service_config(cfg: ConfigNormalizer) -> ServiceConfig:
    """Validate ``cfg`` and build a ``ServiceConfig``.

    Raises:
        ConfigError: Listing every validation failure at once.
    """
    errors = validate_service_config(cfg)
    if errors:
        raise ConfigError("Invalid configuration:\n  - " + "\n  - ".join(errors))
    return ServiceConfig(
        app=AppConfig.from_normalizer(cfg),
        server=ServerSettings(
            host=cfg.get_string("server", "host", "127.0.0.1").strip(),
            port=cfg.get_int("server", "port", 8192),
            cors_origins=_origins(cfg),
            trusted_proxies=_trusted_proxies(cfg),
        ),
        auth=AuthSettings(
            username=cfg.get_string("auth", "username").strip(),
            password_hash=cfg.get_string("auth", "password_hash"),
            jwt_secret=cfg.get_string("auth", "jwt_secret"),
            access_ttl_minutes=cfg.get_int("auth", "access_ttl_minutes", 15),
            refresh_ttl_days=cfg.get_int("auth", "refresh_ttl_days", 30),
        ),
    )
