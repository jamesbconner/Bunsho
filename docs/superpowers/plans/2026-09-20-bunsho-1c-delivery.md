# Bunshō Plan 1C: Delivery (Docker, compose, smoke test, hardening)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Bunshō as a container that a home box can run with `docker compose up -d`: a Python-only image, a compose file, a CI smoke test that exercises the real container end to end, and the startup/shutdown hardening that the container makes matter.

**Architecture:** No new subsystems. Plan 1B's `bunsho` launcher becomes the image entrypoint (single process, single worker). Small code changes make it safe as a long-running service: a migration lock, actionable `progress.db` startup errors, cleanup of temp files left by a killed build, an explicit graceful-shutdown budget, a configurable trusted-proxy list, and a tighter WebSocket frame limit. A stdlib-only Python script drives `docker compose` for the smoke test, locally and in CI.

**Tech Stack:** Docker (multi-stage, `python:3.13-slim-bookworm`, uv 0.12.17 to install), Docker Compose v2, `filelock` (new runtime dependency), pytest (`pytester` for one plugin test), pre-commit, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-19-bunsho-foundation-and-review-engine-design.md` (Docker: multi-stage, non-root, `HEALTHCHECK` on `/api/v1/health`, one compose service on 8192, volumes `/data` rw and `resources/` ro; the Node stage arrives with Plan 2). Plans 1A and 1B are merged: `docs/superpowers/plans/2026-09-19-bunsho-1a-foundation-content-pipeline.md`, `docs/superpowers/plans/2026-09-19-bunsho-1b-authenticated-api.md`.

**Plan series:** 1A (done) → 1B (done) → **1C (this plan: delivery)** → 2 (FSRS review engine + React UI + Node stage in the image).

## Global Constraints

- Python `>=3.13`; build backend `hatchling`; `uv`; display name **Bunshō**, ASCII slug **`bunsho`** (image, service, package, volume names); MIT license (the vocabulary deck in `resources/` is GPL-3.0 with its own LICENSE; it is mounted, not baked into the image).
- **No CLI** (no click/rich); the `bunsho` console script stays a thin uvicorn launcher. No `print` in `src/`; `logging` with `key=value` messages. Never log passwords, tokens or the JWT secret.
- Google-style docstrings on public items; modern type syntax; mypy strict; ruff (lint + format) and bandit clean; coverage `>= 90%` (measured on `src/bunsho`).
- Port **8192**; **never 8000**. The container binds `0.0.0.0` (env), the code default stays `127.0.0.1`.
- **A single worker only.** The login throttle and the build manager are in-process. Never add `--workers`, `--reload` or a second replica. The image entrypoint is the `bunsho` launcher, never `uvicorn ...` directly (uvicorn's own default would re-enable proxy headers).
- Container hardening: non-root user (uid 10001), read-only root filesystem when it works, `no-new-privileges`, all capabilities dropped, `HEALTHCHECK` on `GET /api/v1/health` (a `degraded` first-run answer is HTTP 200 and counts as healthy; only HTTP 503 is unhealthy).
- `progress.db` is irreplaceable: nothing in this plan may weaken the backup-before-migrate rule or make a migration failure silent. Graceful shutdown budget: `BuildTaskManager.aclose` waits 30 s, uvicorn gets `timeout_graceful_shutdown = 35`, compose `stop_grace_period: 60s` (the build runs in a thread that cannot be cancelled, so the process exits only when a running build finishes; measured ~38 s for the real deck, so 35 s ends in SIGKILL exit 137, which is data-safe because content.db is swapped atomically, but unclean).
- Proxy headers are ignored unless `server.trusted_proxies` names the proxy addresses; `*` is rejected (it would let any client choose its throttle bucket).
- Tests: shared builders/fixtures live in `tests/base.py`; the suite must behave identically on ubuntu, windows and macos; no `pytest-asyncio`. Tests that touch threads, sockets or `TestClient` teardown must be run 40+ times in a loop before being called stable (a 35 % flake once passed three repeat runs).
- Test snippets that begin with `import` lines show imports that belong in the **top import block** of the file they extend: merge them there and drop any that end up unused (ruff `I001`/`E402`).
- Commit messages: conventional commits, two `-m` arguments so the `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` trailer is its own paragraph; stage explicit paths only.
- Facts from Plans 1A/1B the tasks rely on: `run_migrations(db_path, *, backup_dir, now, logger)` in `src/bunsho/db/migrate.py`; `build_services(config, overrides)` in `src/bunsho/api/services.py` (migrates, pings, `create_context`); `ContentWriter.write` writes `content.db.<uuid4 hex>.tmp` then `os.replace`; `build_server_config(app, config)` and `main()` in `src/bunsho/main.py` (`proxy_headers=False`); `ServerSettings(host, port, cors_origins)` and `validate_service_config`/`load_service_config` in `src/bunsho/config/service.py`; routes `POST /api/v1/auth/login|refresh`, `POST /api/v1/admin/content/build` (202), `GET /api/v1/admin/content/build/{task_id}`, `GET /api/v1/content/summary`, `GET /api/v1/health`; the real deck yields 7,734 vocab, 3,088 kanji rows (2,109 leveled + 979 unleveled) and 208 kana; `tests/base.py` has `make_service_config`, `make_auth_settings`, `PASSWORD`, `JWT_SECRET`, `StubOrchestrator`, `close_and_wait_for_unsubscribe`; env config keys are `BUNSHO_<SECTION>__<KEY>` (for example `BUNSHO_PATHS__DATA_DIR`).

## File Structure

| Path | Responsibility |
|---|---|
| `src/bunsho/db/migrate.py` (modify) | Migration lock, writability check before the backup |
| `src/bunsho/services/content_repository.py` (modify) | `remove_stale_temp_files` |
| `src/bunsho/api/services.py` (modify) | `StartupError`; wrap migration failures; sweep temp files |
| `src/bunsho/config/service.py` (modify) | `ServerSettings.trusted_proxies` + validation |
| `src/bunsho/main.py` (modify) | Trusted proxies, graceful-shutdown budget, WebSocket frame limit |
| `src/bunsho/py.typed` (create) | PEP 561 marker |
| `Dockerfile`, `.dockerignore`, `compose.yaml` (create) | The image and the compose service |
| `scripts/smoke_test.py` (create) | Container end-to-end smoke test (stdlib + pwdlib) |
| `.github/workflows/ci.yml`, `.github/dependabot.yml` (modify) | `smoke` job; docker ecosystem |
| `.pre-commit-config.yaml` (create) | ruff, ruff-format, mypy, bandit |
| `tests/conftest.py`, `tests/unit/test_ci_skip_policy.py` (modify/create) | Integration tests fail instead of skipping when `CI` is set |
| `CHANGELOG.md` (create), `README.md`, `TODO.md` (modify) | Docs |

---

### Task 1: Startup hardening (migration lock, actionable startup errors, temp sweep)

**Files:**
- Modify: `pyproject.toml` (dependency `filelock`), `uv.lock`
- Modify: `src/bunsho/db/migrate.py`, `src/bunsho/services/content_repository.py`, `src/bunsho/api/services.py`
- Test: `tests/unit/db/test_migrate.py`, `tests/unit/services/test_content_repository.py`, `tests/unit/api/test_app_startup.py`

**Interfaces:**
- Consumes: `run_migrations`, `build_services`, `ContentWriter` (Plan 1B/1A).
- Produces: `MIGRATION_LOCK_TIMEOUT_SECONDS: float`; `remove_stale_temp_files(target: Path, logger: logging.Logger | None = None) -> int`; `StartupError(RuntimeError)` in `bunsho.api.services`. Log lines `content_tmp_removed count=%d dir=%s`, `content_tmp_remove_failed path=%s error=%s`, `progress_db_startup_failed path=%s backups=%s error=%s`.

**Why:** the whole-branch review of Plan 1B found (a) two processes migrating one `progress.db` at once can leave it half-upgraded (SQLite DDL is not transactional; reproduced with two processes, `table card_state already exists`, and both computed the same backup name), (b) a corrupt or read-only `progress.db` produced a 30-line SQLAlchemy traceback with no path or hint, and a read-only file still got a pointless backup first, (c) a SIGKILL mid-build leaves a multi-MB `content.db.<hex>.tmp` in the data volume forever.

- [ ] **Step 1: Add the dependency**

Run: `uv add "filelock>=3.20"` (use whatever current release `uv` resolves; keep the lower bound at that major/minor). Confirm `uv lock --check` passes.

- [ ] **Step 2: Write the failing tests for the migration lock and the writability check**

Append to `tests/unit/db/test_migrate.py` (merge imports at the top; reuse the file's existing fixtures/helpers for a `tmp_path`, `now`, and a quiet logger):

```python
import threading

