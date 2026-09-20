"""Smoke-test the Bunshō container end to end.

The scenario is: build, start, serve the UI, log in, build content, review a card, restart.

Usage: ``uv run python scripts/smoke_test.py``. Needs Docker with Compose v2 and the real deck in
``resources/``. Exits 1 on any failure (after printing the container logs), 2 when Docker is not
installed, 130 on Ctrl+C, and always tears the stack down and removes its temp folder (set
``BUNSHO_SMOKE_KEEP=1`` to leave both in place for debugging).

Environment: ``BUNSHO_SMOKE_PORT`` (host port, default 18192), ``BUNSHO_SMOKE_KEEP`` (``1`` keeps
the stack and its temp env folder).

The script generates its own credentials and env file in a temp folder outside the repository, so
it never touches a developer's ``.env`` or the real ``bunsho_bunsho-data`` volume. Containers,
network and volume are isolated by the ``bunsho-smoke`` compose project name; only the image tag
``bunsho:local`` is shared, so the smoke build reuses and retags a developer's own local build.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from pwdlib import PasswordHash

ROOT = Path(__file__).resolve().parent.parent
PROJECT = "bunsho-smoke"
PORT = int(os.environ.get("BUNSHO_SMOKE_PORT", "18192"))
ORIGIN = f"http://127.0.0.1:{PORT}"
BASE = f"{ORIGIN}/api/v1"
USERNAME = "smoke"
EXPECTED_COUNTS = {"vocab": 7734, "kanji": 3088, "kana": 208}
# The script's own timeouts must lose the race against the 25 minute (1500 s) CI job timeout, so
# its `finally` teardown runs instead of the runner killing the job. Worst case, every stage
# nearly times out, and the last one does: up 600 + healthy 120 + build 300 + docker healthy 90
# + restart 60 + healthy 120 = 1290 s, then the failure path adds logs 60 + down 60 = 1410 s
# (23.5 minutes, 90 s of margin). A normal run takes about one to two minutes.
COMPOSE_UP_TIMEOUT_SECONDS = 600
COMPOSE_TIMEOUT_SECONDS = 60
LOG_TAIL_LINES = 200
HEALTHY_TIMEOUT_SECONDS = 120
DOCKER_HEALTHY_TIMEOUT_SECONDS = 90
BUILD_TIMEOUT_SECONDS = 300
POLL_SECONDS = 2
# The login throttle blocks a client after this many failures inside its window.
THROTTLE_MAX_FAILURES = 5
THROTTLE_ATTEMPTS = 8
# Errors that mean "the service is not answering (yet)" rather than "the test failed".
_TRANSIENT = (OSError, http.client.HTTPException, ValueError)


class SmokeFailure(AssertionError):
    """An expectation of the smoke test did not hold."""


def log(message: str) -> None:
    """Write a progress line to stderr."""
    sys.stderr.write(f"[smoke] {message}\n")


def compose(
    env_file: Path,
    *args: str,
    check: bool = True,
    timeout: float = COMPOSE_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    """Run ``docker compose`` for the smoke project (``TimeoutExpired`` after ``timeout`` s)."""
    env = {**os.environ, "BUNSHO_ENV_FILE": str(env_file), "BUNSHO_HOST_PORT": str(PORT)}
    return subprocess.run(
        ["docker", "compose", "-p", PROJECT, "-f", str(ROOT / "compose.yaml"), *args],
        cwd=ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=check,
        timeout=timeout,
    )


def request(
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    """Call the API and return ``(status, json body)`` without raising on HTTP errors."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    for name, value in (headers or {}).items():
        req.add_header(name, value)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"null")


