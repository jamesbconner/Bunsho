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


@pytest.mark.parametrize("value", ["127.0.0.1", "10.0.0.0/8", "127.0.0.1, 172.16.0.0/12", "::1"])
def test_trusted_proxies_accept_addresses_and_networks(value: str) -> None:
    config = load_service_config(_valid(server={"trusted_proxies": value}))
    assert config.server.trusted_proxies == tuple(part.strip() for part in value.split(","))


def test_trusted_proxies_default_to_empty() -> None:
    assert load_service_config(_valid()).server.trusted_proxies == ()


@pytest.mark.parametrize("value", ["*", "not-an-ip", "10.0.0.0/33", "127.0.0.1, *"])
def test_trusted_proxies_reject_wildcards_and_garbage(value: str) -> None:
    errors = validate_service_config(_valid(server={"trusted_proxies": value}))
    assert any("trusted_proxies" in error for error in errors)


@pytest.mark.parametrize("value", ["fd00::/8", "::1", "127.0.0.1", "127.0.0.0/8", "172.16.0.0/12"])
def test_trusted_proxies_accept_ipv6_and_broad_but_bounded_networks(value: str) -> None:
    assert load_service_config(
        _valid(server={"trusted_proxies": value})
    ).server.trusted_proxies == (value,)


@pytest.mark.parametrize("value", ["0.0.0.0/0", "::/0", "10.0.0.0/8, 0.0.0.0/0"])
def test_trusted_proxies_reject_match_everything_networks(value: str) -> None:
    errors = [
        e
        for e in validate_service_config(_valid(server={"trusted_proxies": value}))
        if "trusted_proxies" in e
    ]
    assert len(errors) == 1
    assert "wildcard" in errors[0]


def test_trusted_proxies_reject_host_bits_the_way_uvicorn_would() -> None:
    errors = validate_service_config(_valid(server={"trusted_proxies": "127.0.0.5/8"}))
    [error] = [e for e in errors if "trusted_proxies" in e]
    assert "host bits" in error
    assert "wildcard" not in error


@pytest.mark.parametrize("value", ["*", "0.0.0.0/0"])
def test_wildcard_hint_appears_for_wildcards(value: str) -> None:
    [error] = validate_service_config(_valid(server={"trusted_proxies": value}))
    assert "login-throttle bucket" in error


def test_wildcard_hint_is_absent_for_other_bad_entries() -> None:
    [error] = validate_service_config(_valid(server={"trusted_proxies": "bogus"}))
    assert "bogus" in error
    assert "wildcard" not in error


def test_csp_report_only_defaults_to_false() -> None:
    assert load_service_config(_valid()).server.csp_report_only is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("true", True), ("yes", True), ("on", True), ("1", True), ("false", False), ("off", False)],
)
def test_csp_report_only_reads_the_usual_boolean_spellings(raw: str, expected: bool) -> None:
    config = load_service_config(_valid(server={"csp_report_only": raw}))
    assert config.server.csp_report_only is expected


def test_csp_report_only_is_read_from_the_environment() -> None:
    from bunsho.config.loader import load_config

    cfg = load_config(
        environ={
            "BUNSHO_AUTH__USERNAME": "james",
            "BUNSHO_AUTH__PASSWORD_HASH": VALID_HASH,
            "BUNSHO_AUTH__JWT_SECRET": SECRET,
            "BUNSHO_SERVER__CSP_REPORT_ONLY": "true",
        }
    )
    assert load_service_config(cfg).server.csp_report_only is True


def test_a_bad_csp_report_only_is_reported_with_the_other_errors() -> None:
    errors = validate_service_config(_valid(server={"csp_report_only": "maybe", "port": "80"}))
    assert any("csp_report_only" in e for e in errors)
    assert any("port" in e for e in errors)  # reported together, not one at a time
    with pytest.raises(ConfigError, match="csp_report_only"):
        load_service_config(_valid(server={"csp_report_only": "maybe"}))