import filelock
import pytest

from bunsho.db import migrate


def test_concurrent_migrations_of_a_new_database_both_succeed(tmp_path, quiet_logger) -> None:
    db = tmp_path / "progress.db"
    backups = tmp_path / "backups"
    barrier = threading.Barrier(2)
    results: list[migrate.MigrationResult] = []
    errors: list[BaseException] = []

    def worker() -> None:
        barrier.wait()
        try:
            results.append(
                migrate.run_migrations(db, backup_dir=backups, logger=quiet_logger)
            )
        except BaseException as exc:  # noqa: BLE001 - collected and asserted below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert errors == []
    assert sorted(r.upgraded for r in results) == [False, True]  # one migrates, one finds it done


def test_a_held_migration_lock_times_out_with_a_clear_error(
    tmp_path, quiet_logger, monkeypatch
) -> None:
    db = tmp_path / "progress.db"
    monkeypatch.setattr(migrate, "MIGRATION_LOCK_TIMEOUT_SECONDS", 0.2)
    with filelock.FileLock(str(tmp_path / "progress.db.migrate.lock")):
        with pytest.raises(filelock.Timeout):
            migrate.run_migrations(db, backup_dir=tmp_path / "backups", logger=quiet_logger)
    assert not db.exists()


def test_an_unwritable_database_fails_before_a_backup_is_taken(
    tmp_path, quiet_logger, monkeypatch
) -> None:
    db = tmp_path / "progress.db"
    with closing(sqlite3.connect(db)) as con:  # a valid but unversioned file: needs migrating
        con.execute("CREATE TABLE legacy (x INTEGER)")
    monkeypatch.setattr(migrate.os, "access", lambda path, mode: False)
    with pytest.raises(PermissionError, match="not writable"):
        migrate.run_migrations(db, backup_dir=tmp_path / "backups", logger=quiet_logger)
    assert not (tmp_path / "backups").exists()
```

(`closing` and `sqlite3` are imported at the top of the file if not already.)

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/db/test_migrate.py -q --no-cov`
Expected: the three new tests FAIL (`MIGRATION_LOCK_TIMEOUT_SECONDS` missing; no lock; no writability check).

- [ ] **Step 4: Implement the lock and the writability check**

In `src/bunsho/db/migrate.py` add near the other constants and imports (`import os`, `from filelock import FileLock`):

```python
MIGRATION_LOCK_TIMEOUT_SECONDS = 120.0
"""How long a starting process waits for another one that is migrating ``progress.db``."""


def _require_writable(db_path: Path) -> None:
    """Raise ``PermissionError`` when ``progress.db`` (or its folder) cannot be written.

    Checked before the backup so a read-only volume does not produce a pointless backup
    followed by an opaque driver error.
    """
    for target in (db_path, db_path.parent):
        if target.exists() and not os.access(target, os.W_OK):
            raise PermissionError(f"progress.db location is not writable: {target}")
```

Change `run_migrations` so everything after `db_path.parent.mkdir(...)` runs inside the lock, and the writability check runs right before the backup is taken:

```python
    db_path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(db_path.with_name(f"{db_path.name}.migrate.lock")))
    with lock.acquire(timeout=MIGRATION_LOCK_TIMEOUT_SECONDS):
        existed = db_path.is_file()
        current = _current_revision(db_path) if existed else None
        if existed and current == head:
            log.info("progress_db_up_to_date revision=%s path=%s", head, db_path)
            return MigrationResult(current, head, False, None)
        if existed:
            _require_writable(db_path)
        backup = _backup(db_path, backup_dir, current, clock()) if existed else None
        ...  # the rest of the existing body, unchanged, indented into the with-block
```

Read the timeout from the module global at call time (`lock.acquire(timeout=MIGRATION_LOCK_TIMEOUT_SECONDS)` does), so the test's `monkeypatch` takes effect. Update the docstring: `Raises:` gains `filelock.Timeout: another process held the migration lock for more than MIGRATION_LOCK_TIMEOUT_SECONDS` and `PermissionError: progress.db or its folder is not writable`.

- [ ] **Step 5: Run the migrate tests until green**

Run: `uv run pytest tests/unit/db/test_migrate.py -q --no-cov` — all pass. Then run the concurrency test 40 times: `for i in $(seq 1 40); do uv run pytest tests/unit/db/test_migrate.py -q --no-cov -k concurrent -x || break; done`.

- [ ] **Step 6: Write the failing tests for the temp-file sweep**

Append to `tests/unit/services/test_content_repository.py`:

