import pytest

from bunsho.config.normalizer import ConfigError, ConfigNormalizer
from bunsho.config.service import (
    MIN_JWT_SECRET_LENGTH,
    load_service_config,
    validate_service_config,
)

VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$aGFzaGhhc2hoYXNo"
SECRET = "x" * MIN_JWT_SECRET_LENGTH


def _valid(**overrides: dict[str, str]) -> ConfigNormalizer:
    raw: dict[str, dict[str, str]] = {
        "auth": {"username": "james", "password_hash": VALID_HASH, "jwt_secret": SECRET},
    }
    for section, values in overrides.items():
        raw.setdefault(section, {}).update(values)
    return ConfigNormalizer(raw)


def test_valid_config_loads_with_defaults() -> None:
    config = load_service_config(_valid())
    assert config.server.host == "127.0.0.1"
    assert config.server.port == 8192
    assert config.server.cors_origins == ()
    assert config.auth.username == "james"
    assert config.auth.access_ttl_minutes == 15
    assert config.auth.refresh_ttl_days == 30
    assert config.app.log_level == "INFO"


def test_auth_secrets_are_required() -> None:
    errors = validate_service_config(ConfigNormalizer())
    assert any("auth" in e and "username" in e for e in errors)
    assert any("password_hash" in e for e in errors)
    assert any("jwt_secret" in e for e in errors)


def test_all_errors_are_reported_together() -> None:
    cfg = ConfigNormalizer(
        {
            "logging": {"level": "loud"},
            "server": {"port": "8000", "host": "", "cors_origins": "*, ftp://x"},
            "auth": {
                "username": "",
                "password_hash": "plain",
                "jwt_secret": "short",
                "access_ttl_minutes": "0",
                "refresh_ttl_days": "9999",
            },
        }
    )
    errors = validate_service_config(cfg)
    assert len(errors) >= 9
    with pytest.raises(ConfigError) as info:
        load_service_config(cfg)
    assert str(info.value).count("\n  - ") == len(errors)


@pytest.mark.parametrize("port", ["8000", "80", "70000", "abc"])
def test_bad_ports_are_rejected(port: str) -> None:
    assert any("port" in e for e in validate_service_config(_valid(server={"port": port})))


def test_cors_origins_are_parsed_and_must_be_explicit() -> None:
    ok = load_service_config(
        _valid(server={"cors_origins": "http://localhost:5173, https://bunsho.example"})
    )
    assert ok.server.cors_origins == ("http://localhost:5173", "https://bunsho.example")
    assert any("cors" in e for e in validate_service_config(_valid(server={"cors_origins": "*"})))


def test_app_config_errors_are_included() -> None:
    cfg = _valid(paths={"deck_sha256": "abc"})
    assert any("deck_sha256" in e for e in validate_service_config(cfg))
