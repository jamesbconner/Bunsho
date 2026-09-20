import dataclasses
import json
import socket
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient

from bunsho.api.app import create_app
from bunsho.config.normalizer import ConfigError
from bunsho.main import build_server_config, build_service_config, create_app_from_env
from tests.base import JWT_SECRET, PASSWORD, make_auth_settings, make_service_config


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


def test_the_launcher_does_not_trust_proxy_headers(tmp_path: Path) -> None:
    config = make_service_config(tmp_path)
    server_config = build_server_config(create_app(config), config)
    assert server_config.proxy_headers is False
    assert (server_config.host, server_config.port) == (config.server.host, config.server.port)
    assert server_config.log_config is None


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def live_server(tmp_path: Path) -> Iterator[int]:
    """Serve the app on a free port exactly as the launcher configures uvicorn."""
    base = make_service_config(tmp_path)
    port = _free_port()
    config = dataclasses.replace(base, server=dataclasses.replace(base.server, port=port))
    server = uvicorn.Server(build_server_config(create_app(config), config))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        assert thread.is_alive(), "server thread died during startup"
        assert time.monotonic() < deadline, "server did not start"
        time.sleep(0.02)
    try:
        yield port
    finally:
        server.should_exit = True
        thread.join(timeout=15)


def _login_status(port: int, forwarded_for: str) -> int:
    request = urllib.request.Request(  # noqa: S310 - fixed http://127.0.0.1 URL
        f"http://127.0.0.1:{port}/api/v1/auth/login",
        data=json.dumps({"username": "james", "password": PASSWORD + "-wrong"}).encode(),
        headers={"Content-Type": "application/json", "X-Forwarded-For": forwarded_for},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return exc.code


def test_a_forged_forwarded_for_header_cannot_dodge_the_login_throttle(live_server: int) -> None:
    statuses = [_login_status(live_server, f"203.0.113.{n}") for n in range(1, 9)]
    assert statuses[:5] == [401] * 5
    assert 429 in statuses[5:]