```python
import logging
import uuid

from bunsho.services.content_repository import remove_stale_temp_files


def test_stale_temp_files_are_removed_and_other_files_kept(tmp_path, caplog) -> None:
    target = tmp_path / "content.db"
    target.write_bytes(b"live")
    stale = [tmp_path / f"content.db.{uuid.uuid4().hex}.tmp" for _ in range(2)]
    for path in stale:
        path.write_bytes(b"x" * 10)
    keep = [
        tmp_path / "content.db.notes.tmp",  # not a build temp file
        tmp_path / "other.db.0123456789abcdef0123456789abcdef.tmp",  # another database
        tmp_path / "progress.db",
    ]
    for path in keep:
        path.write_bytes(b"keep")
    with caplog.at_level(logging.INFO, logger="bunsho"):
        removed = remove_stale_temp_files(target, logging.getLogger("bunsho"))
    assert removed == 2
    assert not any(path.exists() for path in stale)
    assert all(path.exists() for path in [target, *keep])
    assert "content_tmp_removed count=2" in caplog.text


def test_sweeping_a_missing_folder_is_a_no_op(tmp_path) -> None:
    assert remove_stale_temp_files(tmp_path / "nope" / "content.db") == 0
```

- [ ] **Step 7: Run to verify FAIL, then implement `remove_stale_temp_files`**

In `src/bunsho/services/content_repository.py` (add `import re` and `import logging` if missing):

```python
_TEMP_SUFFIX = re.compile(r"\.[0-9a-f]{32}\.tmp$")


def remove_stale_temp_files(target: Path, logger: logging.Logger | None = None) -> int:
    """Delete ``<target>.<uuid hex>.tmp`` files left by a build that was killed mid-write.

    Call only while no build can be running (at startup). Files that do not match the
    exact temp-name pattern of ``ContentWriter`` are never touched.

    Args:
        target: The final ``content.db`` path; its folder is scanned.
        logger: Logger for ``key=value`` messages.

    Returns:
        How many files were removed.
    """
    log = logger or logging.getLogger(__name__)
    if not target.parent.is_dir():
        return 0
    removed = 0
    for path in target.parent.iterdir():
        if not path.name.startswith(f"{target.name}.") or not _TEMP_SUFFIX.search(path.name):
            continue
        try:
            path.unlink()
        except OSError as exc:
            log.warning("content_tmp_remove_failed path=%s error=%s", path, type(exc).__name__)
        else:
            removed += 1
    if removed:
        log.info("content_tmp_removed count=%d dir=%s", removed, target.parent)
    return removed
```

Run: `uv run pytest tests/unit/services/test_content_repository.py -q --no-cov` — pass.

- [ ] **Step 8: Write the failing tests for actionable startup errors**

Append to `tests/unit/api/test_app_startup.py` (reuse its existing fixtures for a `ServiceConfig`; a corrupt file is `progress_db_path.write_bytes(b"not a database" * 100)`):

```python
import asyncio

from bunsho.api.services import StartupError, build_services


def test_a_corrupt_progress_db_gives_an_actionable_startup_error(service_config, caplog) -> None:
    path = service_config.app.progress_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a database" * 100)
    with pytest.raises(StartupError) as info:
        asyncio.run(build_services(service_config))
    message = str(info.value)
    assert str(path) in message
    assert str(service_config.app.data_dir / "backups") in message
    assert "DatabaseError" in message
    assert "progress_db_startup_failed" in caplog.text


def test_stale_build_temp_files_are_swept_at_startup(service_config) -> None:
    data_dir = service_config.app.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    stale = data_dir / f"content.db.{'a' * 32}.tmp"
    stale.write_bytes(b"x")

    async def scenario() -> None:
        services = await build_services(service_config)
        await services.aclose()

    asyncio.run(scenario())
    assert not stale.exists()
```

- [ ] **Step 9: Run to verify FAIL, then implement in `src/bunsho/api/services.py`**

Add imports (`from alembic.util.exc import CommandError`, `from sqlalchemy.exc import DatabaseError`, and `remove_stale_temp_files` from `bunsho.services.content_repository`) and:

```python
class StartupError(RuntimeError):
    """The service cannot start; the message says what to check."""
```

Replace the bare `await asyncio.to_thread(run_migrations, ...)` in `build_services` with:

```python
    backup_dir = app_config.data_dir / "backups"
    try:
        await asyncio.to_thread(
            run_migrations, app_config.progress_db_path, backup_dir=backup_dir, logger=logger
        )
    except (DatabaseError, CommandError, OSError) as exc:  # OSError includes filelock.Timeout
        logger.error(
            "progress_db_startup_failed path=%s backups=%s error=%s: %s",
            app_config.progress_db_path,
            backup_dir,
            type(exc).__name__,
            exc,
        )
        raise StartupError(
            f"progress.db could not be opened or migrated ({type(exc).__name__}). "
            f"Database: {app_config.progress_db_path}. Backups: {backup_dir}. "
            "Check that the data folder is writable by the service user and that the file is "
            "a Bunshō progress database. To restore, stop the service and copy a backup over "
            "progress.db."
        ) from exc
    await asyncio.to_thread(remove_stale_temp_files, app_config.content_db_path, logger)
```

(Keep the existing engine/ping/`create_context` block below unchanged.) Update the `Raises:` docstring of `build_services` (`StartupError`).

- [ ] **Step 10: Run all gates**

Run: `uv run pytest tests -q`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src/`, `uv run bandit -r src/ -l`. All green; `uv lock --check` clean.

- [ ] **Step 11: Commit**

```bash
git add pyproject.toml uv.lock src/bunsho/db/migrate.py src/bunsho/services/content_repository.py src/bunsho/api/services.py tests/unit/db/test_migrate.py tests/unit/services/test_content_repository.py tests/unit/api/test_app_startup.py
git commit -m "feat: migration lock, actionable progress.db startup errors, stale temp sweep" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Server options (trusted proxies, graceful shutdown, WebSocket frame limit)

**Files:**
- Modify: `src/bunsho/config/service.py`, `src/bunsho/main.py`
- Test: `tests/unit/config/test_service_config.py`, `tests/unit/test_main.py`

**Interfaces:**
- Consumes: `ServerSettings`, `validate_service_config`, `load_service_config`, `build_server_config` (Plan 1B).
- Produces: `ServerSettings.trusted_proxies: tuple[str, ...] = ()` (config key `[server] trusted_proxies`, env `BUNSHO_SERVER__TRUSTED_PROXIES`, comma separated IPs or CIDR networks); `GRACEFUL_SHUTDOWN_SECONDS = 35` and `WS_MAX_MESSAGE_BYTES = 65536` in `bunsho.main`; `build_server_config` sets `proxy_headers=bool(trusted_proxies)`, `forwarded_allow_ips=",".join(trusted_proxies) or None`, `timeout_graceful_shutdown=35`, `ws_max_size=65536`.

**Why:** with the launcher's `proxy_headers=False` (Plan 1B final fix) the login throttle keys on the TCP peer. That is correct for direct exposure, but behind nginx (the project's standard front) or Docker NAT every client shares one bucket, so one client can lock the owner out. `trusted_proxies` makes the trust explicit: only those peers may set the client address via `X-Forwarded-For`. The 35 s shutdown budget lets a build that is running at `docker stop` finish or be cancelled cleanly (`BuildTaskManager.aclose` waits 30 s); without it SIGKILL follows uvicorn's default and can leave a temp file. The auth message is at most 8,192 characters (up to 32 KiB of UTF-8), so the 16 MiB default frame limit is needless exposure on unauthenticated sockets.

