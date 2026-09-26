import dataclasses
import inspect
import json
import socket
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient

from bunsho.api.app import create_app
from bunsho.api.routers.ws import MAX_AUTH_MESSAGE_CHARS
from bunsho.config.normalizer import ConfigError
from bunsho.config.service import ServiceConfig
from bunsho.main import (
    GRACEFUL_SHUTDOWN_SECONDS,
    WS_MAX_MESSAGE_BYTES,
    build_server_config,
    build_service_config,
    create_app_from_env,
    main,
)
from bunsho.orchestration.build_tasks import BuildTaskManager
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


def test_missing_settings_report_every_problem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # a developer's real ./.env must not supply the missing settings
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
    assert server_config.timeout_graceful_shutdown == GRACEFUL_SHUTDOWN_SECONDS == 35
    assert server_config.ws_max_size == WS_MAX_MESSAGE_BYTES == 65536


def test_the_launcher_trusts_only_the_configured_proxies(tmp_path: Path) -> None:
    base = make_service_config(tmp_path)
    server = dataclasses.replace(base.server, trusted_proxies=("10.0.0.0/8", "::1"))
    config = dataclasses.replace(base, server=server)
    server_config = build_server_config(create_app(config), config)
    assert server_config.proxy_headers is True
    assert server_config.forwarded_allow_ips == "10.0.0.0/8,::1"


def test_the_frame_limit_fits_the_largest_auth_message() -> None:
    """Up to 4 UTF-8 bytes per character, plus 512 bytes for the JSON wrapper."""
    assert MAX_AUTH_MESSAGE_CHARS * 4 + 512 <= WS_MAX_MESSAGE_BYTES


def test_the_shutdown_budget_exceeds_the_build_task_wait() -> None:
    build_wait = inspect.signature(BuildTaskManager.aclose).parameters["timeout"].default
    assert build_wait < GRACEFUL_SHUTDOWN_SECONDS


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


SERVER_THREAD_NAME = "bunsho-live-server"
STARTUP_TIMEOUT_SECONDS = 60.0
"""A normal start takes about 0.1 s, but the Windows CI runner for PR #34 needed more than 15 s
once and the cause is unknown; be generous. A start that fails fast (the thread dies) never waits
this long."""


def _stack_of(thread: threading.Thread) -> str:
    """Where ``thread`` is right now, for a failure message (empty when it has no frame)."""
    frame = sys._current_frames().get(thread.ident) if thread.ident is not None else None
    return "".join(traceback.format_stack(frame)) if frame is not None else "(no frame)"


def _start_server(
    config: ServiceConfig, startup_timeout: float = STARTUP_TIMEOUT_SECONDS
) -> tuple[uvicorn.Server, threading.Thread]:
    """Run the app in uvicorn on a thread and wait until it accepts connections."""
    server = uvicorn.Server(build_server_config(create_app(config), config))
    thread = threading.Thread(target=server.run, daemon=True, name=SERVER_THREAD_NAME)
    thread.start()
    deadline = time.monotonic() + startup_timeout
    try:
        while not server.started:
            assert thread.is_alive(), "server thread died during startup"
            assert time.monotonic() < deadline, (
                f"server did not start within {startup_timeout:g}s; its thread was at:\n"
                f"{_stack_of(thread)}"
            )
            time.sleep(0.02)
    except BaseException:
        # The fixture never reaches its own cleanup when startup fails, so stop the thread here:
        # left running it would migrate concurrently with the next test's server.
        _stop_server(server, thread)
        raise
    return server, thread


def _stop_server(server: uvicorn.Server, thread: threading.Thread) -> None:
    """Ask the server to exit and wait for its thread."""
    server.should_exit = True
    thread.join(timeout=15)
    assert not thread.is_alive(), "server thread did not shut down"