def http_get(path: str) -> tuple[int, dict[str, str], bytes]:
    """GET ``path`` on the server root (outside /api/v1) without raising on HTTP errors."""
    req = urllib.request.Request(ORIGIN + path, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            headers = {name.lower(): value for name, value in response.headers.items()}
            return response.status, headers, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, {name.lower(): value for name, value in exc.headers.items()}, exc.read()


def expect_frontend_served() -> None:
    """The container serves the built UI: shell, deep links, cache headers and JSON API 404s."""
    status, headers, body = http_get("/")
    expect(status == 200, f"GET / returned {status}, not 200")
    expect("text/html" in headers.get("content-type", ""), "GET / is not HTML")
    expect(b'<div id="root">' in body, "GET / did not return the app shell")
    expect(headers.get("cache-control") == "no-cache", "the app shell must not be cached")
    status, _, deep_link = http_get("/build")
    expect(status == 200 and deep_link == body, "a client-side route did not return the shell")
    script = re.search(rb'/assets/[^"\']+\.js', body)
    expect(script is not None, "index.html references no hashed script")
    status, headers, _ = http_get(script.group(0).decode())
    expect(status == 200, f"the hashed script returned {status}")
    expect("immutable" in headers.get("cache-control", ""), "hashed assets must be immutable")
    expect(http_get("/assets/does-not-exist.js")[0] == 404, "a missing asset must be a 404")
    status, headers, _ = http_get("/api/v1/does-not-exist")
    expect(status == 404, f"an unknown API path returned {status}, not 404")
    expect("application/json" in headers.get("content-type", ""), "an API 404 must be JSON")


def expect(condition: bool, message: str) -> None:
    """Fail the smoke test with ``message`` unless ``condition`` holds."""
    if not condition:
        raise SmokeFailure(message)


def wait_healthy() -> None:
    """Poll ``/health`` until the service answers HTTP 200 (``ok`` or ``degraded``)."""
    deadline = time.monotonic() + HEALTHY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            status, _ = request("GET", "/health")
        except _TRANSIENT:
            status = 0
        if status == 200:
            return
        time.sleep(POLL_SECONDS)
    raise SmokeFailure(f"service not answering /health after {HEALTHY_TIMEOUT_SECONDS}s")


def wait_docker_healthy(env_file: Path) -> None:
    """Poll until Docker's own HEALTHCHECK marks the container ``healthy``."""
    deadline = time.monotonic() + DOCKER_HEALTHY_TIMEOUT_SECONDS
    health = "unknown"
    while time.monotonic() < deadline:
        # Compose prints one JSON object per line (or a JSON array on older versions).
        out = compose(env_file, "ps", "--format", "json").stdout.strip()
        rows = json.loads(out) if out.startswith("[") else [json.loads(x) for x in out.splitlines()]
        health = rows[0].get("Health", "") if rows else "no container"
        if health == "healthy":
            return
        time.sleep(POLL_SECONDS)
    raise SmokeFailure(f"docker healthcheck is {health!r} after {DOCKER_HEALTHY_TIMEOUT_SECONDS}s")


def login(password: str) -> dict[str, str]:
    """Log in and return the token pair."""
    status, body = request("POST", "/auth/login", body={"username": USERNAME, "password": password})
    expect(status == 200, f"login returned {status}: {body}")
    return {"access": body["access_token"], "refresh": body["refresh_token"]}


def build_content(access: str) -> None:
    """Start a full content build and wait for it to succeed."""
    status, task = request("POST", "/admin/content/build", token=access, body={})
    expect(status == 202, f"build start returned {status}: {task}")
    task_id = task["task_id"]
    deadline = time.monotonic() + BUILD_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        status, task = request("GET", f"/admin/content/build/{task_id}", token=access)
        expect(status == 200, f"build status returned {status}: {task}")
        if task["state"] != "running":
            expect(task["state"] == "succeeded", f"build ended {task['state']}: {task['error']}")
            return
        time.sleep(POLL_SECONDS)
    raise SmokeFailure(f"content build still running after {BUILD_TIMEOUT_SECONDS}s")


def expect_summary(access: str) -> None:
    """Check the content summary matches the real deck."""
    status, summary = request("GET", "/content/summary", token=access)
    expect(status == 200, f"summary returned {status}: {summary}")
    expect(summary["built"] is True, "summary says content is not built")
    got = {key: summary[key] for key in EXPECTED_COUNTS}
    expect(got == EXPECTED_COUNTS, f"content counts {got} != {EXPECTED_COUNTS}")


def exercise_reviews(access: str) -> None:
    """Read the settings, answer one new card and check it is recorded exactly once."""
    status, settings = request("GET", "/settings", token=access)
    expect(status == 200, f"settings returned {status}: {settings}")
    expect(settings["new_card_policy"] == "strict_order", f"unexpected settings: {settings}")
    status, first = request("GET", "/reviews/next", token=access)
    expect(status == 200, f"reviews/next returned {status}: {first}")
    card = first["card"]
    expect(card is not None and card["is_new"] is True, f"no new card offered: {first}")
    # Every type starts with a full allowance and ties go to kana.
    expect(card["item_type"] == "kana", f"first new card is {card['item_type']}, not kana")
    body = {
        "item_id": card["item_id"],
        "direction": card["direction"],
        "grade": 3,
        "expected_last_review": card["expected_last_review"],
    }
    status, counts = request("POST", "/reviews/answer", token=access, body=body)
    expect(status == 200, f"answer returned {status}: {counts}")
    status, _ = request("POST", "/reviews/answer", token=access, body=body)
    expect(status == 409, f"a repeated answer returned {status}, not 409")
    expect_reviews_recorded(access)


def expect_reviews_recorded(access: str) -> None:
    """Check ``/stats/summary`` counts exactly one review (robust across the study-day rollover)."""
    status, stats = request("GET", "/stats/summary", token=access)
    expect(status == 200, f"stats returned {status}: {stats}")
    total = sum(day["reviews"] for day in stats["daily_reviews"])
    expect(total == 1, f"expected exactly one recorded review, stats say {total}")


def expect_health(want: str) -> None:
    """Check ``/health`` reports overall status ``want`` and print the components."""
    status, health = request("GET", "/health")
    components = {name: c["status"] for name, c in health["components"].items()}
    log(f"health: {health['status']} {components}")
    expect(status == 200, f"health returned {status}")
    expect(health["status"] == want, f"health is {health['status']}, expected {want}: {health}")


def expect_throttle_ignores_forwarded_for(password: str) -> None:
    """Forged ``X-Forwarded-For`` headers must not give an attacker fresh throttle buckets.

    Proxy headers are ignored unless ``server.trusted_proxies`` is set, so every request below
    comes from the same peer. Attempts 1-5 are answered 401, the rest 429, and then even the
    correct password is refused with 429.

    This runs LAST on purpose. It leaves the peer's bucket locked for the 60 s window, and a
    successful login from the same peer would reset the counter and hide a broken throttle.
    Everything else (login, build, restart, refresh) is finished by now, and the script ends
    right after, so nothing has to wait out the window and the run stays fast and deterministic.
    """
    statuses = [
        request(
            "POST",
            "/auth/login",
            body={"username": USERNAME, "password": "wrong"},
            headers={"X-Forwarded-For": f"203.0.113.{attempt + 1}"},
        )[0]
        for attempt in range(THROTTLE_ATTEMPTS)
    ]
    expected = [401] * THROTTLE_MAX_FAILURES + [429] * (THROTTLE_ATTEMPTS - THROTTLE_MAX_FAILURES)
    expect(
        statuses == expected, f"forged X-Forwarded-For throttle statuses {statuses} != {expected}"
    )
    status, _ = request(
        "POST",
        "/auth/login",
        body={"username": USERNAME, "password": password},
        headers={"X-Forwarded-For": "198.51.100.7"},
    )
    expect(status == 429, f"correct password from a throttled peer returned {status}, not 429")


def run(env_file: Path, password: str) -> None:
    """Drive the whole scenario against a running stack."""
    log("waiting for the service to answer")
    wait_healthy()
    log("checking that the container serves the web UI")
    expect_frontend_served()
    expect_health("degraded")  # first run: no content.db yet
    expect(request("GET", "/content/summary")[0] == 401, "summary must require a token")
    status, _ = request("POST", "/auth/login", body={"username": USERNAME, "password": "wrong"})
    expect(status == 401, f"wrong password returned {status}, not 401")
    tokens = login(password)
    log("building content from the real deck (about 40 s)")
    started = time.monotonic()
    build_content(tokens["access"])
    log(f"content build took {time.monotonic() - started:.0f} s")
    expect_summary(tokens["access"])
    log("answering one card")
    exercise_reviews(tokens["access"])
    expect_health("ok")
    log("waiting for Docker's healthcheck")
    wait_docker_healthy(env_file)
    log("restarting the container")
    compose(env_file, "restart", "bunsho")
    wait_healthy()
    status, refreshed = request("POST", "/auth/refresh", body={"refresh_token": tokens["refresh"]})
    expect(status == 200, f"refresh after restart returned {status}: {refreshed}")
    expect_summary(refreshed["access_token"])
    expect_reviews_recorded(refreshed["access_token"])  # progress.db survived the restart
    expect_health("ok")  # content.db and progress.db survived the restart
    log("checking the login throttle ignores forged X-Forwarded-For headers")
    expect_throttle_ignores_forwarded_for(password)
    log("PASS")


def write_env_file(folder: Path, password: str) -> Path:
    """Write the container env file with freshly generated credentials."""
    env_file = folder / "smoke.env"
    env_file.write_text(
        f"BUNSHO_AUTH__USERNAME={USERNAME}\n"
        f"BUNSHO_AUTH__PASSWORD_HASH='{PasswordHash.recommended().hash(password)}'\n"
        f"BUNSHO_AUTH__JWT_SECRET={secrets.token_urlsafe(48)}\n",
        encoding="utf-8",
    )
    return env_file


def dump_logs(env_file: Path) -> None:
    """Print the container logs; never raises (this runs while another failure is in flight)."""
    try:
        logs = compose(env_file, "logs", "--tail", str(LOG_TAIL_LINES), check=False).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        logs = f"(could not read the container logs: {type(exc).__name__}: {exc})"
    log(logs)


def tear_down(env_file: Path) -> None:
    """Remove the smoke stack and its volume; never raises."""
    try:
        compose(env_file, "down", "-v", "--remove-orphans", check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"WARNING: tear-down failed, remove the stack by hand: {type(exc).__name__}: {exc}")
        log(f"docker compose -p {PROJECT} down -v")


def run_stack(folder: Path, keep: bool) -> int:
    """Create the credentials, start the stack, run the scenario and tear the stack down.

    Returns:
        The process exit code: 0 on success, 1 on any failure, 130 when interrupted.
    """
    env_file: Path | None = None
    try:
        password = secrets.token_urlsafe(16)
        env_file = write_env_file(folder, password)
        log("building the image and starting the stack")
        compose(env_file, "up", "-d", "--build", timeout=COMPOSE_UP_TIMEOUT_SECONDS)
        run(env_file, password)
        return 0
    except (Exception, KeyboardInterrupt) as exc:  # any failure must still print logs
        interrupted = isinstance(exc, KeyboardInterrupt)
        log("INTERRUPTED" if interrupted else f"FAIL: {type(exc).__name__}: {exc}")
        if isinstance(exc, subprocess.CalledProcessError):
            log(exc.stderr or "")
        if env_file is not None:
            dump_logs(env_file)
        return 130 if interrupted else 1
    finally:
        if env_file is not None:
            if keep:
                log(f"BUNSHO_SMOKE_KEEP=1: stack left running, env file in {folder}")
            else:
                tear_down(env_file)


def main() -> int:
    """Check the prerequisites, run the scenario and always remove the temp folder."""
    if shutil.which("docker") is None:
        log("FAIL: the docker executable was not found on PATH; install Docker with Compose v2")
        return 2
    keep = os.environ.get("BUNSHO_SMOKE_KEEP") == "1"
    folder = Path(tempfile.mkdtemp(prefix="bunsho-smoke-"))
    try:
        return run_stack(folder, keep)
    finally:
        if not keep:
            shutil.rmtree(folder, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