- [ ] **Step 1: Write the failing config tests**

Append to `tests/unit/config/test_service_config.py` (reuse the file's existing helper that builds a valid `ConfigNormalizer`/raw dict; if it has none, build one the way the file's other tests do):

```python
@pytest.mark.parametrize("value", ["127.0.0.1", "10.0.0.0/8", "127.0.0.1, 172.16.0.0/12", "::1"])
def test_trusted_proxies_accept_addresses_and_networks(value: str) -> None:
    config = load_service_config(valid_normalizer(server={"trusted_proxies": value}))
    assert config.server.trusted_proxies == tuple(part.strip() for part in value.split(","))


def test_trusted_proxies_default_to_empty() -> None:
    assert load_service_config(valid_normalizer()).server.trusted_proxies == ()


@pytest.mark.parametrize("value", ["*", "not-an-ip", "10.0.0.0/33", "127.0.0.1, *"])
def test_trusted_proxies_reject_wildcards_and_garbage(value: str) -> None:
    errors = validate_service_config(valid_normalizer(server={"trusted_proxies": value}))
    assert any("trusted_proxies" in error for error in errors)
```

`valid_normalizer(server=...)` stands for the file's existing way to produce a normalizer with the required auth settings plus overrides; adapt to what the file offers (do not invent a new fixture if one exists).

- [ ] **Step 2: Run to verify FAIL** (`uv run pytest tests/unit/config/test_service_config.py -q --no-cov`), then implement in `src/bunsho/config/service.py`:

```python
import ipaddress
```

`ServerSettings` gains a defaulted last field:

```python
    trusted_proxies: tuple[str, ...] = ()
```

Add the parser and validation (next to `_origins`):

```python
def _trusted_proxies(cfg: ConfigNormalizer) -> tuple[str, ...]:
    raw = cfg.get_string("server", "trusted_proxies")
    return tuple(part.strip() for part in raw.split(",") if part.strip())
```

In `validate_service_config`, after the CORS loop:

```python
    for proxy in _trusted_proxies(cfg):
        try:
            ipaddress.ip_network(proxy, strict=False)
        except ValueError:
            errors.append(
                f"[server] trusted_proxies entry {proxy!r} must be an IP address or network "
                "(a wildcard would let any client choose its own login-throttle bucket)"
            )
```

and `load_service_config` passes `trusted_proxies=_trusted_proxies(cfg)` to `ServerSettings`. Run the config tests until green.

- [ ] **Step 3: Write the failing launcher tests**

