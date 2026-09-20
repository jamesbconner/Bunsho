from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bunsho.config.normalizer import ConfigError
from bunsho.main import build_service_config, create_app_from_env
from tests.base import JWT_SECRET, make_auth_settings


def _env(tmp_path: Path, **extra: str) -> dict[str, str]:
    env = {
        "BUNSHO_AUTH__USERNAME": "james",
        "BUNSHO_AUTH__PASSWORD_HASH": make_auth_settings().password_hash,
        "BUNSHO_AUTH__JWT_SECRET": JWT_SECRET,
        "BUNSHO_PATHS__DATA_DIR": str(tmp_path / "data"),
    }
    env.update(extra)
    return env


def test_valid_environment_builds_a_config(tmp_path: Path) -> None:
    config = build_service_config(_env(tmp_path, BUNSHO_SERVER__PORT="9191"))
    assert config.server.port == 9191
    assert config.auth.username == "james"
    assert config.app.data_dir == tmp_path / "data"


def test_missing_settings_report_every_problem(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as info:
        build_service_config({"BUNSHO_PATHS__DATA_DIR": str(tmp_path)})
    message = str(info.value)
    for key in ("username", "password_hash", "jwt_secret"):
        assert key in message


def test_the_reserved_port_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="8000"):
        build_service_config(_env(tmp_path, BUNSHO_SERVER__PORT="8000"))


def test_the_default_port_is_8192(tmp_path: Path) -> None:
    assert build_service_config(_env(tmp_path)).server.port == 8192


def test_config_file_and_env_file_are_layered(tmp_path: Path) -> None:
    toml = tmp_path / "bunsho.toml"
    toml.write_text('[server]\nport = 9100\nhost = "0.0.0.0"\n')
    dotenv = tmp_path / ".env.test"
    dotenv.write_text("BUNSHO_SERVER__PORT=9200\n")
    env = _env(
        tmp_path,
        BUNSHO_CONFIG_FILE=str(toml),
        BUNSHO_ENV_FILE=str(dotenv),
        BUNSHO_SERVER__HOST="127.0.0.1",
    )
    config = build_service_config(env)
    assert config.server.port == 9200  # .env beats the TOML file
    assert config.server.host == "127.0.0.1"  # the environment beats both


def test_default_env_file_is_read_from_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("BUNSHO_SERVER__PORT=9300\n")
    assert build_service_config(_env(tmp_path)).server.port == 9300


def test_create_app_from_env_serves_health(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    for key, value in _env(tmp_path).items():
        monkeypatch.setenv(key, value)
    with TestClient(create_app_from_env()) as client:
        assert client.get("/api/v1/health").status_code == 200