def test_a_server_that_misses_its_startup_deadline_is_stopped_not_leaked(tmp_path: Path) -> None:
    """A late start must not leave its thread running in the background.

    A leaked thread keeps running Alembic while the next test's server starts. Alembic's ``op``
    proxy is process-global, so the two migrations corrupt each other: the CI errors
    ``'NoneType' object has no attribute 'create_index'`` and, locally, a native access violation.
    """
    base = make_service_config(tmp_path)
    port = _free_port()
    config = dataclasses.replace(base, server=dataclasses.replace(base.server, port=port))
    with pytest.raises(AssertionError, match="did not start") as failure:
        _start_server(config, startup_timeout=0.0)
    assert not [t for t in threading.enumerate() if t.name == SERVER_THREAD_NAME]
    # The failure says where the server thread was, so a slow CI start can be diagnosed.
    assert "its thread was at" in str(failure.value)


@pytest.fixture
def live_server(tmp_path: Path, request: pytest.FixtureRequest) -> Iterator[int]:
    """Serve the app on a free port exactly as the launcher configures uvicorn.

    Parametrize indirectly with a tuple of ``trusted_proxies`` (default: none).
    """
    base = make_service_config(tmp_path)
    port = _free_port()
    server_settings = dataclasses.replace(
        base.server, port=port, trusted_proxies=getattr(request, "param", ())
    )
    config = dataclasses.replace(base, server=server_settings)
    server, thread = _start_server(config)
    try:
        yield port
    finally:
        _stop_server(server, thread)


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


TRUSTED_LOOPBACK = pytest.mark.parametrize("live_server", [("127.0.0.1",)], indirect=True)


@TRUSTED_LOOPBACK
def test_a_trusted_proxy_makes_the_same_forwarded_client_share_one_throttle_bucket(
    live_server: int,
) -> None:
    statuses = [_login_status(live_server, "203.0.113.7") for _ in range(8)]
    assert statuses[:5] == [401] * 5
    assert 429 in statuses[5:]


@TRUSTED_LOOPBACK
def test_a_trusted_proxy_gives_each_forwarded_client_its_own_throttle_bucket(
    live_server: int,
) -> None:
    """Trusting a proxy makes ``X-Forwarded-For`` authoritative: name only real proxies."""
    statuses = [_login_status(live_server, f"203.0.113.{n}") for n in range(1, 9)]
    assert statuses == [401] * 8


@pytest.mark.parametrize("live_server", [("10.0.0.0/8",)], indirect=True)
def test_a_proxy_list_that_excludes_the_peer_ignores_forwarded_for(live_server: int) -> None:
    statuses = [_login_status(live_server, f"203.0.113.{n}") for n in range(1, 9)]
    assert statuses[:5] == [401] * 5
    assert 429 in statuses[5:]


@TRUSTED_LOOPBACK
def test_a_trusted_proxy_keys_on_the_rightmost_untrusted_forwarded_entry(live_server: int) -> None:
    """A client that prepends forged hops cannot dodge the throttle: the proxy's entry wins."""
    statuses = [_login_status(live_server, f"198.51.100.{n}, 203.0.113.7") for n in range(1, 9)]
    assert statuses[:5] == [401] * 5
    assert 429 in statuses[5:]


def test_ctrl_c_after_a_graceful_shutdown_exits_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``uvicorn.Server.run`` re-raises the captured SIGINT after shutting down gracefully."""
    monkeypatch.chdir(tmp_path)
    for key, value in _env(tmp_path).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr("bunsho.main.configure_logging", lambda *_args, **_kwargs: None)

    class InterruptedServer:
        def __init__(self, _config: uvicorn.Config) -> None:
            pass

        def run(self) -> None:
            raise KeyboardInterrupt

    monkeypatch.setattr("bunsho.main.uvicorn.Server", InterruptedServer)
    main()  # must return normally


def test_an_invalid_configuration_exits_with_status_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    for key in ("USERNAME", "PASSWORD_HASH", "JWT_SECRET"):
        monkeypatch.delenv(f"BUNSHO_AUTH__{key}", raising=False)
    monkeypatch.setattr("bunsho.main.configure_logging", lambda *_args, **_kwargs: None)
    with pytest.raises(SystemExit) as info:
        main()
    assert info.value.code == 2