In `tests/unit/test_main.py`, next to the existing `build_server_config` test, add (use the file's existing `service_config`/`create_app` usage; `dataclasses.replace` builds variants):

```python
def test_server_config_ignores_proxy_headers_by_default(service_config) -> None:
    config = build_server_config(create_app(service_config), service_config)
    assert config.proxy_headers is False
    assert config.timeout_graceful_shutdown == GRACEFUL_SHUTDOWN_SECONDS == 35
    assert config.ws_max_size == WS_MAX_MESSAGE_BYTES == 65536


def test_server_config_trusts_only_the_configured_proxies(service_config) -> None:
    server = dataclasses.replace(service_config.server, trusted_proxies=("10.0.0.0/8", "::1"))
    cfg = dataclasses.replace(service_config, server=server)
    config = build_server_config(create_app(cfg), cfg)
    assert config.proxy_headers is True
    assert config.forwarded_allow_ips == "10.0.0.0/8,::1"
```

Also extend the existing live-server regression test (the one that sends 8 wrong logins with rotating `X-Forwarded-For` and expects a 429 by attempt 6): add a sibling test that starts the real server with `trusted_proxies=("127.0.0.1",)` and shows that (1) 8 wrong logins carrying the **same** `X-Forwarded-For` value get a 429 by attempt 6, and (2) wrong logins carrying a **different** `X-Forwarded-For` value each are all 401 (each forwarded client has its own bucket). Reuse the same `live_server` fixture/thread/readiness-polling helper; parametrize it over the config rather than copying it. This documents the trade-off: trusting a proxy is exactly what makes the header authoritative, so it must only name real proxies.

- [ ] **Step 4: Run to verify FAIL, then implement in `src/bunsho/main.py`**

Add constants (module level, with the explanation):

```python
GRACEFUL_SHUTDOWN_SECONDS = 35
"""uvicorn's shutdown budget: a little more than ``BuildTaskManager.aclose``'s 30 s wait."""

WS_MAX_MESSAGE_BYTES = 65536
"""Largest WebSocket frame accepted. The auth message is at most 8,192 characters (32 KiB of
UTF-8), so uvicorn's 16 MiB default only widens the unauthenticated attack surface."""
```

and replace the `uvicorn.Config(...)` call in `build_server_config`:

```python
    proxies = config.server.trusted_proxies
    return uvicorn.Config(
        app,
        host=config.server.host,
        port=config.server.port,
        log_config=None,
        proxy_headers=bool(proxies),
        forwarded_allow_ips=",".join(proxies) if proxies else None,
        timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_SECONDS,
        ws_max_size=WS_MAX_MESSAGE_BYTES,
    )
```

Update the function's docstring: proxy headers are honoured only from `server.trusted_proxies`; never pass `*`. Run the whole `tests/unit/test_main.py` file **40 times** (`for i in $(seq 1 40); do uv run pytest tests/unit/test_main.py -q --no-cov -x || break; done`) since it starts real servers.

- [ ] **Step 5: Gates and commit**

`uv run pytest tests -q`, ruff check/format, mypy, bandit all green.

```bash
git add src/bunsho/config/service.py src/bunsho/main.py tests/unit/config/test_service_config.py tests/unit/test_main.py
git commit -m "feat: trusted proxy list, graceful-shutdown budget, tighter WebSocket frame limit" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: The image and the compose file

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `compose.yaml`, `src/bunsho/py.typed` (empty file)

**Interfaces:**
- Consumes: the `bunsho` console script (Plan 1B), config env keys `BUNSHO_*`, `GET /api/v1/health`.
- Produces: image `bunsho:local` (built by `docker compose build`), a compose service `bunsho` on host port `${BUNSHO_HOST_PORT:-8192}`, env file `${BUNSHO_ENV_FILE:-.env}`, named volume `bunsho-data` at `/data`, `./resources` mounted read-only at `/app/resources`. The smoke test (Task 4) relies on exactly these three variable names.

**Why these choices:** the jamdict-data-fix package brings a 325 MB SQLite database, so the image is large by nature; a multi-stage build keeps build tools and the uv cache out of it. The deck is mounted (spec: `resources/` read-only) so the GPL-3.0 asset is not baked into an image that may be pushed elsewhere. Python-only for now; Plan 2 adds a Node stage that builds the React app.

- [ ] **Step 1: Create `src/bunsho/py.typed`** (empty). Confirm `uv build` includes it (`unzip -l dist/*.whl | grep py.typed` on the built wheel).

- [ ] **Step 2: Create `.dockerignore`**

```
.git
.github
.venv
.claude
.superpowers
.pytest_cache
.mypy_cache
.ruff_cache
__pycache__
*.pyc
.coverage
coverage.xml
dist
data
docs
tests
scripts
resources
.env
.env.*
compose.yaml
Dockerfile
```

- [ ] **Step 3: Create `Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.13

# ---- build: resolve and install locked dependencies into a virtualenv ----
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first so this layer is cached until pyproject.toml or uv.lock change.
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ---- runtime: only the virtualenv, as a non-root user ----
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime
RUN groupadd --system --gid 10001 bunsho \
    && useradd --system --uid 10001 --gid bunsho --home-dir /nonexistent --shell /usr/sbin/nologin bunsho \
    && install -d -o bunsho -g bunsho -m 0750 /data
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BUNSHO_SERVER__HOST=0.0.0.0 \
    BUNSHO_PATHS__DATA_DIR=/data \
    BUNSHO_PATHS__RESOURCES_DIR=/app/resources
WORKDIR /app
USER bunsho
VOLUME ["/data"]
EXPOSE 8192
# Healthy = HTTP 200 (a first-run "degraded" answer is still 200). HTTP 503 raises and fails.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8192/api/v1/health', timeout=4)"]
STOPSIGNAL SIGTERM
# The launcher, never uvicorn directly: it runs one worker with proxy headers ignored.
ENTRYPOINT ["bunsho"]
```

- [ ] **Step 4: Create `compose.yaml`**

```yaml
# Bunshō: one service, one worker. Never add replicas or --workers (login throttle and build
# manager are in-process).
#
# Secrets live in an env file (default ./.env). Hashes contain "$": single-quote the value in
# the env file (BUNSHO_AUTH__PASSWORD_HASH='$argon2id$...'); compose leaves it untouched.
services:
  bunsho:
    build: .
    image: bunsho:local
    ports:
      - "${BUNSHO_HOST_PORT:-8192}:8192"
    env_file:
      - ${BUNSHO_ENV_FILE:-.env}
    volumes:
      - bunsho-data:/data
      - ./resources:/app/resources:ro
    restart: unless-stopped
    stop_grace_period: 60s
    read_only: true
    tmpfs:
      - /tmp
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL

volumes:
  bunsho-data:
```

- [ ] **Step 5: Build and run locally (Docker is available on the dev machine)**

```bash
docker compose build 2>&1 | tail -20
docker image ls bunsho:local
docker run --rm --entrypoint python bunsho:local -c "import bunsho, sys; print(bunsho.__file__, sys.version_info[:2])"
docker run --rm --entrypoint id bunsho:local            # uid=10001(bunsho)
```

Then create a scratch env file **outside the repo** (for example in a temp dir) with `BUNSHO_AUTH__USERNAME`, `BUNSHO_AUTH__PASSWORD_HASH` (single-quoted; generate with `uv run python -c "from pwdlib import PasswordHash; print(PasswordHash.recommended().hash('scratch-password'))"`) and `BUNSHO_AUTH__JWT_SECRET` (32+ random characters), then:

```bash
BUNSHO_ENV_FILE=<scratch env file> BUNSHO_HOST_PORT=18192 docker compose -p bunsho-scratch up -d --wait
curl -s -i http://127.0.0.1:18192/api/v1/health | head -1            # HTTP/1.1 200 ... "degraded" (no content.db yet)
docker compose -p bunsho-scratch logs | tail -15
docker compose -p bunsho-scratch ps                                    # State running, Health healthy
docker compose -p bunsho-scratch down -v
```

If the service does not start with `read_only: true` (the log will name the file it could not write), find out **which path** needs write access, fix it with a targeted `tmpfs:` or volume if it is a scratch location, and if it is something structural (for example the jamdict package writing next to its database) remove `read_only: true` and record the reason in a comment in `compose.yaml` and in the report. Also verify: `docker compose config` prints without warnings; `docker inspect` shows the healthcheck; `docker compose ... stop` completes in well under 35 s when idle.

- [ ] **Step 6: Commit**

```bash
git add Dockerfile .dockerignore compose.yaml src/bunsho/py.typed
git commit -m "feat: Python-only Docker image, compose service and py.typed marker" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Container smoke test (script + CI job)

**Files:**
- Create: `scripts/smoke_test.py`
- Modify: `pyproject.toml` (ruff per-file ignores for `scripts/**`), `.github/workflows/ci.yml` (job `smoke`), `.github/dependabot.yml` (docker ecosystem)

**Interfaces:**
- Consumes: `compose.yaml` variables `BUNSHO_ENV_FILE`, `BUNSHO_HOST_PORT` (Task 3); the HTTP API of Plan 1B; `pwdlib` (already a dependency) to make a password hash.
- Produces: `uv run python scripts/smoke_test.py` (exit 0 = pass). Environment overrides: `BUNSHO_SMOKE_PORT` (default 18192), `BUNSHO_SMOKE_KEEP=1` (leave the stack up for debugging). Compose project name `bunsho-smoke`.

**What it proves (the spec's verification list):** the image builds, the container reaches healthy, login works, the content build from the **real deck and real jamdict database** yields 7,734 vocab / 3,088 kanji / 208 kana, `content.db` and `progress.db` survive a container restart, and a refresh token issued before the restart still works.

- [ ] **Step 1: Create `scripts/smoke_test.py`**

```python
"""Smoke-test the Bunshō container end to end (build, start, log in, build content, restart).

Usage: ``uv run python scripts/smoke_test.py``. Needs Docker with Compose v2 and the real deck in
``resources/``. Exits non-zero on the first failed expectation and always tears the stack down
(set ``BUNSHO_SMOKE_KEEP=1`` to leave it running).
"""

from __future__ import annotations

import json
import os
import secrets
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
BASE = f"http://127.0.0.1:{PORT}/api/v1"
USERNAME = "smoke"
EXPECTED_COUNTS = {"vocab": 7734, "kanji": 3088, "kana": 208}
HEALTHY_TIMEOUT_SECONDS = 180
BUILD_TIMEOUT_SECONDS = 600


class SmokeFailure(AssertionError):
    """An expectation of the smoke test did not hold."""


def log(message: str) -> None:
    """Write a progress line to stderr."""
    sys.stderr.write(f"[smoke] {message}\n")


def compose(env_file: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run ``docker compose`` for the smoke project."""
    env = {**os.environ, "BUNSHO_ENV_FILE": str(env_file), "BUNSHO_HOST_PORT": str(PORT)}
    return subprocess.run(  # noqa: S603 - fixed argument list, no shell
        ["docker", "compose", "-p", PROJECT, "-f", str(ROOT / "compose.yaml"), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=check,
    )


def request(
    method: str, path: str, *, token: str | None = None, body: dict[str, Any] | None = None
) -> tuple[int, Any]:
    """Call the API and return ``(status, json body)`` without raising on HTTP errors."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)  # noqa: S310 - http
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as response:  # noqa: S310 - http, localhost
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"null")


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
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            status = 0
        if status == 200:
            return
        time.sleep(2)
    raise SmokeFailure(f"service not healthy after {HEALTHY_TIMEOUT_SECONDS}s")


def login(password: str) -> dict[str, str]:
    """Log in and return the token pair."""
    status, body = request("POST", "/auth/login", body={"username": USERNAME, "password": password})
    expect(status == 200, f"login returned {status}")
    return {"access": body["access_token"], "refresh": body["refresh_token"]}


def build_content(access: str) -> None:
    """Start a full content build and wait for it to succeed."""
    status, task = request("POST", "/admin/content/build", token=access, body={})
    expect(status == 202, f"build start returned {status}: {task}")
    deadline = time.monotonic() + BUILD_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        status, task = request("GET", f"/admin/content/build/{task['task_id']}", token=access)
        expect(status == 200, f"build status returned {status}")
        if task["state"] != "running":
            expect(task["state"] == "succeeded", f"build ended {task['state']}: {task.get('error')}")
            return
        time.sleep(3)
    raise SmokeFailure(f"content build still running after {BUILD_TIMEOUT_SECONDS}s")


def expect_summary(access: str) -> None:
    """Check the content summary matches the real deck."""
    status, summary = request("GET", "/content/summary", token=access)
    expect(status == 200, f"summary returned {status}")
    expect(summary["built"] is True, "summary says content is not built")
    got = {key: summary[key] for key in EXPECTED_COUNTS}
    expect(got == EXPECTED_COUNTS, f"content counts {got} != {EXPECTED_COUNTS}")


def run(env_file: Path) -> None:
    """Drive the whole scenario against a running stack."""
    password = env_file.parent.joinpath("password").read_text(encoding="utf-8")
    log("waiting for the service to become healthy")
    wait_healthy()
    status, health = request("GET", "/health")
    expect(health["status"] in {"ok", "degraded"}, f"unexpected health {health}")
    expect(request("GET", "/content/summary")[0] == 401, "summary must require a token")
    expect(
        request("POST", "/auth/login", body={"username": USERNAME, "password": "wrong"})[0] == 401,
        "wrong password must be rejected",
    )
    tokens = login(password)
    log("building content from the real deck (about a minute)")
    build_content(tokens["access"])
    expect_summary(tokens["access"])
    log("restarting the container")
    compose(env_file, "restart", "bunsho")
    wait_healthy()
    status, refreshed = request("POST", "/auth/refresh", body={"refresh_token": tokens["refresh"]})
    expect(status == 200, f"refresh after restart returned {status}")
    expect_summary(refreshed["access_token"])
    status, health = request("GET", "/health")
    expect(health["status"] == "ok", f"health after build and restart is {health['status']}")
    log("PASS")


def main() -> int:
    """Build the image, run the scenario and tear the stack down."""
    keep = os.environ.get("BUNSHO_SMOKE_KEEP") == "1"
    with tempfile.TemporaryDirectory(prefix="bunsho-smoke-") as tmp:
        folder = Path(tmp)
        password = secrets.token_urlsafe(16)
        (folder / "password").write_text(password, encoding="utf-8")
        env_file = folder / "smoke.env"
        env_file.write_text(
            f"BUNSHO_AUTH__USERNAME={USERNAME}\n"
            f"BUNSHO_AUTH__PASSWORD_HASH='{PasswordHash.recommended().hash(password)}'\n"
            f"BUNSHO_AUTH__JWT_SECRET={secrets.token_urlsafe(48)}\n",
            encoding="utf-8",
        )
        try:
            log("building the image and starting the stack")
            compose(env_file, "up", "-d", "--build")
            run(env_file)
        except (SmokeFailure, subprocess.CalledProcessError) as exc:
            log(f"FAIL: {exc}")
            if isinstance(exc, subprocess.CalledProcessError):
                log(exc.stderr or "")
            log(compose(env_file, "logs", "--tail", "80", check=False).stdout)
            return 1
        finally:
            if not keep:
                compose(env_file, "down", "-v", check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Confirm the JSON field names against the actual schemas before trusting the snippet: `task_id`/`state`/`error` in `BuildStatusResponse`, `built`/`kana`/`kanji`/`vocab` in `ContentSummaryResponse`, `status` in `HealthReport`, `access_token`/`refresh_token` in the token response (`src/bunsho/api/schemas.py`); adjust the script, not the API, if they differ. Read the password from the temp folder as shown, or pass it through a variable if that is simpler (the point is that the script generates its own credentials and never uses anything from the repo or a developer `.env`).

- [ ] **Step 2: Allow the script's subprocess and assert usage in ruff**

In `pyproject.toml` under `[tool.ruff.lint.per-file-ignores]` add:

```toml
"scripts/**" = ["D", "S101", "S310", "S603", "S607"]
```

(`S603`/`S310` are also silenced inline where they occur; keep the inline `noqa` comments only if ruff still reports them without the per-file ignore, otherwise remove them so there is no unused-`noqa` noise.) `uv run ruff check .` and `uv run ruff format --check .` must pass with `scripts/` included. mypy stays scoped to `src/`.

- [ ] **Step 3: Run the smoke test locally**

Run: `uv run python scripts/smoke_test.py` — expect the log to end with `[smoke] PASS` in a few minutes (image build, then a ~30-60 s content build). If Docker Desktop is not running, start it first. Run it a second time to check the tear-down left nothing behind (`docker compose -p bunsho-smoke ps -a` is empty; `docker volume ls | grep bunsho-smoke` is empty). If a step fails, fix the cause (image, compose, or script), not the assertion.

- [ ] **Step 4: Add the CI job and the Dependabot entry**

In `.github/workflows/ci.yml` append (same `uv` setup step and pins as the other jobs):

```yaml
  smoke:
    runs-on: ubuntu-latest
    timeout-minutes: 25
    needs: [test]
    steps:
      - uses: actions/checkout@v7

      - name: Install uv
        uses: astral-sh/setup-uv@bec219d24cd3e171d82865faccec33120bb574f4 # v10.1.0
        with:
          version: ${{ env.UV_VERSION }}
          enable-cache: true

      - name: Install dependencies
        run: uv sync --extra dev --locked

      - name: Container smoke test (real deck, real jamdict database)
        run: uv run python scripts/smoke_test.py

      - name: Compose logs on failure
        if: failure()
        run: docker compose -p bunsho-smoke logs --tail 200 || true
```

The header comment of `ci.yml` says the container smoke test arrives with Plan 1C: update it. In `.github/dependabot.yml` add a `docker` ecosystem entry (`directory: "/"`, weekly, limit 5, cooldown 7 days, `commit-message.prefix: "chore(deps)"`) and remove the "docker" line from its "Not configured yet" header comment.

Run `uv tool run --from actionlint-py actionlint .github/workflows/ci.yml` — no findings.

- [ ] **Step 5: Gates and commit**

`uv run pytest tests -q` (unchanged), ruff, mypy, bandit green.

```bash
git add scripts/smoke_test.py pyproject.toml .github/workflows/ci.yml .github/dependabot.yml
git commit -m "feat: container smoke test script and CI job" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Tooling and policy (pre-commit, CI-fails-not-skips, bandit config, changelog)

**Files:**
- Create: `.pre-commit-config.yaml`, `CHANGELOG.md`, `tests/unit/test_ci_skip_policy.py`
- Modify: `tests/conftest.py`, `.github/workflows/ci.yml`, `.github/workflows/release.yml` (bandit command only)

**Interfaces:**
- Consumes: the `integration` marker (`pyproject.toml`), `[tool.bandit]` in `pyproject.toml`.
- Produces: under an environment variable `CI` (any non-empty value, which GitHub Actions always sets) an `integration`-marked test that is **skipped** is reported as **failed**; the hook `pytest_runtest_makereport` in `tests/conftest.py`.

**Why:** the real-deck and real-jamdict integration tests `pytest.skip` when their inputs are missing, which is right on a developer laptop and wrong in CI, where a silently skipped integration suite looks green. `bandit` only reads `[tool.bandit]` from `pyproject.toml` when given `-c pyproject.toml`.

- [ ] **Step 1: Write the failing test** `tests/unit/test_ci_skip_policy.py`:

```python
"""Integration tests must fail, not skip, when the CI environment variable is set."""

import pytest

pytest_plugins = ["pytester"]

_TEST_FILE = """
import pytest

@pytest.mark.integration
def test_needs_the_deck():
    pytest.skip("deck not available")

def test_plain_skip_is_left_alone():
    pytest.skip("not an integration test")
"""


def _project(pytester: pytest.Pytester) -> None:
    pytester.makeini("[pytest]\nmarkers =\n    integration: cross-boundary test\n")
    pytester.makeconftest("from tests.conftest import pytest_runtest_makereport  # noqa: F401\n")
    pytester.makepyfile(test_sample=_TEST_FILE)


def test_a_skipped_integration_test_fails_under_ci(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CI", "true")
    _project(pytester)
    result = pytester.runpytest()
    result.assert_outcomes(failed=1, skipped=1)
    result.stdout.fnmatch_lines(["*skipped under CI*deck not available*"])


def test_a_skipped_integration_test_stays_skipped_locally(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CI", raising=False)
    _project(pytester)
    pytester.runpytest().assert_outcomes(skipped=2)
```

`pytest_plugins` is only allowed at a test module's top level like this; if the installed pytest rejects it, enable the plugin with `pytester` via `-p pytester` in `addopts` for this run instead (`pytest.ini_options.addopts`), and remove the line. Run it: FAIL (`pytest_runtest_makereport` not defined in `tests/conftest.py`).

- [ ] **Step 2: Implement the hook** in `tests/conftest.py` (keep the existing fixture re-exports):

```python
import os
from collections.abc import Generator
from typing import Any

import pytest


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, Any, None]:
    """Turn a skipped ``integration`` test into a failure when ``CI`` is set."""
    outcome = yield
    report = outcome.get_result()
    if (
        report.skipped
        and os.environ.get("CI")
        and item.get_closest_marker("integration") is not None
        and call.when in {"setup", "call"}
    ):
        reason = report.longrepr[2] if isinstance(report.longrepr, tuple) else str(report.longrepr)
        report.outcome = "failed"
        report.longrepr = f"integration test skipped under CI (its inputs must exist there): {reason}"
```

Run the new tests until green. Then confirm the effect on the real suite: `CI=1 uv run pytest tests/integration -q --no-cov` passes with the deck and jamdict present (nothing skipped). Also run the whole suite once with `CI=1` and once without: same pass count.

- [ ] **Step 3: bandit uses the project config**

Change every `bandit -r src/ -l` to `bandit -c pyproject.toml -r src/ -l` in `.github/workflows/ci.yml` and `.github/workflows/release.yml` (release runs only ruff/mypy/pytest today: add nothing there if bandit is absent). Run `uv run bandit -c pyproject.toml -r src/ -l` locally: same result as before (no issues).

- [ ] **Step 4: Create `.pre-commit-config.yaml`**

Find the ruff version in `uv.lock` (`uv pip show ruff` or `grep -A2 'name = "ruff"' uv.lock`) and use the matching `astral-sh/ruff-pre-commit` tag as `rev`; find the current `pre-commit/pre-commit-hooks` release with `gh api repos/pre-commit/pre-commit-hooks/releases/latest --jq .tag_name`.

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: <latest tag>
    hooks:
      - id: check-yaml
      - id: check-toml
      - id: check-merge-conflict
      - id: check-added-large-files
        args: ["--maxkb=3000"]
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: <tag matching uv.lock>
    hooks:
      - id: ruff
        args: ["--fix"]
      - id: ruff-format
  - repo: local
    hooks:
      - id: mypy
        name: mypy (strict, src)
        entry: uv run mypy src/
        language: system
        pass_filenames: false
        types: [python]
      - id: bandit
        name: bandit (medium+ severity, src)
        entry: uv run bandit -c pyproject.toml -r src/ -l
        language: system
        pass_filenames: false
        types: [python]
```

Run `uv run pre-commit run --all-files`. It must pass (fix or scope any hook that flags existing files, for example exclude `uv.lock` or the `resources/` deck from `check-added-large-files` if needed, with a comment). Do not run `pre-commit install` (that edits `.git/hooks`, a per-clone action; the README documents it).

- [ ] **Step 5: Create `CHANGELOG.md`** in Keep a Changelog format with an `## [Unreleased]` section listing, under **Added**, the user-visible capabilities of Plans 1A, 1B and 1C (content pipeline and deck import; authenticated API with health, config-check, content build and WebSocket progress; progress database with backup-before-migrate; Docker image, compose file and CI smoke test), and a link to the Keep a Changelog and Semantic Versioning conventions. Do not invent version numbers or dates.

- [ ] **Step 6: Gates and commit**

`uv run pytest tests -q`, ruff check/format, mypy, bandit (with `-c`), `uv run pre-commit run --all-files`, `uv tool run --from actionlint-py actionlint .github/workflows/*.yml` all green.

```bash
git add .pre-commit-config.yaml CHANGELOG.md tests/conftest.py tests/unit/test_ci_skip_policy.py .github/workflows/ci.yml .github/workflows/release.yml
git commit -m "chore: pre-commit, fail-not-skip for integration tests in CI, bandit config, changelog" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Documentation

**Files:**
- Modify: `README.md`, `TODO.md`

**Interfaces:**
- Consumes: everything above.
- Produces: README sections "Running with Docker" and "Development"; corrected proxy/limits text; TODO items moved or closed.

- [ ] **Step 1: README, "Running with Docker"** (place after "Running the service"; keep the existing sections' accuracy):

Cover, in this order and only what is true of the files in this repo:
1. Prerequisites: Docker with Compose v2; the deck is already in `resources/` (it is committed); an env file with the three required settings.
2. Create `.env` (same three settings as the "Running the service" section; state again that the hash contains `$` and must be single-quoted in an env file, `$$` inside YAML).
3. `docker compose up -d --build`, then `docker compose ps` (wait for `healthy`), the same first-run flow as the non-Docker section (login, config-check, POST build, poll status), and where the data lives (named volume `bunsho-data` at `/data`: `progress.db`, `content.db`, `backups/`; how to back up the volume, for example `docker run --rm -v bunsho-data:/data -v "$PWD":/backup busybox tar czf /backup/bunsho-data.tgz -C /data .`).
4. Upgrading: `git pull && docker compose up -d --build`; the service migrates `progress.db` at startup after taking a backup in `backups/`; how to restore a backup (stop the service, copy a `backups/progress-...db` over `progress.db`).
5. Stopping: `docker compose stop` waits up to 60 s so a build that is running finishes before the container exits (a build cannot be interrupted midway; `content.db` is only replaced when it completes).
6. Limits and networking: one replica only; the container listens on 0.0.0.0 inside the network and compose publishes `8192`; to keep it off the LAN publish `127.0.0.1:8192:8192` via a compose override; no HTTPS in the app.
7. Trusted proxies: replace the "proxy or Docker NAT" paragraph. Without `BUNSHO_SERVER__TRUSTED_PROXIES` proxy headers are ignored and the throttle keys on the TCP peer (behind a proxy or Docker Desktop NAT all clients share one bucket). If an nginx or similar proxy fronts the service, set `BUNSHO_SERVER__TRUSTED_PROXIES` to that proxy's address(es) or network (never `*`) and make the proxy **overwrite** `X-Forwarded-For` with the client address (nginx: `proxy_set_header X-Forwarded-For $remote_addr;`); with an entry configured, the address the proxy reports is trusted, so list only real proxies. Linux Docker with a published port preserves client addresses; Docker Desktop (Mac, Windows) shows the gateway address.
8. Smoke test: `uv run python scripts/smoke_test.py` (what it checks, that it needs Docker and takes a few minutes).

- [ ] **Step 2: README, "Development"**: `uv sync --extra dev`; the five local checks (ruff check, ruff format --check, mypy src/, `bandit -c pyproject.toml -r src/ -l`, pytest with coverage); `uv run pre-commit install` (optional, per clone); `CI=1` makes skipped integration tests fail (how to reproduce CI locally).

- [ ] **Step 3: `TODO.md`**: remove or tick items this plan delivered (Docker, compose, CI rewrite, pre-commit, py.typed, temp-file sweep, migration lock, startup errors, proxy story) and add anything discovered while doing them. Leave the Plan 2 and later items (OpenAPI quality, typed `unleveled_kanji` in the summary, WAL pragma and `foreign_keys`, `downgrade()` test, stateless-refresh logout, CORS methods, unauthenticated WebSocket cap, backup retention) in place; add any of those that are not yet listed.

- [ ] **Step 4: Verify the docs against reality**

Copy each command block from the new README sections into a scratch shell and run it (with the scratch env file from Task 3); fix the README, not the commands. `uv run ruff format --check .` must still pass (markdown is excluded from formatting). Commit:

```bash
git add README.md TODO.md
git commit -m "docs: Docker, trusted proxies, development workflow" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7 (controller, not part of the pull request): agent-config cleanup

`.claude/` is git-ignored, so this is a local-only edit performed by the controller after Task 6, never staged.

- Rewrite `.claude/skills/db-migration/SKILL.md` for Bunshō: SQLite `progress.db`, Alembic run programmatically from `src/bunsho/db/migrate.py` with migrations in `src/bunsho/db/migrations/versions/`, SQLAlchemy models in `src/bunsho/db/models.py`, the backup-before-migrate rule, batch mode for SQLite, review steps (downgrade path, destructive operations, dry run with `alembic upgrade head --sql`, backup restore), and the `tests/unit/db` patterns. Remove every Jidou, Postgres and `asyncpg` reference.
- Replace "Jidou" and the example headings in `.claude/skills/release-notes/SKILL.md` with Bunshō equivalents (repository `jamesbconner/Bunsho`, conventional commits, `CHANGELOG.md` sections).
- `.claude/skills/check-pr/` (`SKILL.md`, `.sh`, `.ps1`): remove the hardcoded `jamesbconner/Jidou`; derive the repository with `gh repo view --json nameWithOwner`; mention Cursor Bugbot review comments and the CI checks that exist (`lint`, `test` matrix, `build`, `smoke`).
- Clean the Jidou-related entries out of `.claude/settings.local.json`.
- **Do not edit** `.claude/CLAUDE.md` or the guideline documents (`llm-patterns.md`, `react.md`, `ml-data.md`, `fastapi.md`, `packaging.md`) without the user's approval: report that they still carry Jidou, TMDB, Celery and Redis rules that do not apply, and ask.
- Verify with `grep -ril "jidou\|tmdb" .claude/skills .claude/settings.local.json` (expect no matches) and report what changed.

---

## Self-review

**Spec coverage.** Docker: multi-stage, non-root, `HEALTHCHECK` on `/api/v1/health`, one compose service on 8192, volumes `/data` rw and `resources/` ro (Task 3); the Node stage is deliberately left to Plan 2. CI: rewrite done in the repository-config PR; the compose smoke test (login, real-deck content build, health) is Task 4 (spec "Testing & delivery" and "Verification": restart persistence and a token that survives a restart are asserted). Skills cleanup (spec "Repo cleanup" item 3) is Task 7 (local, because `.claude/` is ignored). Everything Plan 1B's final review carried forward is covered: migration lock, actionable startup errors and writability check, temp sweep, graceful-shutdown budget, trusted-proxy story, absolute container paths (Dockerfile env), non-root data volume, WebSocket frame limit (Task 2), `py.typed`, pre-commit, fail-not-skip, bandit `-c` (Tasks 3 and 5). Not covered on purpose: an unauthenticated-socket cap and backup retention (recorded in `TODO.md`), OpenAPI quality and the other Plan 2 items.

**Placeholder scan.** The only deliberately open values are version pins that must be read from the repository at execution time (`filelock` release, `pre-commit-hooks` and `ruff-pre-commit` tags); each step says how to find them.

**Type and name consistency.** `MIGRATION_LOCK_TIMEOUT_SECONDS`, `remove_stale_temp_files`, `StartupError` (Task 1); `trusted_proxies`, `GRACEFUL_SHUTDOWN_SECONDS`, `WS_MAX_MESSAGE_BYTES` (Task 2); `BUNSHO_ENV_FILE`, `BUNSHO_HOST_PORT`, project `bunsho-smoke`, volume `bunsho-data` (Tasks 3, 4, 6) are spelled identically wherever they recur.
