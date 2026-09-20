# Bunshō Plan 1B: Authenticated API Service

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A runnable, authenticated FastAPI service (start it with `bunsho` or `uvicorn`) that owns the migrated `progress.db`, reports health, and builds `content.db` in the background with live WebSocket progress.

**Architecture:** A FastAPI app factory (`create_app(ServiceConfig)`) whose lifespan runs Alembic migrations (with a backup first), then wires a `Services` container: `ProgressDatabase` (async SQLAlchemy), the Plan 1A `Context`, an `AuthService` (argon2 password check, JWT access and refresh tokens), a login throttle, and a single-flight `BuildTaskManager` that runs the Plan 1A `ContentBuildOrchestrator` in a worker thread and fans progress events out to WebSocket subscribers. Routers live under `/api/v1`.

**Tech Stack:** Python 3.13, FastAPI, uvicorn, SQLAlchemy 2.0 (async, aiosqlite), Alembic (sync stdlib sqlite driver for migrations), PyJWT, pwdlib[argon2], httpx2 (Starlette's TestClient now asks for `httpx2`; plain `httpx` works but emits a deprecation warning), pytest.

**Spec:** `docs/superpowers/specs/2026-09-19-bunsho-foundation-and-review-engine-design.md`. Plan 1A (merged) provides the library this service wraps: `docs/superpowers/plans/2026-09-19-bunsho-1a-foundation-content-pipeline.md`.

**Plan series:** 1A (done, merged) → **1B (this plan: API)** → 1C (delivery: Dockerfile, compose, CI rewrite, skills cleanup, tooling) → 2 (FSRS review engine + React UI).

## Global Constraints

- Python `>=3.13`; build backend `hatchling`; `uv`; display name **Bunshō**, ASCII slug **`bunsho`**; MIT license.
- **No CLI** (no click/rich). The `bunsho` console script is a thin uvicorn launcher. No `print`; `logging` with `key=value` messages. Never log passwords, tokens or the JWT secret.
- Google-style docstrings on public items; modern type syntax; mypy strict; ruff (lint + format), bandit clean; coverage `>= 90%`.
- API prefix `/api/v1`; default port **8192**; **never port 8000** (config validation rejects it). Default bind host `127.0.0.1` (Docker sets `0.0.0.0` in Plan 1C).
- Auth: single local user from config; argon2 password hash; **JWT HS256**, access token TTL 15 min, refresh token TTL 30 days (both configurable); every REST route and the WebSocket require a valid access token except `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh` and `GET /api/v1/health`.
- Config precedence unchanged: TOML file < `.env` < real environment; keys `BUNSHO_<SECTION>__<KEY>`; all validation errors reported together; service secrets are **required** (no defaults): `auth.username`, `auth.password_hash`, `auth.jwt_secret` (at least 32 characters).
- CORS is explicit: origins come from `server.cors_origins` (comma separated); no wildcard; no CORS middleware when empty.
- `progress.db` is the irreplaceable database: migrations run at startup, preceded by a timestamped consistent backup whenever an existing database needs migrating; a migration failure aborts startup (fail fast). `content.db` missing is a normal first-run state (health `degraded`), not an error.
- Every state-changing operation supports `dry_run` where it makes sense (the content build endpoint does).
- Tests: shared builders/fixtures live in `tests/base.py`; new behaviour needs tests; the suite must behave identically on ubuntu, windows and macos; no `pytest-asyncio` (use `asyncio.run` inside sync tests and FastAPI's sync `TestClient`).
- Test snippets in this plan that begin with `import` lines show imports that belong in the **top import block** of the file they extend (or create): merge them there (ruff `I001`/`E402` will flag anything left mid-file), and drop any import that ends up unused.
- Commit messages: conventional commits, two `-m` arguments so the `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` trailer is its own paragraph; stage explicit paths only; never stage `.gitignore`, `.github/`, `.python-version`.
- Plan 1A facts the code relies on: `AppConfig` (`content_db_path`, `progress_db_path`, `deck_path`, `deck_sha256`, `jamdict_db`, `log_level`); `Context(config, logger, dry_run, kanji_source, kanji_catalog, content_repo)` with `refresh_content_repo()`; `create_context(config, dry_run=False, logger=None)`; `create_content_build_orchestrator(ctx)`; `ContentBuildOrchestrator.build(deck_path, target, *, dry_run, on_progress)` returning `BuildReport`; `BuildProgress(stage, current, total)`; `ContentRepository` (`counts()`, `meta()`, `verify_schema()`, `list_kanji(level, *, unleveled)`); `ContentWriter`; `JamdictService` (per-thread connections, thread-safe); `tests/base.py` (`make_vocab`, `make_kanji_details`, `FakeKanjiSource`, fixtures `app_config`, `quiet_logger`) and `tests/apkg_builder.py` (`build_apkg`, `note`).

## Rulings baked into this plan (controller decisions, challenge them in review)

1. Migrations run through the **stdlib sqlite driver** (sync SQLAlchemy engine) at startup; the app itself uses `aiosqlite`. No async `env.py`.
2. Migration scripts ship **inside the package** (`src/bunsho/db/migrations/`); the Alembic `Config` is built in code (no `alembic.ini` needed at runtime); a repo-root `alembic.ini` exists only for developers running `alembic revision`.
3. Service settings (server/auth) are a separate `ServiceConfig` that wraps the unchanged Plan 1A `AppConfig`, so Plan 1A behaviour and tests stay untouched.
4. Timestamps in `progress.db` are ISO-8601 UTC **text**, not SQLite datetimes (no timezone ambiguity).
5. Refresh tokens are stateless (no server-side revocation list): logging out is client-side; rotating `auth.jwt_secret` invalidates every token. Documented limitation.
6. WebSocket authentication is a **first message** (`{"type": "auth", "token": "<access token>"}` within 5 seconds), not a query-string token (URLs get logged).
7. Only one content build may run at a time (single-flight); a second `POST` gets 409.
8. Docker, the CI rewrite, and the `.claude/skills` Jidou cleanup are **Plan 1C** (the `.gitignore` question needs the user first).

## File Structure

```
pyproject.toml, alembic.ini                               (Task 1, Task 3)
src/bunsho/config/service.py, loader.py, normalizer.py    (Task 1)
src/bunsho/services/content_repository.py, factories.py,
  logging_setup.py, orchestration/content_build.py        (Task 2 edits)
src/bunsho/db/{__init__,models,engine,migrate}.py         (Task 3)
src/bunsho/db/migrations/{env.py,script.py.mako,versions/0001_initial.py}  (Task 3)
src/bunsho/services/{auth,login_throttle}.py              (Task 4)
src/bunsho/orchestration/build_tasks.py                   (Task 5)
src/bunsho/services/{health,config_check}.py              (Task 6)
src/bunsho/api/{__init__,schemas,services,deps,app}.py    (Task 6)
src/bunsho/api/routers/{__init__,health,auth,admin,content,ws}.py  (Tasks 6-8)
src/bunsho/main.py                                        (Task 9)
tests/unit/config/test_service_config.py, tests/unit/db/*, tests/unit/services/*, tests/unit/api/*, tests/integration/test_api_end_to_end.py
```

---

### Task 1: Dependencies, service configuration, loader hardening

**Files:**
- Modify: `pyproject.toml` (via `uv add`), `src/bunsho/config/loader.py`, `src/bunsho/config/normalizer.py`, `src/bunsho/config/settings.py`, `src/bunsho/config/__init__.py`
- Create: `src/bunsho/config/service.py`
- Test: `tests/unit/config/test_service_config.py`; extend `tests/unit/config/test_loader.py`, `tests/unit/config/test_normalizer.py`, `tests/unit/config/test_settings.py`

**Interfaces:**
- Consumes: `ConfigNormalizer`, `ConfigError`, `AppConfig`, `validate_config`, `load_config` (Plan 1A).
- Produces (`bunsho.config.service`): `MIN_JWT_SECRET_LENGTH = 32`, `RESERVED_PORT = 8000`; frozen slots dataclasses `ServerSettings(host: str, port: int, cors_origins: tuple[str, ...])`, `AuthSettings(username: str, password_hash: str, jwt_secret: str, access_ttl_minutes: int, refresh_ttl_days: int)`, `ServiceConfig(app: AppConfig, server: ServerSettings, auth: AuthSettings)`; `validate_service_config(cfg: ConfigNormalizer) -> list[str]` (app errors + server/auth errors, all together); `load_service_config(cfg: ConfigNormalizer) -> ServiceConfig` (raises `ConfigError` listing every error). Defaults: host `127.0.0.1`, port `8192`, cors origins empty, access TTL 15, refresh TTL 30; `auth.*` secrets have no defaults (empty values are errors).
- Behaviour changes (Plan 1A carry-forward): `load_config` wraps a missing or malformed TOML file and a missing explicit `.env` file in `ConfigError`; `ConfigNormalizer` raises `ConfigError` for a top-level TOML value that is not a table; `validate_config` also rejects a `data_dir` that exists and is not a directory.

- [ ] **Step 1: Add dependencies**

```bash
unset VIRTUAL_ENV
uv add fastapi "uvicorn[standard]" "sqlalchemy[asyncio]" aiosqlite alembic pyjwt "pwdlib[argon2]"
uv add --optional dev httpx2
uv sync --extra dev
```
Expected: `pyproject.toml` and `uv.lock` updated; `uv run python -c "import fastapi, uvicorn, sqlalchemy, aiosqlite, alembic, jwt, pwdlib, httpx2"` prints nothing.

- [ ] **Step 2: Write the failing tests**

`tests/unit/config/test_service_config.py`:

```python
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
```

Append to `tests/unit/config/test_loader.py`:

```python
import pytest

from bunsho.config.normalizer import ConfigError


def test_missing_and_malformed_files_raise_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(config_file=tmp_path / "missing.toml", environ={})
    bad = tmp_path / "bad.toml"
    bad.write_text("[unclosed\n")
    with pytest.raises(ConfigError, match="not valid TOML"):
        load_config(config_file=bad, environ={})
    with pytest.raises(ConfigError, match="not found"):
        load_config(env_file=tmp_path / "missing.env", environ={})
```

Append to `tests/unit/config/test_normalizer.py`:

```python
def test_top_level_scalar_is_a_config_error() -> None:
    with pytest.raises(ConfigError, match="must be a table"):
        ConfigNormalizer({"x": 1})  # type: ignore[dict-item]
```

Append to `tests/unit/config/test_settings.py`:

```python
def test_data_dir_must_not_be_a_file(tmp_path: Path) -> None:
    blocker = tmp_path / "data"
    blocker.write_text("not a directory")
    errors = validate_config(ConfigNormalizer({"paths": {"data_dir": str(blocker)}}))
    assert any("data_dir" in e for e in errors)
```

- [ ] **Step 3: Run them to verify they fail**

Run: `uv run pytest tests/unit/config -q`
Expected: FAIL (`ModuleNotFoundError: bunsho.config.service`, and the new loader/normalizer/settings tests fail on missing behaviour).

- [ ] **Step 4: Implement**

`src/bunsho/config/service.py`:

```python
"""Service-level configuration: HTTP server and authentication."""

from __future__ import annotations

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


def _int(
    cfg: ConfigNormalizer, section: str, key: str, fallback: int, errors: list[str]
) -> int:
    try:
        return cfg.get_int(section, key, fallback)
    except ConfigError as exc:
        errors.append(str(exc))
        return fallback


def _origins(cfg: ConfigNormalizer) -> tuple[str, ...]:
    raw = cfg.get_string("server", "cors_origins")
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def validate_service_config(cfg: ConfigNormalizer) -> list[str]:
    """Validate library, server and auth settings; return every problem found."""
    errors = validate_config(cfg)
    if not cfg.get_string("server", "host", "127.0.0.1").strip():
        errors.append("[server] host must not be empty")
    port = _int(cfg, "server", "port", 8192, errors)
    if port == RESERVED_PORT or not 1024 <= port <= 65535:
        errors.append(f"[server] port={port} must be between 1024 and 65535 and not {RESERVED_PORT}")
    for origin in _origins(cfg):
        if not origin.startswith(("http://", "https://")):
            errors.append(f"[server] cors_origins entry {origin!r} must start with http:// or https://")
    if not cfg.get_string("auth", "username").strip():
        errors.append("[auth] username is required")
    if not cfg.get_string("auth", "password_hash").startswith(_ARGON2_PREFIX):
        errors.append("[auth] password_hash is required and must be an argon2 hash")
    if len(cfg.get_string("auth", "jwt_secret")) < MIN_JWT_SECRET_LENGTH:
        errors.append(f"[auth] jwt_secret is required and must be at least {MIN_JWT_SECRET_LENGTH} characters")
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
        ),
        auth=AuthSettings(
            username=cfg.get_string("auth", "username").strip(),
            password_hash=cfg.get_string("auth", "password_hash"),
            jwt_secret=cfg.get_string("auth", "jwt_secret"),
            access_ttl_minutes=cfg.get_int("auth", "access_ttl_minutes", 15),
            refresh_ttl_days=cfg.get_int("auth", "refresh_ttl_days", 30),
        ),
    )
```

Edit `src/bunsho/config/loader.py`: replace the body of `load_config` between `file_values` and `return` with:

```python
    file_values: dict[str, Any] = {}
    if config_file is not None:
        try:
            with config_file.open("rb") as handle:
                file_values = tomllib.load(handle)
        except FileNotFoundError as exc:
            raise ConfigError(f"config file not found: {config_file}") from exc
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"config file {config_file} is not valid TOML: {exc}") from exc
    merged_env: dict[str, str] = {}
    if env_file is not None:
        if not env_file.is_file():
            raise ConfigError(f"env file not found: {env_file}")
        merged_env.update({k: v for k, v in dotenv_values(env_file).items() if v is not None})
    merged_env.update(os.environ if environ is None else environ)
    return ConfigNormalizer(file_values).merge_env(merged_env)
```
and import `ConfigError` alongside `ConfigNormalizer` (`from bunsho.config.normalizer import ConfigError, ConfigNormalizer`).

Edit `src/bunsho/config/normalizer.py` `ConfigNormalizer.__init__`: inside the `for section, values in (raw or {}).items():` loop, before `bucket = ...`, add:

```python
            if not isinstance(values, Mapping):
                raise ConfigError(f"top-level key {section!r} must be a table, not {values!r}")
```

Edit `src/bunsho/config/settings.py` `validate_config`: after the `jamdict` check, add:

```python
    data_dir = cfg.get_string("paths", "data_dir", "data")
    if Path(data_dir).exists() and not Path(data_dir).is_dir():
        errors.append(f"[paths] data_dir={data_dir!r} exists and is not a directory")
```

Edit `src/bunsho/config/__init__.py`: also export `ServiceConfig`, `ServerSettings`, `AuthSettings`, `load_service_config`, `validate_service_config` from `bunsho.config.service` (keep `__all__` sorted).

- [ ] **Step 5: Run tests and gates**

Run: `uv run pytest tests -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run bandit -r src/ -l`
Expected: all PASS (the Plan 1A suite still passes). If `ruff format` rewraps the long lines in `service.py`, accept it.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/bunsho/config tests/unit/config
git commit -m "feat(config): server and auth settings, harden config loading" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Plan 1A hardening carry-forward

Four small fixes to merged Plan 1A code that the API needs before it can rely on it. All were found in Plan 1A's final review.

**Files:**
- Modify: `src/bunsho/services/content_repository.py`, `src/bunsho/orchestration/content_build.py`, `src/bunsho/factories.py`, `src/bunsho/logging_setup.py`
- Test: extend `tests/unit/services/test_content_repository.py`, `tests/unit/orchestration/test_content_build.py`, `tests/unit/test_factories.py`, `tests/unit/test_logging_setup.py`

**Interfaces:**
- Produces: `ContentWriter.write` retries `os.replace` on `PermissionError` (5 attempts, sleeping `0.1 * attempt` seconds between them) and still cleans up its temp file when it finally fails; `ContentBuildOrchestrator.build` logs `content_build_failed stage=write target=<path>` (level ERROR, with traceback) before re-raising a writer failure; `create_context` also tolerates `OSError` and `sqlite3.Error` from the jamdict service; `configure_logging(level: str = "INFO", *, force: bool = True) -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/services/test_content_repository.py` (merge any new imports into the file's import block at the top; the file already has `_write(target)`):

```python
def test_replace_is_retried_on_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_replace = os.replace
    calls: list[int] = []
    slept: list[float] = []

    def flaky(src: object, dst: object) -> None:
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError("target is open elsewhere")
        real_replace(src, dst)  # type: ignore[arg-type]

    monkeypatch.setattr("bunsho.services.content_repository.os.replace", flaky)
    monkeypatch.setattr("bunsho.services.content_repository.time.sleep", slept.append)
    target = tmp_path / "content.db"
    _write(target)
    assert len(calls) == 3
    assert slept == pytest.approx([0.1, 0.2])
    assert ContentRepository(target).counts().vocab == 2
    assert [p.name for p in tmp_path.iterdir()] == ["content.db"]


def test_other_os_errors_are_not_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def broken(src: object, dst: object) -> None:
        calls.append(1)
        raise OSError("disk on fire")

    monkeypatch.setattr("bunsho.services.content_repository.os.replace", broken)
    monkeypatch.setattr("bunsho.services.content_repository.time.sleep", lambda _s: None)
    with pytest.raises(OSError, match="on fire"):
        _write(tmp_path / "content.db")
    assert len(calls) == 1
```

In the existing `test_replace_failure_cleans_up_and_keeps_existing_database`, add this line before the `with pytest.raises(PermissionError, ...)` block so the retry backoff does not slow the suite:

```python
    monkeypatch.setattr("bunsho.services.content_repository.time.sleep", lambda _s: None)
```

Append to `tests/unit/orchestration/test_content_build.py` (merge imports: `logging`, `pytest` and `ContentBuildOrchestrator` are already imported there):

```python
class _FailingWriter:
    def write(self, target, *, kana, kanji, vocab, meta):  # type: ignore[no-untyped-def]
        raise RuntimeError("disk full")


def test_writer_failure_is_logged_and_propagates(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    logger = logging.getLogger("bunsho.test_build_failure")
    events: list[BuildProgress] = []
    orchestrator = ContentBuildOrchestrator(
        importer=_FakeImporter(VOCAB),  # type: ignore[arg-type]
        kana_provider=KanaSource(),
        kanji_source=FakeKanjiSource(),  # type: ignore[arg-type]
        writer=_FailingWriter(),  # type: ignore[arg-type]
        logger=logger,
    )
    with caplog.at_level(logging.ERROR, logger=logger.name):
        with pytest.raises(RuntimeError, match="disk full"):
            orchestrator.build(tmp_path / "deck.apkg", tmp_path / "c.db", on_progress=events.append)
    assert "content_build_failed stage=write" in caplog.text
    assert events[-1] == BuildProgress("write", 0, 1)
```

Append to `tests/unit/test_factories.py` (merge `sqlite3` into the imports):

```python
@pytest.mark.parametrize("error", [OSError("unreadable"), sqlite3.DatabaseError("corrupt")])
def test_jamdict_os_and_sqlite_errors_degrade_gracefully(
    app_config: AppConfig,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
) -> None:
    def broken(_db_file: object) -> None:
        raise error

    monkeypatch.setattr("bunsho.factories.JamdictService", broken)
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        ctx = create_context(app_config, logger=logging.getLogger(LOGGER_NAME))
    assert ctx.kanji_source is None
    assert ctx.kanji_catalog is None
    assert "service_init_failed service=jamdict" in caplog.text
```

Append to `tests/unit/test_logging_setup.py`:

```python
def test_configure_logging_without_force_keeps_existing_handlers() -> None:
    root = logging.getLogger()
    previous_level, previous_handlers = root.level, list(root.handlers)
    marker = logging.NullHandler()
    try:
        root.handlers[:] = [marker]
        configure_logging("WARNING", force=False)
        assert root.handlers == [marker]
    finally:
        root.handlers[:] = previous_handlers
        root.setLevel(previous_level)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/services/test_content_repository.py tests/unit/orchestration/test_content_build.py tests/unit/test_factories.py tests/unit/test_logging_setup.py -q`
Expected: the five new tests FAIL (no retry; no `content_build_failed` log; `OSError`/`sqlite3.DatabaseError` escape `create_context`; `configure_logging` has no `force` parameter).

- [ ] **Step 3: Implement**

`src/bunsho/services/content_repository.py`: add `import time` to the imports (keep them sorted), then add this module-level code after `_SCHEMA` (before the `ContentWriter` class):

```python
_REPLACE_ATTEMPTS = 5
_REPLACE_DELAY_SECONDS = 0.1


def _replace_with_retry(source: Path, target: Path) -> None:
    """Move ``source`` over ``target``, retrying briefly on ``PermissionError``.

    On Windows ``os.replace`` fails while another connection has ``target`` open; the
    repository opens short-lived connections, so a few short retries almost always succeed.
    """
    for attempt in range(1, _REPLACE_ATTEMPTS + 1):
        try:
            os.replace(source, target)
        except PermissionError:
            if attempt == _REPLACE_ATTEMPTS:
                raise
            time.sleep(_REPLACE_DELAY_SECONDS * attempt)
        else:
            return
```

In `ContentWriter.write` replace `os.replace(tmp, target)` (inside the final `try: ... except OSError:`) with `_replace_with_retry(tmp, target)`, and change the docstring sentence about Windows to: "On Windows ``os.replace`` raises ``PermissionError`` while another connection has ``target`` open; the move is retried a few times (about a second in total) before the error is raised."

`src/bunsho/orchestration/content_build.py`: replace the single line `self._writer.write(target, kana=kana, kanji=kanji, vocab=deck.vocab, meta=meta)` with:

```python
            try:
                self._writer.write(target, kana=kana, kanji=kanji, vocab=deck.vocab, meta=meta)
            except Exception:
                self._logger.error(
                    "content_build_failed stage=write target=%s", target, exc_info=True
                )
                raise
```

`src/bunsho/factories.py`: add `import sqlite3` to the imports and change `except JamdictUnavailableError as exc:` to `except (JamdictUnavailableError, OSError, sqlite3.Error) as exc:`.

`src/bunsho/logging_setup.py`: replace the function with:

```python
def configure_logging(level: str = "INFO", *, force: bool = True) -> None:
    """Configure the root logger with a logfmt-style line format.

    Args:
        level: A standard level name such as ``INFO`` or ``DEBUG``.
        force: Replace existing root handlers. Pass ``False`` when a server such as uvicorn
            already installed handlers that must be kept.
    """
    logging.basicConfig(level=level.upper(), format=LOG_FORMAT, force=force)
```

- [ ] **Step 4: Run tests and gates**

Run: `uv run pytest tests -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run bandit -r src/ -l`
Expected: all PASS; the existing replace-failure and factory tests still pass unchanged apart from the one added `monkeypatch` line.

- [ ] **Step 5: Commit**

```bash
git add src/bunsho tests
git commit -m "fix: retry content.db replace on Windows, log write failures, widen jamdict init" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: `progress.db` — models, Alembic migration, backup-then-upgrade runner, async engine

**Files:**
- Create: `src/bunsho/db/__init__.py`, `src/bunsho/db/models.py`, `src/bunsho/db/engine.py`, `src/bunsho/db/migrate.py`, `src/bunsho/db/migrations/env.py`, `src/bunsho/db/migrations/script.py.mako`, `src/bunsho/db/migrations/versions/0001_initial.py`, `alembic.ini`
- Test: `tests/unit/db/__init__.py`, `tests/unit/db/test_migrate.py`, `tests/unit/db/test_engine.py`
- Modify: `pyproject.toml` (mypy override, only if needed)

**Interfaces:**
- Produces (`bunsho.db.models`): `Base(DeclarativeBase)`; `CardState` (`card_state`: `id`, `item_id`, `direction`, `state`, `step`, `stability`, `difficulty`, `due`, `last_review`, `reps`, `lapses`; unique `(item_id, direction)`; index on `due`), `ReviewLog` (`review_log`: `id`, `item_id`, `direction`, `grade`, `mode`, `reviewed_at`, `state_before`, `stability_before`, `difficulty_before`, `elapsed_days`, `duration_ms`; indexes on `(item_id, direction)` and `reviewed_at`), `AppSetting` (`app_setting`: `key` primary key, `value`). Timestamps are ISO-8601 UTC strings. Plan 2 adds columns through new migrations.
- Produces (`bunsho.db.migrate`): `MigrationResult(from_revision: str | None, to_revision: str, upgraded: bool, backup_path: Path | None)`; `run_migrations(db_path: Path, *, backup_dir: Path, now: Callable[[], datetime] | None = None, logger: logging.Logger | None = None) -> MigrationResult`. Behaviour: a missing database is created with no backup; an existing database already at head is left alone; an existing database that needs migrating (including one with no `alembic_version` table) is first copied with the sqlite backup API to `backup_dir/progress-<UTC yyyymmddThhmmssZ>-from-<revision or "unversioned">.db`, then upgraded to head. A database that is not valid SQLite raises (fail fast) without a backup.
- Produces (`bunsho.db.engine`): `ProgressDatabase(path: Path)` with `sessions: async_sessionmaker[AsyncSession]` (`expire_on_commit=False`), `async ping() -> None`, `async dispose() -> None`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/db/test_migrate.py` (create an empty `tests/unit/db/__init__.py`):

```python
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.exc import DatabaseError

from bunsho.db.migrate import run_migrations
from bunsho.db.models import Base

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def _tables(db_path: Path) -> set[str]:
    with closing(sqlite3.connect(db_path)) as con:
        return {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_fresh_database_is_created_without_backup(tmp_path: Path) -> None:
    db = tmp_path / "data" / "progress.db"
    result = run_migrations(db, backup_dir=tmp_path / "backups", now=lambda: NOW)
    assert (result.from_revision, result.to_revision) == (None, "0001")
    assert result.upgraded is True
    assert result.backup_path is None
    assert {"card_state", "review_log", "app_setting", "alembic_version"} <= _tables(db)
    assert not (tmp_path / "backups").exists()


def test_second_run_is_a_no_op(tmp_path: Path) -> None:
    db = tmp_path / "progress.db"
    run_migrations(db, backup_dir=tmp_path / "backups", now=lambda: NOW)
    again = run_migrations(db, backup_dir=tmp_path / "backups", now=lambda: NOW)
    assert (again.from_revision, again.upgraded, again.backup_path) == ("0001", False, None)
    assert not (tmp_path / "backups").exists()


def test_existing_unversioned_database_is_backed_up_then_upgraded(tmp_path: Path) -> None:
    db = tmp_path / "progress.db"
    with closing(sqlite3.connect(db)) as con, con:
        con.execute("CREATE TABLE legacy (v TEXT)")
        con.execute("INSERT INTO legacy VALUES ('keep me')")
    result = run_migrations(db, backup_dir=tmp_path / "backups", now=lambda: NOW)
    assert result.upgraded is True
    assert result.backup_path == tmp_path / "backups" / "progress-20260102T030405Z-from-unversioned.db"
    with closing(sqlite3.connect(result.backup_path)) as con:
        assert con.execute("SELECT v FROM legacy").fetchall() == [("keep me",)]
        assert "card_state" not in _tables(result.backup_path)  # backup predates the upgrade
    assert {"legacy", "card_state"} <= _tables(db)


def test_corrupt_database_fails_fast_without_a_backup(tmp_path: Path) -> None:
    db = tmp_path / "progress.db"
    db.write_bytes(b"this is not a sqlite database" * 20)
    with pytest.raises(DatabaseError):
        run_migrations(db, backup_dir=tmp_path / "backups", now=lambda: NOW)
    assert not (tmp_path / "backups").exists()


def test_migration_matches_the_models(tmp_path: Path) -> None:
    db = tmp_path / "progress.db"
    run_migrations(db, backup_dir=tmp_path / "backups", now=lambda: NOW)
    engine = create_engine(URL.create("sqlite", database=str(db)))
    try:
        with engine.connect() as connection:
            differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    finally:
        engine.dispose()
    assert differences == []
```

`tests/unit/db/test_engine.py`:

```python
import asyncio
from pathlib import Path

from bunsho.db.engine import ProgressDatabase
from bunsho.db.migrate import run_migrations
from bunsho.db.models import AppSetting, CardState


def test_round_trip_through_the_async_engine(tmp_path: Path) -> None:
    path = tmp_path / "progress.db"
    run_migrations(path, backup_dir=tmp_path / "backups")

    async def scenario() -> tuple[str, int]:
        database = ProgressDatabase(path)
        try:
            await database.ping()
            async with database.sessions() as session:
                session.add(AppSetting(key="theme", value="dark"))
                session.add(
                    CardState(item_id="kana:hira:あ", direction="glyph-sound", due="2026-01-01T00:00:00Z")
                )
                await session.commit()
            async with database.sessions() as session:
                setting = await session.get(AppSetting, "theme")
                card = await session.get(CardState, 1)
                assert setting is not None and card is not None
                return setting.value, card.reps
        finally:
            await database.dispose()

    assert asyncio.run(scenario()) == ("dark", 0)


def test_ping_fails_for_an_unreachable_database(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = ProgressDatabase(tmp_path / "missing-dir" / "progress.db")
        try:
            await database.ping()
        finally:
            await database.dispose()

    import pytest

    with pytest.raises(Exception):  # noqa: B017,PT011 - driver-specific OperationalError
        asyncio.run(scenario())
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/db -q`
Expected: FAIL (`ModuleNotFoundError: bunsho.db`).

- [ ] **Step 3: Implement the models and engine**

`src/bunsho/db/__init__.py`:

```python
"""Persistence for ``progress.db``: models, migrations and the async engine."""
```

`src/bunsho/db/models.py`:

```python
"""SQLAlchemy models for ``progress.db`` (the irreplaceable study history)."""

from __future__ import annotations

from sqlalchemy import Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for every ``progress.db`` table."""


class CardState(Base):
    """Scheduling state of one card (an item plus a direction)."""

    __tablename__ = "card_state"
    __table_args__ = (
        UniqueConstraint("item_id", "direction", name="uq_card_state_item_direction"),
        Index("ix_card_state_due", "due"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[str] = mapped_column(String(255))
    direction: Mapped[str] = mapped_column(String(32))
    state: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    step: Mapped[int | None] = mapped_column(Integer)
    stability: Mapped[float | None] = mapped_column(Float)
    difficulty: Mapped[float | None] = mapped_column(Float)
    due: Mapped[str] = mapped_column(String(32))
    last_review: Mapped[str | None] = mapped_column(String(32))
    reps: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    lapses: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class ReviewLog(Base):
    """Append-only history of every review."""

    __tablename__ = "review_log"
    __table_args__ = (
        Index("ix_review_log_card", "item_id", "direction"),
        Index("ix_review_log_reviewed_at", "reviewed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[str] = mapped_column(String(255))
    direction: Mapped[str] = mapped_column(String(32))
    grade: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(32), default="flip", server_default="flip")
    reviewed_at: Mapped[str] = mapped_column(String(32))
    state_before: Mapped[int | None] = mapped_column(Integer)
    stability_before: Mapped[float | None] = mapped_column(Float)
    difficulty_before: Mapped[float | None] = mapped_column(Float)
    elapsed_days: Mapped[float | None] = mapped_column(Float)
    duration_ms: Mapped[int | None] = mapped_column(Integer)


class AppSetting(Base):
    """A small key/value store for user settings."""

    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(String)
```

`src/bunsho/db/engine.py`:

```python
"""Async access to ``progress.db``."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


class ProgressDatabase:
    """Async engine and session factory for ``progress.db``.

    The schema is managed by Alembic (see ``bunsho.db.migrate``); this class never
    creates tables.
    """

    def __init__(self, path: Path) -> None:
        """Create the engine (no connection is opened until first use).

        Args:
            path: Location of ``progress.db``.
        """
        self._engine = create_async_engine(URL.create("sqlite+aiosqlite", database=str(path)))
        self.sessions: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine, expire_on_commit=False
        )

    async def ping(self) -> None:
        """Run ``SELECT 1``; raises if the database cannot be opened."""
        async with self._engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def dispose(self) -> None:
        """Close pooled connections."""
        await self._engine.dispose()
```

- [ ] **Step 4: Implement the migration environment and runner**

`src/bunsho/db/migrations/env.py`:

```python
"""Alembic environment: online migrations of ``progress.db`` through stdlib sqlite."""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import URL, make_url

from bunsho.db.models import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_online() -> None:
    """Migrate the database named by ``config.attributes['db_path']`` (or ``alembic.ini``)."""
    db_path = config.attributes.get("db_path")
    if db_path is not None:
        url = URL.create("sqlite", database=str(db_path))
    else:
        configured = config.get_main_option("sqlalchemy.url")
        if configured is None:
            raise RuntimeError("set Config.attributes['db_path'] or sqlalchemy.url in alembic.ini")
        url = make_url(configured)
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("offline migrations are not supported for progress.db")
run_migrations_online()
```

`src/bunsho/db/migrations/script.py.mako`:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

`src/bunsho/db/migrations/versions/0001_initial.py`:

```python
"""Initial progress.db schema: card_state, review_log, app_setting.

Revision ID: 0001
Revises:
Create Date: 2026-09-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the initial tables."""
    op.create_table(
        "card_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.String(length=255), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("state", sa.Integer(), server_default="0", nullable=False),
        sa.Column("step", sa.Integer(), nullable=True),
        sa.Column("stability", sa.Float(), nullable=True),
        sa.Column("difficulty", sa.Float(), nullable=True),
        sa.Column("due", sa.String(length=32), nullable=False),
        sa.Column("last_review", sa.String(length=32), nullable=True),
        sa.Column("reps", sa.Integer(), server_default="0", nullable=False),
        sa.Column("lapses", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_id", "direction", name="uq_card_state_item_direction"),
    )
    op.create_index("ix_card_state_due", "card_state", ["due"])
    op.create_table(
        "review_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.String(length=255), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("grade", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=32), server_default="flip", nullable=False),
        sa.Column("reviewed_at", sa.String(length=32), nullable=False),
        sa.Column("state_before", sa.Integer(), nullable=True),
        sa.Column("stability_before", sa.Float(), nullable=True),
        sa.Column("difficulty_before", sa.Float(), nullable=True),
        sa.Column("elapsed_days", sa.Float(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_log_card", "review_log", ["item_id", "direction"])
    op.create_index("ix_review_log_reviewed_at", "review_log", ["reviewed_at"])
    op.create_table(
        "app_setting",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    """Drop the initial tables."""
    op.drop_table("app_setting")
    op.drop_index("ix_review_log_reviewed_at", table_name="review_log")
    op.drop_index("ix_review_log_card", table_name="review_log")
    op.drop_table("review_log")
    op.drop_index("ix_card_state_due", table_name="card_state")
    op.drop_table("card_state")
```

`src/bunsho/db/migrate.py`:

```python
"""Run ``progress.db`` migrations, backing up an existing database first."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


@dataclass(frozen=True, slots=True)
class MigrationResult:
    """Outcome of ``run_migrations``."""

    from_revision: str | None
    to_revision: str
    upgraded: bool
    backup_path: Path | None


def _config(db_path: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR).replace("%", "%%"))
    cfg.attributes["db_path"] = str(db_path)
    return cfg


def _current_revision(db_path: Path) -> str | None:
    engine = create_engine(URL.create("sqlite", database=str(db_path)))
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def _backup(db_path: Path, backup_dir: Path, revision: str | None, stamp: datetime) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    name = f"progress-{stamp.strftime('%Y%m%dT%H%M%SZ')}-from-{revision or 'unversioned'}.db"
    target = backup_dir / name
    with closing(sqlite3.connect(db_path)) as source, closing(sqlite3.connect(target)) as dest:
        source.backup(dest)
    return target


def run_migrations(
    db_path: Path,
    *,
    backup_dir: Path,
    now: Callable[[], datetime] | None = None,
    logger: logging.Logger | None = None,
) -> MigrationResult:
    """Bring ``progress.db`` to the latest schema, backing it up first if it exists.

    Args:
        db_path: Location of ``progress.db`` (created if missing).
        backup_dir: Where the pre-migration backup is written.
        now: Clock used for the backup file name (defaults to UTC now).
        logger: Logger for key=value messages.

    Returns:
        What happened, including the backup path when one was made.

    Raises:
        sqlalchemy.exc.DatabaseError: The file exists but is not a valid SQLite database.
        alembic.util.exc.CommandError: A migration failed; the backup (if any) is kept.
    """
    log = logger or logging.getLogger(__name__)
    clock = now or (lambda: datetime.now(UTC))
    cfg = _config(db_path)
    head = ScriptDirectory.from_config(cfg).get_current_head()
    if head is None:
        raise RuntimeError("no progress.db migrations found")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    existed = db_path.is_file()
    current = _current_revision(db_path) if existed else None
    if existed and current == head:
        log.info("progress_db_up_to_date revision=%s path=%s", head, db_path)
        return MigrationResult(current, head, False, None)
    backup = _backup(db_path, backup_dir, current, clock()) if existed else None
    command.upgrade(cfg, "head")
    log.info(
        "progress_db_migrated from=%s to=%s backup=%s path=%s",
        current,
        head,
        backup,
        db_path,
    )
    return MigrationResult(current, head, True, backup)
```

`alembic.ini` (repo root; only for developers running `uv run alembic revision --autogenerate -m "..." --rev-id 0002`; the app never reads it):

```ini
[alembic]
script_location = src/bunsho/db/migrations
sqlalchemy.url = sqlite:///data/progress.db
```

- [ ] **Step 5: Run tests and gates**

Run: `uv run pytest tests/unit/db -q && uv run pytest tests -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run bandit -r src/ -l`
Expected: all PASS. If mypy strict rejects `env.py` or the migration script (Alembic's `op` and `context` are dynamic), add to `pyproject.toml`:

```toml
[[tool.mypy.overrides]]
module = ["bunsho.db.migrations.*"]
ignore_errors = true
```

Also confirm the migration files are packaged: `uv build --wheel --out-dir <tmp>` and check `bunsho/db/migrations/versions/0001_initial.py` and `script.py.mako` are inside the wheel (`python -m zipfile -l <wheel> | grep migrations`).

- [ ] **Step 6: Commit**

```bash
git add src/bunsho/db alembic.ini tests/unit/db pyproject.toml
git commit -m "feat(db): progress.db models, Alembic migration with backup, async engine" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Authentication service and login throttle

**Files:**
- Create: `src/bunsho/services/auth.py`, `src/bunsho/services/login_throttle.py`
- Modify: `tests/base.py` (add auth builders)
- Test: `tests/unit/services/test_auth.py`, `tests/unit/services/test_login_throttle.py`

**Interfaces:**
- Consumes: `AuthSettings` (Task 1).
- Produces (`bunsho.services.auth`): `AuthError(Exception)`; frozen slots dataclass `TokenPair(access_token: str, refresh_token: str, expires_in: int, token_type: str = "bearer")` (`expires_in` is the access token lifetime in seconds); `AuthService(settings: AuthSettings, *, clock: Callable[[], datetime] | None = None)` with `verify_credentials(username: str, password: str) -> bool`, `issue_tokens(username: str) -> TokenPair`, `authenticate(access_token: str) -> str` (returns the username, raises `AuthError`), `refresh(refresh_token: str) -> TokenPair` (raises `AuthError`; the old refresh token stays valid until it expires — tokens are stateless, ruling 5).
- Produces (`bunsho.services.login_throttle`): `LoginThrottle(*, max_failures: int = 5, window_seconds: float = 60.0, clock: Callable[[], float] = time.monotonic)` with `retry_after(key: str) -> float | None` (seconds to wait, or `None` when allowed), `record_failure(key: str) -> None`, `reset(key: str) -> None`.
- Produces (`tests/base.py`): `PASSWORD`, `JWT_SECRET`, `make_auth_settings(**overrides: object) -> AuthSettings` (argon2 hash of `PASSWORD`, computed once and cached).
- Token claims: `sub` (username), `typ` (`"access"` or `"refresh"`), `iat`, `exp`, `jti`; HS256 with `auth.jwt_secret`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/base.py` (merge the imports into the import block at the top of the file):

```python
from dataclasses import replace
from functools import cache

from pwdlib import PasswordHash

from bunsho.config.service import MIN_JWT_SECRET_LENGTH, AuthSettings

PASSWORD = "correct horse battery staple"
JWT_SECRET = "s" * (MIN_JWT_SECRET_LENGTH + 8)


@cache
def _password_hash() -> str:
    return PasswordHash.recommended().hash(PASSWORD)


def make_auth_settings(**overrides: object) -> AuthSettings:
    """Build ``AuthSettings`` for user ``james`` with a cached argon2 hash of ``PASSWORD``."""
    base = AuthSettings(
        username="james",
        password_hash=_password_hash(),
        jwt_secret=JWT_SECRET,
        access_ttl_minutes=15,
        refresh_ttl_days=30,
    )
    return replace(base, **overrides)  # type: ignore[arg-type]
```

`tests/unit/services/test_auth.py`:

```python
from datetime import UTC, datetime

import jwt
import pytest

from bunsho.services.auth import AuthError, AuthService
from tests.base import JWT_SECRET, PASSWORD, make_auth_settings


@pytest.fixture(scope="module")
def auth() -> AuthService:
    return AuthService(make_auth_settings())


def test_correct_credentials_are_accepted(auth: AuthService) -> None:
    assert auth.verify_credentials("james", PASSWORD) is True


@pytest.mark.parametrize(
    ("username", "password"),
    [("james", "wrong"), ("mallory", PASSWORD), ("", ""), ("JAMES", PASSWORD)],
)
def test_wrong_credentials_are_rejected(auth: AuthService, username: str, password: str) -> None:
    assert auth.verify_credentials(username, password) is False


def test_token_round_trip(auth: AuthService) -> None:
    tokens = auth.issue_tokens("james")
    assert tokens.token_type == "bearer"
    assert tokens.expires_in == 15 * 60
    assert auth.authenticate(tokens.access_token) == "james"
    claims = jwt.decode(tokens.access_token, JWT_SECRET, algorithms=["HS256"])
    assert claims["typ"] == "access"
    assert claims["sub"] == "james"


def test_refresh_issues_a_new_pair(auth: AuthService) -> None:
    first = auth.issue_tokens("james")
    second = auth.refresh(first.refresh_token)
    assert second.access_token != first.access_token
    assert auth.authenticate(second.access_token) == "james"


def test_access_and_refresh_tokens_are_not_interchangeable(auth: AuthService) -> None:
    tokens = auth.issue_tokens("james")
    with pytest.raises(AuthError):
        auth.authenticate(tokens.refresh_token)
    with pytest.raises(AuthError):
        auth.refresh(tokens.access_token)


def test_expired_token_is_rejected() -> None:
    past = AuthService(make_auth_settings(), clock=lambda: datetime(2020, 1, 1, tzinfo=UTC))
    with pytest.raises(AuthError):
        past.authenticate(past.issue_tokens("james").access_token)


def test_token_signed_with_another_secret_is_rejected(auth: AuthService) -> None:
    other = AuthService(make_auth_settings(jwt_secret="o" * 40))
    with pytest.raises(AuthError):
        auth.authenticate(other.issue_tokens("james").access_token)


def test_tampered_and_garbage_tokens_are_rejected(auth: AuthService) -> None:
    token = auth.issue_tokens("james").access_token
    with pytest.raises(AuthError):
        auth.authenticate(token[:-3] + ("abc" if not token.endswith("abc") else "xyz"))
    with pytest.raises(AuthError):
        auth.authenticate("not.a.jwt")
    with pytest.raises(AuthError):
        auth.authenticate("")


def test_token_for_another_subject_is_rejected(auth: AuthService) -> None:
    with pytest.raises(AuthError):
        auth.authenticate(auth.issue_tokens("mallory").access_token)


def test_token_without_expiry_is_rejected(auth: AuthService) -> None:
    forged = jwt.encode({"sub": "james", "typ": "access"}, JWT_SECRET, algorithm="HS256")
    with pytest.raises(AuthError):
        auth.authenticate(forged)
```

`tests/unit/services/test_login_throttle.py`:

```python
import pytest

from bunsho.services.login_throttle import LoginThrottle


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_allows_until_the_failure_limit_is_reached() -> None:
    clock = _Clock()
    throttle = LoginThrottle(max_failures=3, window_seconds=60, clock=clock)
    for _ in range(2):
        throttle.record_failure("10.0.0.1")
        assert throttle.retry_after("10.0.0.1") is None
    throttle.record_failure("10.0.0.1")
    assert throttle.retry_after("10.0.0.1") == pytest.approx(60.0)


def test_wait_shrinks_and_expires_with_the_window() -> None:
    clock = _Clock()
    throttle = LoginThrottle(max_failures=2, window_seconds=60, clock=clock)
    throttle.record_failure("k")
    throttle.record_failure("k")
    clock.now += 45
    assert throttle.retry_after("k") == pytest.approx(15.0)
    clock.now += 16
    assert throttle.retry_after("k") is None


def test_keys_are_independent_and_reset_clears() -> None:
    clock = _Clock()
    throttle = LoginThrottle(max_failures=1, window_seconds=60, clock=clock)
    throttle.record_failure("a")
    assert throttle.retry_after("a") is not None
    assert throttle.retry_after("b") is None
    throttle.reset("a")
    assert throttle.retry_after("a") is None
    throttle.reset("never-seen")  # must not raise
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/services/test_auth.py tests/unit/services/test_login_throttle.py -q`
Expected: FAIL (`ModuleNotFoundError: bunsho.services.auth`).

- [ ] **Step 3: Implement**

`src/bunsho/services/auth.py`:

```python
"""Single-user authentication: argon2 password check and JWT access/refresh tokens."""

from __future__ import annotations

import hmac
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from bunsho.config.service import AuthSettings

_ALGORITHM = "HS256"
TokenType = Literal["access", "refresh"]


class AuthError(Exception):
    """Raised when credentials or a token are invalid."""


@dataclass(frozen=True, slots=True)
class TokenPair:
    """An access token and a refresh token."""

    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"


class AuthService:
    """Verifies the single configured user and issues stateless JWTs."""

    def __init__(
        self, settings: AuthSettings, *, clock: Callable[[], datetime] | None = None
    ) -> None:
        """Create the service.

        Args:
            settings: Validated auth settings (argon2 hash, JWT secret, lifetimes).
            clock: Time source used for ``iat``/``exp`` (defaults to UTC now).
        """
        self._settings = settings
        self._clock = clock or (lambda: datetime.now(UTC))
        self._hasher = PasswordHash.recommended()
        # Checked when the username is wrong so a bad username costs as much as a bad password.
        self._dummy_hash = self._hasher.hash(uuid.uuid4().hex)

    def verify_credentials(self, username: str, password: str) -> bool:
        """Check a username and password in constant time.

        Returns:
            ``True`` only when both match the configured user.
        """
        user_ok = hmac.compare_digest(username.encode(), self._settings.username.encode())
        candidate = self._settings.password_hash if user_ok else self._dummy_hash
        try:
            password_ok = self._hasher.verify(password, candidate)
        except UnknownHashError:
            password_ok = False
        return user_ok and password_ok

    def _encode(self, username: str, token_type: TokenType, lifetime: timedelta) -> str:
        issued = self._clock()
        claims: dict[str, Any] = {
            "sub": username,
            "typ": token_type,
            "iat": issued,
            "exp": issued + lifetime,
            "jti": uuid.uuid4().hex,
        }
        return jwt.encode(claims, self._settings.jwt_secret, algorithm=_ALGORITHM)

    def issue_tokens(self, username: str) -> TokenPair:
        """Issue a new access and refresh token for ``username``."""
        access_ttl = timedelta(minutes=self._settings.access_ttl_minutes)
        refresh_ttl = timedelta(days=self._settings.refresh_ttl_days)
        return TokenPair(
            access_token=self._encode(username, "access", access_ttl),
            refresh_token=self._encode(username, "refresh", refresh_ttl),
            expires_in=int(access_ttl.total_seconds()),
        )

    def _decode(self, token: str, expected: TokenType) -> str:
        try:
            claims = jwt.decode(
                token,
                self._settings.jwt_secret,
                algorithms=[_ALGORITHM],
                options={"require": ["exp", "sub", "typ"]},
            )
        except jwt.InvalidTokenError as exc:
            raise AuthError("invalid or expired token") from exc
        if claims["typ"] != expected or claims["sub"] != self._settings.username:
            raise AuthError("wrong token type or subject")
        return str(claims["sub"])

    def authenticate(self, access_token: str) -> str:
        """Validate an access token.

        Returns:
            The authenticated username.

        Raises:
            AuthError: The token is invalid, expired, of the wrong type or for another user.
        """
        return self._decode(access_token, "access")

    def refresh(self, refresh_token: str) -> TokenPair:
        """Exchange a valid refresh token for a new token pair.

        Raises:
            AuthError: The token is invalid, expired, of the wrong type or for another user.
        """
        return self.issue_tokens(self._decode(refresh_token, "refresh"))
```

`src/bunsho/services/login_throttle.py`:

```python
"""In-memory sliding-window throttle for failed logins."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

_PRUNE_THRESHOLD = 1024


class LoginThrottle:
    """Blocks a client key after too many recent failures."""

    def __init__(
        self,
        *,
        max_failures: int = 5,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Create a throttle.

        Args:
            max_failures: Failures inside the window that trigger blocking.
            window_seconds: Length of the sliding window.
            clock: Monotonic time source in seconds.
        """
        self._max = max_failures
        self._window = window_seconds
        self._clock = clock
        self._failures: dict[str, deque[float]] = {}

    def _recent(self, key: str) -> deque[float]:
        failures = self._failures.get(key)
        if failures is None:
            return deque()
        horizon = self._clock() - self._window
        while failures and failures[0] <= horizon:
            failures.popleft()
        if not failures:
            del self._failures[key]
        return failures

    def retry_after(self, key: str) -> float | None:
        """Seconds until ``key`` may try again, or ``None`` when it is allowed now."""
        failures = self._recent(key)
        if len(failures) < self._max:
            return None
        return max(0.0, failures[0] + self._window - self._clock())

    def record_failure(self, key: str) -> None:
        """Record one failed attempt for ``key``."""
        if len(self._failures) > _PRUNE_THRESHOLD:
            for stale in list(self._failures):
                self._recent(stale)
        self._failures.setdefault(key, deque()).append(self._clock())

    def reset(self, key: str) -> None:
        """Forget ``key`` (after a successful login)."""
        self._failures.pop(key, None)
```

- [ ] **Step 4: Run tests and gates**

Run: `uv run pytest tests -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run bandit -r src/ -l`
Expected: all PASS. (`test_wrong_credentials_are_rejected` and the round-trip tests each hash or verify once at about 0.1 s.)

- [ ] **Step 5: Commit**

```bash
git add src/bunsho/services/auth.py src/bunsho/services/login_throttle.py tests/base.py tests/unit/services
git commit -m "feat(auth): argon2 password check, JWT tokens and login throttle" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Background build task manager

**Files:**
- Create: `src/bunsho/orchestration/build_tasks.py`
- Test: `tests/unit/orchestration/test_build_tasks.py`

**Interfaces:**
- Consumes: `Context` (with `config`, `logger`, `refresh_content_repo()`), `ContentBuildOrchestrator`, `BuildProgress`, `BuildReport` (Plan 1A).
- Produces (`bunsho.orchestration.build_tasks`):
  - `BuildState(StrEnum)`: `RUNNING="running"`, `SUCCEEDED="succeeded"`, `FAILED="failed"`.
  - `BuildAlreadyRunningError(RuntimeError)`.
  - `BuildTask` (slots dataclass): `task_id: str`, `dry_run: bool`, `state: BuildState`, `started_at: datetime`, `finished_at: datetime | None = None`, `progress: BuildProgress | None = None`, `report: BuildReport | None = None`, `error: str | None = None`.
  - `BuildEvent` (frozen slots dataclass): `kind: Literal["progress", "state"]`, `task_id: str`, `state: BuildState`, `progress: BuildProgress | None = None`, `error: str | None = None`.
  - `OrchestratorFactory = Callable[[Context], ContentBuildOrchestrator]`.
  - `BuildTaskManager(ctx: Context, orchestrator_factory: OrchestratorFactory, *, clock: Callable[[], datetime] | None = None, max_history: int = 10, subscriber_queue_size: int = 512)` with: `start(*, dry_run: bool) -> BuildTask` (must be called on the event loop thread; raises `BuildAlreadyRunningError` when a build is active), `get(task_id: str) -> BuildTask | None`, `latest() -> BuildTask | None`, `active -> BuildTask | None` (property), `subscribe() -> asyncio.Queue[BuildEvent]`, `unsubscribe(queue) -> None`, `async join() -> None` (waits for the active build), `async aclose(timeout: float = 30.0) -> None` (waits up to `timeout` seconds for an active build, logging a warning if it is still running).
- Behaviour: the build runs in a worker thread via `asyncio.to_thread`; progress callbacks are marshalled onto the loop with `call_soon_threadsafe` (a closed loop during shutdown is tolerated) and **throttled** — an event is published only when the stage changes, at the first and last item, or every `max(1, total // 100)` items; every published event is delivered to each subscriber queue (a full queue drops its oldest event, so the final `state` event always arrives); after a successful non-dry build `ctx.refresh_content_repo()` runs; any exception marks the task `FAILED` with `error = "<ExceptionType>: <message>"` and is logged; history keeps the newest `max_history` tasks.

- [ ] **Step 1: Write the failing tests**

`tests/unit/orchestration/test_build_tasks.py`:

```python
import asyncio
import threading
from pathlib import Path

import pytest

from bunsho.config.settings import AppConfig
from bunsho.context import Context
from bunsho.orchestration.build_tasks import (
    BuildAlreadyRunningError,
    BuildEvent,
    BuildState,
    BuildTaskManager,
)
from bunsho.orchestration.content_build import BuildProgress, BuildReport, ContentBuildError
from bunsho.services.content_repository import ContentWriter


def _report(dry_run: bool) -> BuildReport:
    return BuildReport(
        dry_run=dry_run,
        target=Path("content.db"),
        deck_sha256="a" * 64,
        kana_count=208,
        kanji_count=3,
        vocab_count=2,
        sentence_count=0,
        vocab_by_level={"N5": 2},
        kanji_by_level={"N5": 3},
        kanji_without_details=0,
        duration_seconds=0.1,
    )


class _Stub:
    """Fake orchestrator: emits progress, optionally blocks, fails, or writes content.db."""

    def __init__(
        self,
        *,
        items: int = 3,
        gate: threading.Event | None = None,
        error: Exception | None = None,
    ) -> None:
        self.items = items
        self.gate = gate
        self.error = error

    def build(self, deck_path, target, *, dry_run=False, on_progress=None):  # type: ignore[no-untyped-def]
        assert on_progress is not None
        on_progress(BuildProgress("import_deck", 0, 1))
        on_progress(BuildProgress("import_deck", 1, 1))
        for index in range(1, self.items + 1):
            on_progress(BuildProgress("enrich_kanji", index, self.items))
        if self.gate is not None:
            assert self.gate.wait(10), "test gate was never released"
        if self.error is not None:
            raise self.error
        if not dry_run:
            on_progress(BuildProgress("write", 0, 1))
            ContentWriter().write(target, kana=[], kanji=[], vocab=[], meta={})
            on_progress(BuildProgress("write", 1, 1))
        return _report(dry_run)


def _manager(app_config: AppConfig, quiet_logger, stub: _Stub, **kwargs) -> tuple[Context, BuildTaskManager]:  # type: ignore[no-untyped-def]
    ctx = Context(config=app_config, logger=quiet_logger)
    return ctx, BuildTaskManager(ctx, lambda _ctx: stub, **kwargs)  # type: ignore[arg-type,return-value]


def _drain(queue: "asyncio.Queue[BuildEvent]") -> list[BuildEvent]:
    events: list[BuildEvent] = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events


def test_successful_build_publishes_events_and_refreshes_the_repository(
    app_config: AppConfig, quiet_logger
) -> None:  # type: ignore[no-untyped-def]
    async def scenario() -> None:
        ctx, manager = _manager(app_config, quiet_logger, _Stub())
        queue = manager.subscribe()
        assert ctx.content_repo is None
        task = manager.start(dry_run=False)
        assert task.state is BuildState.RUNNING
        assert manager.active is task
        await manager.join()
        assert task.state is BuildState.SUCCEEDED
        assert task.report is not None and task.finished_at is not None
        assert manager.active is None
        assert ctx.content_repo is not None  # refreshed after the real build
        events = _drain(queue)
        assert (events[0].kind, events[0].state) == ("state", BuildState.RUNNING)
        assert (events[-1].kind, events[-1].state) == ("state", BuildState.SUCCEEDED)
        stages = [e.progress.stage for e in events if e.progress is not None]
        assert stages[0] == "import_deck" and stages[-1] == "write"
        assert manager.get(task.task_id) is task
        assert manager.latest() is task

    asyncio.run(scenario())


def test_dry_run_does_not_refresh_the_repository(app_config: AppConfig, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    async def scenario() -> None:
        ctx, manager = _manager(app_config, quiet_logger, _Stub())
        task = manager.start(dry_run=True)
        await manager.join()
        assert task.state is BuildState.SUCCEEDED and task.report is not None
        assert ctx.content_repo is None
        assert not app_config.content_db_path.exists()

    asyncio.run(scenario())


def test_failure_marks_the_task_failed_and_allows_a_new_build(
    app_config: AppConfig, quiet_logger
) -> None:  # type: ignore[no-untyped-def]
    async def scenario() -> None:
        stub = _Stub(error=ContentBuildError("jamdict is unavailable"))
        _ctx, manager = _manager(app_config, quiet_logger, stub)
        queue = manager.subscribe()
        task = manager.start(dry_run=False)
        await manager.join()
        assert task.state is BuildState.FAILED
        assert task.error == "ContentBuildError: jamdict is unavailable"
        final = _drain(queue)[-1]
        assert (final.state, final.error) == (BuildState.FAILED, task.error)
        stub.error = None
        second = manager.start(dry_run=True)  # not blocked by the failed build
        await manager.join()
        assert second.state is BuildState.SUCCEEDED

    asyncio.run(scenario())


def test_a_factory_error_is_reported_as_a_failed_task(app_config: AppConfig, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    def broken_factory(_ctx: Context):  # type: ignore[no-untyped-def]
        raise ContentBuildError("cannot build content")

    async def scenario() -> None:
        manager = BuildTaskManager(Context(config=app_config, logger=quiet_logger), broken_factory)
        task = manager.start(dry_run=False)
        await manager.join()
        assert task.state is BuildState.FAILED
        assert "cannot build content" in (task.error or "")

    asyncio.run(scenario())


def test_only_one_build_may_run_at_a_time(app_config: AppConfig, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    async def scenario() -> None:
        gate = threading.Event()
        _ctx, manager = _manager(app_config, quiet_logger, _Stub(gate=gate))
        first = manager.start(dry_run=False)
        with pytest.raises(BuildAlreadyRunningError, match=first.task_id):
            manager.start(dry_run=True)
        gate.set()
        await manager.join()
        assert first.state is BuildState.SUCCEEDED

    asyncio.run(scenario())


def test_progress_events_are_throttled(app_config: AppConfig, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    async def scenario() -> None:
        _ctx, manager = _manager(app_config, quiet_logger, _Stub(items=3000))
        queue = manager.subscribe()
        manager.start(dry_run=True)
        await manager.join()
        events = _drain(queue)
        enrich = [e.progress for e in events if e.progress and e.progress.stage == "enrich_kanji"]
        assert 90 <= len(enrich) <= 140  # about one per percent, not 3000
        assert enrich[-1] == BuildProgress("enrich_kanji", 3000, 3000)

    asyncio.run(scenario())


def test_a_full_subscriber_queue_drops_old_events_but_keeps_the_final_state(
    app_config: AppConfig, quiet_logger
) -> None:  # type: ignore[no-untyped-def]
    async def scenario() -> None:
        _ctx, manager = _manager(app_config, quiet_logger, _Stub(items=500), subscriber_queue_size=2)
        queue = manager.subscribe()
        manager.start(dry_run=True)
        await manager.join()
        events = _drain(queue)
        assert len(events) == 2
        assert (events[-1].kind, events[-1].state) == ("state", BuildState.SUCCEEDED)

    asyncio.run(scenario())


def test_history_is_trimmed_and_unsubscribed_queues_get_nothing(
    app_config: AppConfig, quiet_logger
) -> None:  # type: ignore[no-untyped-def]
    async def scenario() -> None:
        _ctx, manager = _manager(app_config, quiet_logger, _Stub(), max_history=2)
        queue = manager.subscribe()
        manager.unsubscribe(queue)
        tasks = []
        for _ in range(3):
            tasks.append(manager.start(dry_run=True))
            await manager.join()
        assert manager.get(tasks[0].task_id) is None
        assert manager.get(tasks[1].task_id) is tasks[1]
        assert manager.latest() is tasks[2]
        assert queue.empty()

    asyncio.run(scenario())


def test_aclose_waits_for_the_active_build(app_config: AppConfig, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    async def scenario() -> None:
        gate = threading.Event()
        _ctx, manager = _manager(app_config, quiet_logger, _Stub(gate=gate))
        task = manager.start(dry_run=True)
        asyncio.get_running_loop().call_later(0.05, gate.set)
        await manager.aclose(timeout=5)
        assert task.state is BuildState.SUCCEEDED

    asyncio.run(scenario())
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/orchestration/test_build_tasks.py -q`
Expected: FAIL (`ModuleNotFoundError: bunsho.orchestration.build_tasks`).

- [ ] **Step 3: Implement**

`src/bunsho/orchestration/build_tasks.py`:

```python
"""Single-flight background content builds with progress fan-out."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from bunsho.context import Context
from bunsho.orchestration.content_build import (
    BuildProgress,
    BuildReport,
    ContentBuildOrchestrator,
)

OrchestratorFactory = Callable[[Context], ContentBuildOrchestrator]


class BuildState(StrEnum):
    """Lifecycle of a build task."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class BuildAlreadyRunningError(RuntimeError):
    """A build was requested while another one is running."""


@dataclass(slots=True)
class BuildTask:
    """State of one build."""

    task_id: str
    dry_run: bool
    state: BuildState
    started_at: datetime
    finished_at: datetime | None = None
    progress: BuildProgress | None = None
    report: BuildReport | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class BuildEvent:
    """A change published to subscribers."""

    kind: Literal["progress", "state"]
    task_id: str
    state: BuildState
    progress: BuildProgress | None = None
    error: str | None = None


class BuildTaskManager:
    """Runs at most one content build at a time in a worker thread."""

    def __init__(
        self,
        ctx: Context,
        orchestrator_factory: OrchestratorFactory,
        *,
        clock: Callable[[], datetime] | None = None,
        max_history: int = 10,
        subscriber_queue_size: int = 512,
    ) -> None:
        """Create a manager.

        Args:
            ctx: Application context (config, logger, content repository handle).
            orchestrator_factory: Builds the orchestrator for a run (may raise, which
                marks the task failed).
            clock: Time source (defaults to UTC now).
            max_history: How many finished tasks to remember.
            subscriber_queue_size: Capacity of each subscriber queue.
        """
        self._ctx = ctx
        self._factory = orchestrator_factory
        self._clock = clock or (lambda: datetime.now(UTC))
        self._max_history = max_history
        self._queue_size = subscriber_queue_size
        self._logger = ctx.logger
        self._tasks: dict[str, BuildTask] = {}
        self._active: BuildTask | None = None
        self._runner: asyncio.Task[None] | None = None
        self._subscribers: set[asyncio.Queue[BuildEvent]] = set()

    @property
    def active(self) -> BuildTask | None:
        """The running build, if any."""
        return self._active

    def get(self, task_id: str) -> BuildTask | None:
        """Look up a remembered task."""
        return self._tasks.get(task_id)

    def latest(self) -> BuildTask | None:
        """The most recently started task, if any."""
        return next(reversed(self._tasks.values()), None)

    def subscribe(self) -> asyncio.Queue[BuildEvent]:
        """Register a queue that receives every published event."""
        queue: asyncio.Queue[BuildEvent] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[BuildEvent]) -> None:
        """Stop delivering events to ``queue``."""
        self._subscribers.discard(queue)

    def start(self, *, dry_run: bool) -> BuildTask:
        """Start a build in the background.

        Must be called on the event loop thread.

        Raises:
            BuildAlreadyRunningError: A build is already running.
        """
        if self._active is not None:
            raise BuildAlreadyRunningError(f"build {self._active.task_id} is already running")
        task = BuildTask(
            task_id=uuid.uuid4().hex,
            dry_run=dry_run,
            state=BuildState.RUNNING,
            started_at=self._clock(),
        )
        self._active = task
        self._tasks[task.task_id] = task
        self._trim_history()
        loop = asyncio.get_running_loop()
        self._runner = loop.create_task(self._run(task, loop))
        self._logger.info("content_build_task_started task_id=%s dry_run=%s", task.task_id, dry_run)
        self._publish(BuildEvent("state", task.task_id, task.state))
        return task

    async def join(self) -> None:
        """Wait for the active build (if any) to finish."""
        runner = self._runner
        if runner is not None and not runner.done():
            await asyncio.shield(runner)

    async def aclose(self, timeout: float = 30.0) -> None:
        """Wait up to ``timeout`` seconds for an active build; log if it keeps running."""
        runner = self._runner
        if runner is None or runner.done():
            return
        try:
            await asyncio.wait_for(asyncio.shield(runner), timeout)
        except TimeoutError:
            self._logger.warning("content_build_still_running_at_shutdown timeout=%s", timeout)

    def _trim_history(self) -> None:
        for task_id in list(self._tasks):
            if len(self._tasks) <= self._max_history:
                break
            if self._tasks[task_id] is not self._active:
                del self._tasks[task_id]

    async def _run(self, task: BuildTask, loop: asyncio.AbstractEventLoop) -> None:
        try:
            orchestrator = self._factory(self._ctx)
            config = self._ctx.config
            task.report = await asyncio.to_thread(
                orchestrator.build,
                config.deck_path,
                config.content_db_path,
                dry_run=task.dry_run,
                on_progress=self._make_callback(task, loop),
            )
            task.state = BuildState.SUCCEEDED
            if not task.dry_run:
                self._ctx.refresh_content_repo()
        except Exception as exc:
            # Any failure (including a factory error) is reported on the task, not raised.
            task.state = BuildState.FAILED
            task.error = f"{type(exc).__name__}: {exc}"
            self._logger.error(
                "content_build_task_failed task_id=%s error=%s", task.task_id, task.error, exc_info=True
            )
        finally:
            task.finished_at = self._clock()
            self._active = None
            self._logger.info("content_build_task_finished task_id=%s state=%s", task.task_id, task.state)
            self._publish(BuildEvent("state", task.task_id, task.state, error=task.error))

    def _make_callback(
        self, task: BuildTask, loop: asyncio.AbstractEventLoop
    ) -> Callable[[BuildProgress], None]:
        last_stage: str | None = None

        def callback(progress: BuildProgress) -> None:
            nonlocal last_stage
            stage_changed = progress.stage != last_stage
            last_stage = progress.stage
            step = max(1, progress.total // 100)
            if not (
                stage_changed
                or progress.current in (0, progress.total)
                or progress.current % step == 0
            ):
                return
            try:
                loop.call_soon_threadsafe(self._on_progress, task, progress)
            except RuntimeError:  # the event loop closed while shutting down
                self._logger.debug("build_progress_dropped task_id=%s", task.task_id)

        return callback

    def _on_progress(self, task: BuildTask, progress: BuildProgress) -> None:
        task.progress = progress
        self._publish(BuildEvent("progress", task.task_id, task.state, progress=progress))

    def _publish(self, event: BuildEvent) -> None:
        for queue in list(self._subscribers):
            if queue.full():
                queue.get_nowait()  # drop the oldest so the newest (e.g. the final state) fits
            queue.put_nowait(event)
```

- [ ] **Step 4: Run tests and gates**

Run: `uv run pytest tests -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run bandit -r src/ -l`
Expected: all PASS. If the throttling assertion range `90 <= len(enrich) <= 140` fails, print `len(enrich)` and reason about `max(1, total // 100)` (3000 items → every 30th → about 100 events plus the stage boundaries) before changing the bounds.

- [ ] **Step 5: Commit**

```bash
git add src/bunsho/orchestration/build_tasks.py tests/unit/orchestration/test_build_tasks.py
git commit -m "feat(orchestration): single-flight background build manager with progress events" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Health and config-check services, API foundation

**Files:**
- Create: `src/bunsho/services/health.py`, `src/bunsho/services/config_check.py`, `src/bunsho/api/__init__.py`, `src/bunsho/api/schemas.py`, `src/bunsho/api/services.py`, `src/bunsho/api/deps.py`, `src/bunsho/api/app.py`, `src/bunsho/api/routers/__init__.py`, `src/bunsho/api/routers/health.py`
- Modify: `tests/base.py` (service config builder + fixture), `tests/conftest.py`
- Test: `tests/unit/services/test_health.py`, `tests/unit/services/test_config_check.py`, `tests/unit/api/__init__.py`, `tests/unit/api/conftest.py`, `tests/unit/api/test_app_startup.py`

**Interfaces:**
- Consumes: `ServiceConfig` (Task 1), `run_migrations` (Task 3), `ProgressDatabase` (Task 3), `AuthService`, `LoginThrottle` (Task 4), `BuildTaskManager`, `OrchestratorFactory` (Task 5), `Context`, `create_context`, `create_content_build_orchestrator`, `ContentSchemaError`, `sha256_of` (Plan 1A), `configure_logging`.
- Produces (`bunsho.services.health`): `ComponentHealth(status: Literal["ok","degraded","error"], detail: str = "", latency_ms: float = 0.0)`, `HealthReport(status, components: dict[str, ComponentHealth])`, `HealthService(progress_db: ProgressDatabase, ctx: Context)` with `async check() -> HealthReport` (components `progress_db`, `content_db`, `jamdict`; `progress_db` failing is `error`; content not built, content schema mismatch or jamdict unavailable is `degraded`; overall status is the worst component).
- Produces (`bunsho.services.config_check`): `CheckResult(name: str, ok: bool, detail: str)`; `run_config_checks(config: ServiceConfig, ctx: Context) -> list[CheckResult]` with checks `deck_present`, `deck_checksum`, `data_dir_writable`, `jamdict_available`.
- Produces (`bunsho.api`): `API_PREFIX = "/api/v1"`; `bunsho.api.services`: `Services` (slots dataclass: `config`, `ctx`, `progress_db`, `auth`, `throttle`, `tasks`, `health`; `async aclose()`), `ServiceOverrides(orchestrator_factory: OrchestratorFactory | None = None)`, `async build_services(config: ServiceConfig, overrides: ServiceOverrides | None = None) -> Services` (runs migrations in a thread, pings `progress.db`, builds the context in a thread; any failure disposes the engine and propagates — fail fast); `bunsho.api.deps`: `ServicesDep`, `CurrentUser` (`Annotated` dependencies), `require_user`, `get_services` (works for HTTP and WebSocket connections); `bunsho.api.app.create_app(config: ServiceConfig, *, overrides: ServiceOverrides | None = None) -> FastAPI` (lifespan builds services and stores them on `app.state.services`; explicit CORS only when `server.cors_origins` is set; mounts the routers under `API_PREFIX`); `GET /api/v1/health` (no auth; HTTP 503 when overall status is `error`, otherwise 200).
- Produces (`bunsho.api.schemas`): pydantic models `LoginRequest`, `RefreshRequest`, `TokenResponse`, `ComponentHealthModel`, `HealthResponse`, `CheckResultModel`, `ConfigCheckResponse`, `BuildRequest`, `BuildProgressModel`, `BuildReportModel`, `BuildStatusResponse`, `ContentSummaryResponse`, and converters `health_response(report) -> HealthResponse`, `build_status(task) -> BuildStatusResponse`, `config_check_response(results) -> ConfigCheckResponse`.
- Produces (`tests/base.py`): `make_service_config(tmp_path: Path, *, cors_origins: tuple[str, ...] = (), **auth_overrides: object) -> ServiceConfig` and fixture `service_config(tmp_path)`; (`tests/unit/api/conftest.py`): fixture `client` (a `TestClient` inside its lifespan).

- [ ] **Step 1: Write the failing tests**

Append to `tests/base.py` (merge imports at the top):

```python
from bunsho.config.service import ServerSettings, ServiceConfig


def make_service_config(
    tmp_path: Path, *, cors_origins: tuple[str, ...] = (), **auth_overrides: object
) -> ServiceConfig:
    """A ``ServiceConfig`` rooted in ``tmp_path`` for user ``james`` (see ``make_auth_settings``)."""
    app = AppConfig(
        data_dir=tmp_path / "data",
        resources_dir=tmp_path / "resources",
        deck_filename=DEFAULT_DECK_FILENAME,
        deck_sha256=DEFAULT_DECK_SHA256,
        jamdict_db=None,
        log_level="INFO",
    )
    return ServiceConfig(
        app=app,
        server=ServerSettings(host="127.0.0.1", port=8192, cors_origins=cors_origins),
        auth=make_auth_settings(**auth_overrides),
    )


@pytest.fixture
def service_config(tmp_path: Path) -> ServiceConfig:
    """A default ``ServiceConfig`` rooted in a temporary directory."""
    return make_service_config(tmp_path)
```

In `tests/conftest.py` add `service_config` to the import and to `__all__`:

```python
from tests.base import app_config, quiet_logger, service_config

__all__ = ["app_config", "quiet_logger", "service_config"]
```

`tests/unit/api/conftest.py` (with an empty `tests/unit/api/__init__.py`):

```python
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from bunsho.api.app import create_app
from bunsho.config.service import ServiceConfig


@pytest.fixture
def client(service_config: ServiceConfig) -> Iterator[TestClient]:
    with TestClient(create_app(service_config)) as test_client:
        yield test_client
```

`tests/unit/services/test_health.py`:

```python
import asyncio
from pathlib import Path

from bunsho.config.settings import AppConfig
from bunsho.context import Context
from bunsho.services.content_repository import CONTENT_SCHEMA_VERSION, ContentWriter
from bunsho.services.health import HealthService
from tests.base import FakeKanjiSource


class _Db:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    async def ping(self) -> None:
        if self.error is not None:
            raise self.error


def _ctx(app_config: AppConfig, quiet_logger, *, meta=None, jamdict=True) -> Context:  # type: ignore[no-untyped-def]
    ctx = Context(
        config=app_config,
        logger=quiet_logger,
        kanji_source=FakeKanjiSource() if jamdict else None,  # type: ignore[arg-type]
    )
    if meta is not None:
        ContentWriter().write(app_config.content_db_path, kana=[], kanji=[], vocab=[], meta=meta)
        ctx.refresh_content_repo()
    return ctx


def _check(db: _Db, ctx: Context):  # type: ignore[no-untyped-def]
    return asyncio.run(HealthService(db, ctx).check())  # type: ignore[arg-type]


def test_everything_ok(app_config: AppConfig, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    ctx = _ctx(app_config, quiet_logger, meta={"schema_version": CONTENT_SCHEMA_VERSION})
    report = _check(_Db(), ctx)
    assert report.status == "ok"
    assert {name: c.status for name, c in report.components.items()} == {
        "progress_db": "ok",
        "content_db": "ok",
        "jamdict": "ok",
    }
    assert report.components["progress_db"].latency_ms >= 0


def test_content_not_built_is_degraded(app_config: AppConfig, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    report = _check(_Db(), _ctx(app_config, quiet_logger))
    assert report.status == "degraded"
    assert report.components["content_db"].status == "degraded"
    assert "not built" in report.components["content_db"].detail


def test_content_schema_mismatch_is_degraded_with_a_rebuild_hint(
    app_config: AppConfig, quiet_logger
) -> None:  # type: ignore[no-untyped-def]
    report = _check(_Db(), _ctx(app_config, quiet_logger, meta={"schema_version": "0"}))
    assert report.components["content_db"].status == "degraded"
    assert "rebuild" in report.components["content_db"].detail


def test_missing_jamdict_is_degraded(app_config: AppConfig, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    ctx = _ctx(app_config, quiet_logger, meta={"schema_version": CONTENT_SCHEMA_VERSION}, jamdict=False)
    report = _check(_Db(), ctx)
    assert report.status == "degraded"
    assert report.components["jamdict"].status == "degraded"


def test_progress_db_failure_is_an_error(app_config: AppConfig, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    report = _check(_Db(OSError("disk gone")), _ctx(app_config, quiet_logger))
    assert report.status == "error"
    assert report.components["progress_db"].status == "error"
    assert "disk gone" in report.components["progress_db"].detail
```

`tests/unit/services/test_config_check.py`:

```python
import dataclasses
from pathlib import Path

from bunsho.context import Context
from bunsho.services.config_check import run_config_checks
from tests.apkg_builder import build_apkg, note
from tests.base import FakeKanjiSource, make_service_config


def _results(tmp_path: Path, quiet_logger, *, deck_sha: str | None = None, jamdict=True):  # type: ignore[no-untyped-def]
    config = make_service_config(tmp_path)
    if deck_sha is not None:
        config = dataclasses.replace(config, app=dataclasses.replace(config.app, deck_sha256=deck_sha))
    ctx = Context(
        config=config.app,
        logger=quiet_logger,
        kanji_source=FakeKanjiSource() if jamdict else None,  # type: ignore[arg-type]
    )
    return config, {r.name: r for r in run_config_checks(config, ctx)}


def test_missing_deck_fails_both_deck_checks(tmp_path: Path, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    _config, results = _results(tmp_path, quiet_logger)
    assert not results["deck_present"].ok
    assert not results["deck_checksum"].ok


def test_deck_with_the_wrong_checksum(tmp_path: Path, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    config = make_service_config(tmp_path)
    (tmp_path / "resources").mkdir()
    build_apkg(config.app.deck_path, [note("日", "にち")])
    _config, results = _results(tmp_path, quiet_logger)
    assert results["deck_present"].ok
    assert not results["deck_checksum"].ok


def test_deck_with_the_pinned_checksum(tmp_path: Path, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    config = make_service_config(tmp_path)
    (tmp_path / "resources").mkdir()
    sha = build_apkg(config.app.deck_path, [note("日", "にち")])
    _config, results = _results(tmp_path, quiet_logger, deck_sha=sha)
    assert results["deck_checksum"].ok


def test_data_dir_and_jamdict_checks(tmp_path: Path, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    _config, results = _results(tmp_path, quiet_logger)
    assert results["data_dir_writable"].ok
    assert results["jamdict_available"].ok
    _config, results = _results(tmp_path, quiet_logger, jamdict=False)
    assert not results["jamdict_available"].ok


def test_data_dir_that_is_a_file_is_not_writable(tmp_path: Path, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "data").write_text("in the way")
    _config, results = _results(tmp_path, quiet_logger)
    assert not results["data_dir_writable"].ok
```

`tests/unit/api/test_app_startup.py`:

```python
import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

from bunsho import __version__
from bunsho.api.app import create_app
from tests.base import make_service_config


def test_health_needs_no_auth_and_reports_components(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == __version__
    assert body["components"]["progress_db"]["status"] == "ok"
    assert body["components"]["content_db"]["status"] == "degraded"  # first run: not built yet
    assert body["status"] == "degraded"


def test_startup_migrates_progress_db(client: TestClient, service_config) -> None:  # type: ignore[no-untyped-def]
    with closing(sqlite3.connect(service_config.app.progress_db_path)) as con:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"card_state", "review_log", "app_setting"} <= tables
    assert not (service_config.app.data_dir / "backups").exists()


def test_cors_is_only_enabled_for_configured_origins(tmp_path: Path) -> None:
    config = make_service_config(tmp_path, cors_origins=("http://localhost:5173",))
    preflight = {"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"}
    with TestClient(create_app(config)) as client:
        allowed = client.options("/api/v1/health", headers=preflight)
        assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
        other = client.options(
            "/api/v1/health", headers={**preflight, "Origin": "http://evil.example"}
        )
        assert "access-control-allow-origin" not in other.headers


def test_no_cors_headers_without_configured_origins(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    assert "access-control-allow-origin" not in response.headers


def test_a_corrupt_progress_db_aborts_startup(tmp_path: Path) -> None:
    config = make_service_config(tmp_path)
    config.app.data_dir.mkdir(parents=True)
    config.app.progress_db_path.write_bytes(b"definitely not sqlite" * 20)
    import pytest

    with pytest.raises(Exception):  # noqa: B017,PT011 - sqlalchemy DatabaseError from the migration
        with TestClient(create_app(config)):
            pass
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/services/test_health.py tests/unit/services/test_config_check.py tests/unit/api -q`
Expected: FAIL (`ModuleNotFoundError: bunsho.services.health`, `bunsho.api`).

- [ ] **Step 3: Implement the health and config-check services**

`src/bunsho/services/health.py`:

```python
"""Health checks for the API service's dependencies."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from typing import Literal, Protocol

from bunsho.context import Context
from bunsho.services.content_repository import ContentSchemaError

Status = Literal["ok", "degraded", "error"]
_SEVERITY: dict[Status, int] = {"ok": 0, "degraded": 1, "error": 2}


class _Pingable(Protocol):
    async def ping(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ComponentHealth:
    """Health of one component."""

    status: Status
    detail: str = ""
    latency_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class HealthReport:
    """Overall health: the worst component status plus every component."""

    status: Status
    components: dict[str, ComponentHealth]


class HealthService:
    """Checks ``progress.db``, ``content.db`` and jamdict."""

    def __init__(self, progress_db: _Pingable, ctx: Context) -> None:
        """Create the service.

        Args:
            progress_db: Anything with ``async ping()`` (normally ``ProgressDatabase``).
            ctx: Application context holding the content repository and jamdict handle.
        """
        self._progress_db = progress_db
        self._ctx = ctx

    async def check(self) -> HealthReport:
        """Run every check; never raises."""
        components = {
            "progress_db": await self._check_progress_db(),
            "content_db": self._check_content_db(),
            "jamdict": self._check_jamdict(),
        }
        worst = max((c.status for c in components.values()), key=_SEVERITY.__getitem__)
        return HealthReport(status=worst, components=components)

    async def _check_progress_db(self) -> ComponentHealth:
        started = time.perf_counter()
        try:
            await self._progress_db.ping()
        except Exception as exc:
            elapsed = (time.perf_counter() - started) * 1000
            return ComponentHealth("error", f"{type(exc).__name__}: {exc}", elapsed)
        return ComponentHealth("ok", latency_ms=(time.perf_counter() - started) * 1000)

    def _check_content_db(self) -> ComponentHealth:
        repo = self._ctx.content_repo
        if repo is None:
            return ComponentHealth("degraded", "content.db not built yet; run a content build")
        started = time.perf_counter()
        try:
            repo.verify_schema()
        except ContentSchemaError as exc:
            return ComponentHealth("degraded", str(exc))
        except (sqlite3.Error, OSError) as exc:
            return ComponentHealth("degraded", f"content.db unreadable ({exc}); rebuild it")
        return ComponentHealth("ok", latency_ms=(time.perf_counter() - started) * 1000)

    def _check_jamdict(self) -> ComponentHealth:
        if self._ctx.kanji_source is None:
            return ComponentHealth("degraded", "jamdict database unavailable; builds are disabled")
        return ComponentHealth("ok")
```

`src/bunsho/services/config_check.py`:

```python
"""Environment suitability checks (what a config-check endpoint reports)."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass

from bunsho.config.service import ServiceConfig
from bunsho.context import Context
from bunsho.services.anki_importer import sha256_of


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Outcome of one check."""

    name: str
    ok: bool
    detail: str


def run_config_checks(config: ServiceConfig, ctx: Context) -> list[CheckResult]:
    """Check the deck, its checksum, the data directory and jamdict.

    Args:
        config: The loaded service configuration.
        ctx: The application context (for the jamdict handle).

    Returns:
        One result per check, in a stable order.
    """
    deck = config.app.deck_path
    present = deck.is_file()
    results = [CheckResult("deck_present", present, str(deck) if present else f"missing: {deck}")]
    if present:
        actual = sha256_of(deck)
        matches = actual == config.app.deck_sha256
        detail = "checksum matches" if matches else f"expected {config.app.deck_sha256}, got {actual}"
        results.append(CheckResult("deck_checksum", matches, detail))
    else:
        results.append(CheckResult("deck_checksum", False, "deck file missing"))
    try:
        config.app.data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=config.app.data_dir):
            pass
        results.append(CheckResult("data_dir_writable", True, str(config.app.data_dir)))
    except OSError as exc:
        results.append(CheckResult("data_dir_writable", False, f"{config.app.data_dir}: {exc}"))
    jamdict_ok = ctx.kanji_source is not None
    results.append(
        CheckResult(
            "jamdict_available",
            jamdict_ok,
            "ready" if jamdict_ok else "jamdict database unavailable; builds are disabled",
        )
    )
    return results
```

- [ ] **Step 4: Implement the API foundation**

`src/bunsho/api/__init__.py`:

```python
"""HTTP API (FastAPI)."""

API_PREFIX = "/api/v1"
```

`src/bunsho/api/schemas.py`:

```python
"""Pydantic request and response models for the API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from bunsho import __version__
from bunsho.orchestration.build_tasks import BuildState, BuildTask
from bunsho.services.config_check import CheckResult
from bunsho.services.health import HealthReport

Status = Literal["ok", "degraded", "error"]


class LoginRequest(BaseModel):
    """Credentials for ``POST /auth/login``."""

    username: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=1024)


class RefreshRequest(BaseModel):
    """Body of ``POST /auth/refresh``."""

    refresh_token: str = Field(min_length=1)


class TokenResponse(BaseModel):
    """An access and refresh token."""

    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int


class ComponentHealthModel(BaseModel):
    """Health of one component."""

    status: Status
    detail: str
    latency_ms: float


class HealthResponse(BaseModel):
    """Response of ``GET /health``."""

    status: Status
    version: str
    components: dict[str, ComponentHealthModel]


class CheckResultModel(BaseModel):
    """One config check."""

    name: str
    ok: bool
    detail: str


class ConfigCheckResponse(BaseModel):
    """Response of ``GET /admin/config-check``."""

    ok: bool
    checks: list[CheckResultModel]


class BuildRequest(BaseModel):
    """Body of ``POST /admin/content/build``."""

    dry_run: bool = False


class BuildProgressModel(BaseModel):
    """Progress of a running build."""

    stage: str
    current: int
    total: int


class BuildReportModel(BaseModel):
    """Summary of a finished build."""

    dry_run: bool
    target: str
    deck_sha256: str
    kana_count: int
    kanji_count: int
    unleveled_kanji_count: int
    vocab_count: int
    sentence_count: int
    vocab_by_level: dict[str, int]
    kanji_by_level: dict[str, int]
    kanji_without_details: int
    duration_seconds: float


class BuildStatusResponse(BaseModel):
    """State of a build task."""

    task_id: str
    state: BuildState
    dry_run: bool
    started_at: datetime
    finished_at: datetime | None
    progress: BuildProgressModel | None
    report: BuildReportModel | None
    error: str | None


class ContentSummaryResponse(BaseModel):
    """Response of ``GET /content/summary``."""

    built: bool
    kana: int = 0
    kanji: int = 0
    vocab: int = 0
    meta: dict[str, str] = Field(default_factory=dict)


def health_response(report: HealthReport) -> HealthResponse:
    """Convert a ``HealthReport`` to its response model."""
    return HealthResponse(
        status=report.status,
        version=__version__,
        components={
            name: ComponentHealthModel(
                status=c.status, detail=c.detail, latency_ms=round(c.latency_ms, 2)
            )
            for name, c in report.components.items()
        },
    )


def config_check_response(results: list[CheckResult]) -> ConfigCheckResponse:
    """Convert check results to the response model."""
    return ConfigCheckResponse(
        ok=all(r.ok for r in results),
        checks=[CheckResultModel(name=r.name, ok=r.ok, detail=r.detail) for r in results],
    )


def build_status(task: BuildTask) -> BuildStatusResponse:
    """Convert a ``BuildTask`` to its response model."""
    report = task.report
    return BuildStatusResponse(
        task_id=task.task_id,
        state=task.state,
        dry_run=task.dry_run,
        started_at=task.started_at,
        finished_at=task.finished_at,
        progress=(
            BuildProgressModel(
                stage=task.progress.stage,
                current=task.progress.current,
                total=task.progress.total,
            )
            if task.progress
            else None
        ),
        report=(
            BuildReportModel(
                dry_run=report.dry_run,
                target=str(report.target),
                deck_sha256=report.deck_sha256,
                kana_count=report.kana_count,
                kanji_count=report.kanji_count,
                unleveled_kanji_count=report.unleveled_kanji_count,
                vocab_count=report.vocab_count,
                sentence_count=report.sentence_count,
                vocab_by_level=report.vocab_by_level,
                kanji_by_level=report.kanji_by_level,
                kanji_without_details=report.kanji_without_details,
                duration_seconds=round(report.duration_seconds, 3),
            )
            if report
            else None
        ),
        error=task.error,
    )
```

`src/bunsho/api/services.py`:

```python
"""The API's shared service container and its construction."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from bunsho.config.service import ServiceConfig
from bunsho.context import Context
from bunsho.db.engine import ProgressDatabase
from bunsho.db.migrate import run_migrations
from bunsho.factories import create_content_build_orchestrator, create_context
from bunsho.orchestration.build_tasks import BuildTaskManager, OrchestratorFactory
from bunsho.services.auth import AuthService
from bunsho.services.health import HealthService
from bunsho.services.login_throttle import LoginThrottle


@dataclass(slots=True)
class Services:
    """Everything request handlers share."""

    config: ServiceConfig
    ctx: Context
    progress_db: ProgressDatabase
    auth: AuthService
    throttle: LoginThrottle
    tasks: BuildTaskManager
    health: HealthService

    async def aclose(self) -> None:
        """Wait briefly for an active build, then close the database engine."""
        await self.tasks.aclose()
        await self.progress_db.dispose()


@dataclass(frozen=True, slots=True)
class ServiceOverrides:
    """Test seams for ``build_services``."""

    orchestrator_factory: OrchestratorFactory | None = None


async def build_services(
    config: ServiceConfig, overrides: ServiceOverrides | None = None
) -> Services:
    """Migrate ``progress.db`` and wire every service.

    Args:
        config: Validated service configuration.
        overrides: Optional test seams.

    Returns:
        The service container.

    Raises:
        Exception: A migration or the ``progress.db`` ping failed (fail fast).
    """
    logger = logging.getLogger("bunsho")
    app_config = config.app
    await asyncio.to_thread(
        run_migrations,
        app_config.progress_db_path,
        backup_dir=app_config.data_dir / "backups",
        logger=logger,
    )
    progress_db = ProgressDatabase(app_config.progress_db_path)
    try:
        await progress_db.ping()
        ctx = await asyncio.to_thread(create_context, app_config, logger=logger)
        factory = (overrides.orchestrator_factory if overrides else None) or (
            create_content_build_orchestrator
        )
        return Services(
            config=config,
            ctx=ctx,
            progress_db=progress_db,
            auth=AuthService(config.auth),
            throttle=LoginThrottle(),
            tasks=BuildTaskManager(ctx, factory),
            health=HealthService(progress_db, ctx),
        )
    except BaseException:
        await progress_db.dispose()
        raise
```

`src/bunsho/api/deps.py`:

```python
"""FastAPI dependencies: shared services and the authenticated user."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.requests import HTTPConnection

from bunsho.api.services import Services
from bunsho.services.auth import AuthError

_bearer = HTTPBearer(auto_error=False)


def get_services(connection: HTTPConnection) -> Services:
    """Return the service container (works for HTTP requests and WebSockets)."""
    services: Services = connection.app.state.services
    return services


ServicesDep = Annotated[Services, Depends(get_services)]


def require_user(
    services: ServicesDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    """Validate the bearer access token and return the username.

    Raises:
        HTTPException: 401 when the token is missing, invalid or expired.
    """
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        return services.auth.authenticate(credentials.credentials)
    except AuthError as exc:
        raise unauthorized from exc


CurrentUser = Annotated[str, Depends(require_user)]
```

`src/bunsho/api/routers/__init__.py`:

```python
"""API routers."""
```

`src/bunsho/api/routers/health.py`:

```python
"""``GET /health`` (unauthenticated)."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from bunsho.api.deps import ServicesDep
from bunsho.api.schemas import HealthResponse, health_response

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def get_health(services: ServicesDep, response: Response) -> HealthResponse:
    """Report the health of the service's dependencies (503 when one is in error)."""
    report = await services.health.check()
    if report.status == "error":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return health_response(report)
```

`src/bunsho/api/app.py`:

```python
"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bunsho import APP_NAME, __version__
from bunsho.api import API_PREFIX
from bunsho.api.routers import health
from bunsho.api.services import ServiceOverrides, build_services
from bunsho.config.service import ServiceConfig
from bunsho.logging_setup import configure_logging


def create_app(
    config: ServiceConfig, *, overrides: ServiceOverrides | None = None
) -> FastAPI:
    """Build the FastAPI app.

    The lifespan migrates ``progress.db`` and wires the services; a failure there
    aborts startup.

    Args:
        config: Validated service configuration.
        overrides: Optional test seams.

    Returns:
        The application (routers are mounted under ``/api/v1``).
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(config.app.log_level, force=False)
        services = await build_services(config, overrides)
        app.state.services = services
        try:
            yield
        finally:
            await services.aclose()

    app = FastAPI(title=APP_NAME, version=__version__, lifespan=lifespan)
    if config.server.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(config.server.cors_origins),
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
        )
    app.include_router(health.router, prefix=API_PREFIX)
    return app
```

- [ ] **Step 5: Run tests and gates**

Run: `uv run pytest tests -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run bandit -r src/ -l`
Expected: all PASS. Notes: `test_a_corrupt_progress_db_aborts_startup` may raise `sqlalchemy.exc.DatabaseError`; keep the broad assertion. If mypy strict complains about the `Protocol` `...` body, keep it (it is excluded from coverage by the bare-ellipsis rule).

- [ ] **Step 6: Commit**

```bash
git add src/bunsho/services/health.py src/bunsho/services/config_check.py src/bunsho/api tests
git commit -m "feat(api): app factory, service container, health and config-check services" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: Auth, admin and content routers

**Files:**
- Create: `src/bunsho/api/routers/auth.py`, `src/bunsho/api/routers/admin.py`, `src/bunsho/api/routers/content.py`
- Modify: `src/bunsho/api/app.py` (mount the three routers), `tests/base.py` (shared build stub), `tests/unit/orchestration/test_build_tasks.py` (import the stub from `tests/base.py`), `tests/unit/api/conftest.py`
- Test: `tests/unit/api/test_auth_routes.py`, `tests/unit/api/test_admin_routes.py`

**Interfaces:**
- Consumes: everything from Tasks 1–6.
- Produces (all under `/api/v1`; bearer access token required unless stated):
  - `POST /auth/login` (no auth) — body `LoginRequest` → `TokenResponse`; wrong credentials → 401 with `WWW-Authenticate: Bearer` and the same body whether the username or the password was wrong; after 5 failures inside 60 s from one client address → 429 with a `Retry-After` header (even for correct credentials); the argon2 check runs in a worker thread; a successful login resets that client's failures.
  - `POST /auth/refresh` (no auth) — body `RefreshRequest` → `TokenResponse`; invalid, expired, or wrong-type token → 401.
  - `GET /admin/config-check` → `ConfigCheckResponse`.
  - `POST /admin/content/build` — body `BuildRequest` (`dry_run` default false) → **202** `BuildStatusResponse`; **409** while another build runs.
  - `GET /admin/content/build` → latest `BuildStatusResponse`, 404 if none; `GET /admin/content/build/{task_id}` → `BuildStatusResponse`, 404 if unknown.
  - `GET /content/summary` → `ContentSummaryResponse` (`built: false` and zero counts until a real build has finished).
  - Every admin and content route (and only the auth routes and `/health` are exempt) answers 401 with `WWW-Authenticate: Bearer` for a missing, invalid or expired token.
- Produces (`tests/base.py`): `make_build_report(dry_run: bool) -> BuildReport` and `StubOrchestrator(*, items: int = 3, gate: threading.Event | None = None, error: Exception | None = None)` with a `build(...)` method that emits progress, optionally blocks on `gate`, optionally raises `error`, writes an empty `content.db` on a non-dry run, and returns a report (moved from Task 5's test file). `tests/unit/api/conftest.py` gains fixtures `stub` (a `StubOrchestrator`), `stub_client` (a `TestClient` whose app uses `stub` as the orchestrator) and `auth_headers` (an `Authorization: Bearer` header obtained by logging in through the API).

- [ ] **Step 1: Move the build stub into the shared test base**

In `tests/unit/orchestration/test_build_tasks.py` delete the `_report` function and the `_Stub` class and instead import them from the shared module: `from tests.base import StubOrchestrator as _Stub` (keep the name `_Stub` at its call sites so the rest of the file is unchanged) and remove the now-unused imports (`BuildReport`, `ContentWriter`, `threading` only if unused).

Append to `tests/base.py` (merge imports at the top: `threading`, `BuildProgress`, `BuildReport`, `ContentWriter`):

```python
def make_build_report(dry_run: bool) -> BuildReport:
    """A small ``BuildReport`` for tests."""
    return BuildReport(
        dry_run=dry_run,
        target=Path("content.db"),
        deck_sha256="a" * 64,
        kana_count=208,
        kanji_count=3,
        vocab_count=2,
        sentence_count=0,
        vocab_by_level={"N5": 2},
        kanji_by_level={"N5": 3},
        kanji_without_details=0,
        duration_seconds=0.1,
    )


class StubOrchestrator:
    """Fake content build orchestrator: emits progress, optionally blocks, fails or writes."""

    def __init__(
        self,
        *,
        items: int = 3,
        gate: threading.Event | None = None,
        error: Exception | None = None,
    ) -> None:
        self.items = items
        self.gate = gate
        self.error = error

    def build(self, deck_path, target, *, dry_run=False, on_progress=None):  # type: ignore[no-untyped-def]
        """Pretend to build; see the class docstring."""
        assert on_progress is not None
        on_progress(BuildProgress("import_deck", 0, 1))
        on_progress(BuildProgress("import_deck", 1, 1))
        for index in range(1, self.items + 1):
            on_progress(BuildProgress("enrich_kanji", index, self.items))
        if self.gate is not None:
            assert self.gate.wait(10), "test gate was never released"
        if self.error is not None:
            raise self.error
        if not dry_run:
            on_progress(BuildProgress("write", 0, 1))
            ContentWriter().write(target, kana=[], kanji=[], vocab=[], meta={})
            on_progress(BuildProgress("write", 1, 1))
        return make_build_report(dry_run)
```

Run `uv run pytest tests/unit/orchestration/test_build_tasks.py -q` — Expected: still PASS.

- [ ] **Step 2: Write the failing API tests**

Replace `tests/unit/api/conftest.py` with:

```python
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from bunsho.api.app import create_app
from bunsho.api.services import ServiceOverrides
from bunsho.config.service import ServiceConfig
from tests.base import PASSWORD, StubOrchestrator


@pytest.fixture
def client(service_config: ServiceConfig) -> Iterator[TestClient]:
    with TestClient(create_app(service_config)) as test_client:
        yield test_client


@pytest.fixture
def stub() -> StubOrchestrator:
    return StubOrchestrator()


@pytest.fixture
def stub_client(service_config: ServiceConfig, stub: StubOrchestrator) -> Iterator[TestClient]:
    overrides = ServiceOverrides(orchestrator_factory=lambda _ctx: stub)  # type: ignore[arg-type,return-value]
    with TestClient(create_app(service_config, overrides=overrides)) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(stub_client: TestClient) -> dict[str, str]:
    response = stub_client.post(
        "/api/v1/auth/login", json={"username": "james", "password": PASSWORD}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
```

`tests/unit/api/test_auth_routes.py`:

```python
import pytest
from fastapi.testclient import TestClient

from tests.base import PASSWORD

LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
PROTECTED = [
    ("GET", "/api/v1/content/summary"),
    ("GET", "/api/v1/admin/config-check"),
    ("GET", "/api/v1/admin/content/build"),
    ("POST", "/api/v1/admin/content/build"),
]


def _login(client: TestClient, password: str = PASSWORD, username: str = "james"):  # type: ignore[no-untyped-def]
    return client.post(LOGIN, json={"username": username, "password": password})


def test_login_returns_tokens_that_open_protected_routes(client: TestClient) -> None:
    response = _login(client)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 15 * 60
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    assert client.get("/api/v1/content/summary", headers=headers).status_code == 200


def test_wrong_username_and_wrong_password_look_identical(client: TestClient) -> None:
    bad_password = _login(client, password="nope")
    bad_user = _login(client, username="mallory")
    assert bad_password.status_code == bad_user.status_code == 401
    assert bad_password.json() == bad_user.json()
    assert bad_password.headers["www-authenticate"] == "Bearer"


def test_login_is_throttled_after_repeated_failures(client: TestClient) -> None:
    for _ in range(5):
        assert _login(client, password="nope").status_code == 401
    blocked = _login(client, password="nope")
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert _login(client).status_code == 429  # even the right password waits


def test_login_body_is_validated(client: TestClient) -> None:
    assert client.post(LOGIN, json={"username": "james"}).status_code == 422
    assert client.post(LOGIN, json={"username": "", "password": ""}).status_code == 422


def test_refresh_issues_new_tokens_and_rejects_bad_ones(client: TestClient) -> None:
    tokens = _login(client).json()
    refreshed = client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] != tokens["access_token"]
    assert client.post(REFRESH, json={"refresh_token": tokens["access_token"]}).status_code == 401
    assert client.post(REFRESH, json={"refresh_token": "garbage"}).status_code == 401


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_protected_routes_reject_missing_and_bad_tokens(
    client: TestClient, method: str, path: str
) -> None:
    missing = client.request(method, path)
    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"
    bad = client.request(method, path, headers={"Authorization": "Bearer not-a-token"})
    assert bad.status_code == 401
    refresh_token = _login(client).json()["refresh_token"]
    wrong_type = client.request(method, path, headers={"Authorization": f"Bearer {refresh_token}"})
    assert wrong_type.status_code == 401
```

`tests/unit/api/test_admin_routes.py`:

```python
import threading
import time

from fastapi.testclient import TestClient

from tests.base import StubOrchestrator

BUILD = "/api/v1/admin/content/build"


def _wait(client: TestClient, headers: dict[str, str], task_id: str, timeout: float = 10.0) -> dict:  # type: ignore[type-arg]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"{BUILD}/{task_id}", headers=headers).json()
        if body["state"] != "running":
            return body  # type: ignore[no-any-return]
        time.sleep(0.02)
    raise AssertionError("build did not finish in time")


def test_config_check_reports_each_check(stub_client: TestClient, auth_headers: dict[str, str]) -> None:
    body = stub_client.get("/api/v1/admin/config-check", headers=auth_headers).json()
    names = [check["name"] for check in body["checks"]]
    assert names == ["deck_present", "deck_checksum", "data_dir_writable", "jamdict_available"]
    assert body["ok"] is False  # the test environment has no deck


def test_real_build_finishes_and_makes_content_visible(
    stub_client: TestClient, auth_headers: dict[str, str]
) -> None:
    summary_url = "/api/v1/content/summary"
    assert stub_client.get(summary_url, headers=auth_headers).json() == {
        "built": False, "kana": 0, "kanji": 0, "vocab": 0, "meta": {},
    }
    started = stub_client.post(BUILD, json={}, headers=auth_headers)
    assert started.status_code == 202
    body = started.json()
    assert body["state"] == "running" and body["dry_run"] is False
    finished = _wait(stub_client, auth_headers, body["task_id"])
    assert finished["state"] == "succeeded"
    assert finished["report"]["kana_count"] == 208
    assert finished["progress"]["stage"] == "write"
    assert stub_client.get(summary_url, headers=auth_headers).json()["built"] is True
    latest = stub_client.get(BUILD, headers=auth_headers).json()
    assert latest["task_id"] == body["task_id"]


def test_dry_run_builds_nothing(stub_client: TestClient, auth_headers: dict[str, str]) -> None:
    started = stub_client.post(BUILD, json={"dry_run": True}, headers=auth_headers).json()
    finished = _wait(stub_client, auth_headers, started["task_id"])
    assert finished["state"] == "succeeded" and finished["dry_run"] is True
    summary = stub_client.get("/api/v1/content/summary", headers=auth_headers).json()
    assert summary["built"] is False


def test_second_build_while_one_runs_gets_409(
    stub_client: TestClient, auth_headers: dict[str, str], stub: StubOrchestrator
) -> None:
    stub.gate = threading.Event()
    first = stub_client.post(BUILD, json={}, headers=auth_headers).json()
    conflict = stub_client.post(BUILD, json={}, headers=auth_headers)
    assert conflict.status_code == 409
    assert first["task_id"] in conflict.json()["detail"]
    stub.gate.set()
    assert _wait(stub_client, auth_headers, first["task_id"])["state"] == "succeeded"


def test_failed_build_is_reported(
    stub_client: TestClient, auth_headers: dict[str, str], stub: StubOrchestrator
) -> None:
    stub.error = RuntimeError("deck exploded")
    started = stub_client.post(BUILD, json={}, headers=auth_headers).json()
    finished = _wait(stub_client, auth_headers, started["task_id"])
    assert finished["state"] == "failed"
    assert finished["error"] == "RuntimeError: deck exploded"
    assert finished["report"] is None


def test_unknown_build_and_no_builds_yet_are_404(
    stub_client: TestClient, auth_headers: dict[str, str]
) -> None:
    assert stub_client.get(f"{BUILD}/nope", headers=auth_headers).status_code == 404
    assert stub_client.get(BUILD, headers=auth_headers).status_code == 404
```

- [ ] **Step 3: Run them to verify they fail**

Run: `uv run pytest tests/unit/api -q`
Expected: FAIL (404 on `/api/v1/auth/login` etc., because the routers are not mounted yet).

- [ ] **Step 4: Implement the routers**

`src/bunsho/api/routers/auth.py`:

```python
"""Login and token refresh."""

from __future__ import annotations

import asyncio
import math

from fastapi import APIRouter, HTTPException, Request, status

from bunsho.api.deps import ServicesDep
from bunsho.api.schemas import LoginRequest, RefreshRequest, TokenResponse
from bunsho.services.auth import AuthError, TokenPair

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(tokens: TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, services: ServicesDep) -> TokenResponse:
    """Exchange the configured username and password for tokens."""
    client = request.client.host if request.client else "unknown"
    wait = services.throttle.retry_after(client)
    if wait is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many failed logins; try again later",
            headers={"Retry-After": str(math.ceil(wait))},
        )
    valid = await asyncio.to_thread(services.auth.verify_credentials, body.username, body.password)
    if not valid:
        services.throttle.record_failure(client)
        services.ctx.logger.warning("login_failed client=%s", client)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    services.throttle.reset(client)
    return _token_response(services.auth.issue_tokens(services.config.auth.username))


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, services: ServicesDep) -> TokenResponse:
    """Exchange a refresh token for a new token pair."""
    try:
        return _token_response(services.auth.refresh(body.refresh_token))
    except AuthError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
```

`src/bunsho/api/routers/admin.py`:

```python
"""Administrative routes: environment check and content builds."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status

from bunsho.api.deps import ServicesDep, require_user
from bunsho.api.schemas import (
    BuildRequest,
    BuildStatusResponse,
    ConfigCheckResponse,
    build_status,
    config_check_response,
)
from bunsho.orchestration.build_tasks import BuildAlreadyRunningError
from bunsho.services.config_check import run_config_checks

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_user)])


@router.get("/config-check", response_model=ConfigCheckResponse)
async def config_check(services: ServicesDep) -> ConfigCheckResponse:
    """Check that the deck, data directory and dictionary are usable."""
    results = await asyncio.to_thread(run_config_checks, services.config, services.ctx)
    return config_check_response(results)


@router.post(
    "/content/build", response_model=BuildStatusResponse, status_code=status.HTTP_202_ACCEPTED
)
async def start_build(body: BuildRequest, services: ServicesDep) -> BuildStatusResponse:
    """Start a content build in the background (409 if one is already running)."""
    try:
        task = services.tasks.start(dry_run=body.dry_run)
    except BuildAlreadyRunningError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return build_status(task)


@router.get("/content/build", response_model=BuildStatusResponse)
async def latest_build(services: ServicesDep) -> BuildStatusResponse:
    """The most recent build, or 404 when none has run."""
    task = services.tasks.latest()
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no build has run yet")
    return build_status(task)


@router.get("/content/build/{task_id}", response_model=BuildStatusResponse)
async def get_build(task_id: str, services: ServicesDep) -> BuildStatusResponse:
    """A build by id, or 404 when unknown (only recent builds are remembered)."""
    task = services.tasks.get(task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown build")
    return build_status(task)
```

`src/bunsho/api/routers/content.py`:

```python
"""Read-only content routes."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from bunsho.api.deps import ServicesDep, require_user
from bunsho.api.schemas import ContentSummaryResponse

router = APIRouter(prefix="/content", tags=["content"], dependencies=[Depends(require_user)])


@router.get("/summary", response_model=ContentSummaryResponse)
async def content_summary(services: ServicesDep) -> ContentSummaryResponse:
    """Counts and build metadata for ``content.db`` (``built: false`` until a build ran)."""
    repo = services.ctx.content_repo
    if repo is None:
        return ContentSummaryResponse(built=False)
    counts = await asyncio.to_thread(repo.counts)
    meta = await asyncio.to_thread(repo.meta)
    return ContentSummaryResponse(
        built=True, kana=counts.kana, kanji=counts.kanji, vocab=counts.vocab, meta=meta
    )
```

In `src/bunsho/api/app.py` change the router import to `from bunsho.api.routers import admin, auth, content, health` and add, after the health router line:

```python
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(admin.router, prefix=API_PREFIX)
    app.include_router(content.router, prefix=API_PREFIX)
```

- [ ] **Step 5: Run tests and gates**

Run: `uv run pytest tests -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run bandit -r src/ -l`
Expected: all PASS. The login tests each hash or verify once (about 0.1 s); the throttle test performs six failed logins.

- [ ] **Step 6: Commit**

```bash
git add src/bunsho/api tests
git commit -m "feat(api): login, refresh, config-check, content build and summary routes" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 8: WebSocket task stream

**Files:**
- Create: `src/bunsho/api/routers/ws.py`
- Modify: `src/bunsho/api/schemas.py` (WebSocket message models), `src/bunsho/api/app.py` (mount the router)
- Test: `tests/unit/api/test_ws_routes.py`

**Interfaces:**
- Consumes: `BuildTaskManager.subscribe/unsubscribe/latest` (Task 5), `AuthService.authenticate` (Task 4), `ServicesDep`, `build_status` (Task 6).
- Produces: `WebSocket /api/v1/ws/tasks`. Protocol: the client connects and must send `{"type": "auth", "token": "<access token>"}` within `AUTH_TIMEOUT_SECONDS` (module constant, 5.0). A missing, malformed, late or invalid first message closes the socket with code **1008**. After a valid message the server sends `{"type": "ready"}`, then — if any build is remembered — `{"type": "snapshot", "task": <BuildStatusResponse>}`, then `{"type": "event", "event": {"kind": "progress" | "state", "task_id", "state", "progress": {stage, current, total} | null, "error": str | null}}` for every subsequent build event, until the client disconnects. Client messages after auth are ignored. The socket is subscribed **before** the snapshot is sent so no event is missed (a snapshot may repeat the latest progress).
- Produces (`bunsho.api.schemas`): `WsAuthMessage(type: Literal["auth"], token: str)`, `WsReady(type: Literal["ready"] = "ready")`, `BuildEventModel(kind, task_id, state, progress, error)`, `WsSnapshot(type: Literal["snapshot"] = "snapshot", task: BuildStatusResponse)`, `WsEvent(type: Literal["event"] = "event", event: BuildEventModel)`, converter `build_event(event: BuildEvent) -> BuildEventModel`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/api/test_ws_routes.py`:

```python
import time

import pytest
from starlette.websockets import WebSocketDisconnect
from fastapi.testclient import TestClient

from tests.base import PASSWORD

WS = "/api/v1/ws/tasks"
BUILD = "/api/v1/admin/content/build"


def _login(client: TestClient) -> dict:  # type: ignore[type-arg]
    return client.post(  # type: ignore[no-any-return]
        "/api/v1/auth/login", json={"username": "james", "password": PASSWORD}
    ).json()


def _connect_and_expect_close(client: TestClient, first_message: object | None) -> int:
    with pytest.raises(WebSocketDisconnect) as info:
        with client.websocket_connect(WS) as ws:
            if isinstance(first_message, str):
                ws.send_text(first_message)
            elif first_message is not None:
                ws.send_json(first_message)
            ws.receive_json()
    return info.value.code


@pytest.mark.parametrize(
    "first_message",
    [
        {"type": "auth", "token": "bad-token"},
        {"type": "hello"},
        {"type": "auth"},
        ["not", "an", "object"],
        "this is not json",
    ],
)
def test_bad_first_messages_close_with_1008(stub_client: TestClient, first_message: object) -> None:
    assert _connect_and_expect_close(stub_client, first_message) == 1008


def test_a_refresh_token_cannot_authenticate_the_socket(stub_client: TestClient) -> None:
    tokens = _login(stub_client)
    message = {"type": "auth", "token": tokens["refresh_token"]}
    assert _connect_and_expect_close(stub_client, message) == 1008


def test_silence_times_out_with_1008(
    stub_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("bunsho.api.routers.ws.AUTH_TIMEOUT_SECONDS", 0.2)
    assert _connect_and_expect_close(stub_client, None) == 1008


def test_events_are_streamed_for_a_build_started_after_connecting(stub_client: TestClient) -> None:
    tokens = _login(stub_client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    with stub_client.websocket_connect(WS) as ws:
        ws.send_json({"type": "auth", "token": tokens["access_token"]})
        assert ws.receive_json() == {"type": "ready"}
        started = stub_client.post(BUILD, json={}, headers=headers)
        assert started.status_code == 202
        task_id = started.json()["task_id"]
        messages = []
        while True:
            message = ws.receive_json()
            messages.append(message)
            event = message["event"]
            if event["kind"] == "state" and event["state"] != "running":
                break
    assert all(m["type"] == "event" and m["event"]["task_id"] == task_id for m in messages)
    assert (messages[0]["event"]["kind"], messages[0]["event"]["state"]) == ("state", "running")
    assert messages[-1]["event"]["state"] == "succeeded"
    stages = [m["event"]["progress"]["stage"] for m in messages if m["event"]["progress"]]
    assert stages[0] == "import_deck" and stages[-1] == "write"


def test_a_late_client_gets_a_snapshot_of_the_latest_build(stub_client: TestClient) -> None:
    tokens = _login(stub_client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    task_id = stub_client.post(BUILD, json={"dry_run": True}, headers=headers).json()["task_id"]
    deadline = time.monotonic() + 10
    while stub_client.get(f"{BUILD}/{task_id}", headers=headers).json()["state"] == "running":
        assert time.monotonic() < deadline
        time.sleep(0.02)
    with stub_client.websocket_connect(WS) as ws:
        ws.send_json({"type": "auth", "token": tokens["access_token"]})
        assert ws.receive_json() == {"type": "ready"}
        snapshot = ws.receive_json()
    assert snapshot["type"] == "snapshot"
    assert snapshot["task"]["task_id"] == task_id
    assert snapshot["task"]["state"] == "succeeded"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/api/test_ws_routes.py -q`
Expected: FAIL (the WebSocket route does not exist; connecting raises).

- [ ] **Step 3: Implement**

Append to `src/bunsho/api/schemas.py` (add `BuildEvent` to the `bunsho.orchestration.build_tasks` import):

```python
class WsAuthMessage(BaseModel):
    """First message a WebSocket client must send."""

    type: Literal["auth"]
    token: str = Field(min_length=1)


class WsReady(BaseModel):
    """Sent once after a successful WebSocket authentication."""

    type: Literal["ready"] = "ready"


class BuildEventModel(BaseModel):
    """A build event as sent over the WebSocket."""

    kind: Literal["progress", "state"]
    task_id: str
    state: BuildState
    progress: BuildProgressModel | None
    error: str | None


class WsSnapshot(BaseModel):
    """The latest known build, sent right after ``ready``."""

    type: Literal["snapshot"] = "snapshot"
    task: BuildStatusResponse


class WsEvent(BaseModel):
    """One build event."""

    type: Literal["event"] = "event"
    event: BuildEventModel


def build_event(event: BuildEvent) -> BuildEventModel:
    """Convert a ``BuildEvent`` to its WebSocket model."""
    progress = event.progress
    return BuildEventModel(
        kind=event.kind,
        task_id=event.task_id,
        state=event.state,
        progress=(
            BuildProgressModel(stage=progress.stage, current=progress.current, total=progress.total)
            if progress
            else None
        ),
        error=event.error,
    )
```

`src/bunsho/api/routers/ws.py`:

```python
"""WebSocket stream of build events."""

from __future__ import annotations

import asyncio
from contextlib import suppress

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from bunsho.api.deps import ServicesDep
from bunsho.api.schemas import (
    WsAuthMessage,
    WsEvent,
    WsReady,
    WsSnapshot,
    build_event,
    build_status,
)
from bunsho.orchestration.build_tasks import BuildEvent
from bunsho.services.auth import AuthError

router = APIRouter(tags=["ws"])

AUTH_TIMEOUT_SECONDS = 5.0
POLICY_VIOLATION = 1008


async def _forward(websocket: WebSocket, queue: asyncio.Queue[BuildEvent]) -> None:
    while True:
        event = await queue.get()
        await websocket.send_json(WsEvent(event=build_event(event)).model_dump(mode="json"))


async def _authenticate(websocket: WebSocket, services: ServicesDep) -> bool:
    """Read the first message and validate the access token; close the socket on failure."""
    try:
        raw = await asyncio.wait_for(websocket.receive_json(), AUTH_TIMEOUT_SECONDS)
        message = WsAuthMessage.model_validate(raw)
        services.auth.authenticate(message.token)
    except WebSocketDisconnect:
        return False
    except (TimeoutError, ValueError, ValidationError, AuthError):
        with suppress(RuntimeError):
            await websocket.close(code=POLICY_VIOLATION)
        return False
    return True


@router.websocket("/ws/tasks")
async def task_stream(websocket: WebSocket, services: ServicesDep) -> None:
    """Authenticate with a first message, then stream build events until disconnect."""
    await websocket.accept()
    if not await _authenticate(websocket, services):
        return
    queue = services.tasks.subscribe()
    sender: asyncio.Task[None] | None = None
    try:
        await websocket.send_json(WsReady().model_dump())
        latest = services.tasks.latest()
        if latest is not None:
            await websocket.send_json(WsSnapshot(task=build_status(latest)).model_dump(mode="json"))
        sender = asyncio.create_task(_forward(websocket, queue))
        async for _ in websocket.iter_text():
            pass  # client messages after authentication are ignored
    except WebSocketDisconnect:
        pass
    finally:
        services.tasks.unsubscribe(queue)
        if sender is not None:
            sender.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await sender
```

In `src/bunsho/api/app.py` change the router import to include `ws` (`from bunsho.api.routers import admin, auth, content, health, ws`) and add `app.include_router(ws.router, prefix=API_PREFIX)` after the content router.

- [ ] **Step 4: Run tests and gates**

Run: `uv run pytest tests -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run bandit -r src/ -l`
Expected: all PASS. If a WebSocket test hangs, the awaited message never arrives: interrupt, and check that `subscribe()` happens before `ready` and that the stub's final state event is published.

- [ ] **Step 5: Commit**

```bash
git add src/bunsho/api tests/unit/api
git commit -m "feat(api): authenticated WebSocket stream of build events" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 9: Launcher, README, end-to-end test

**Files:**
- Create: `src/bunsho/main.py`, `tests/unit/test_main.py`, `tests/integration/test_api_end_to_end.py`
- Modify: `pyproject.toml` (console script), `README.md`

**Interfaces:**
- Produces (`bunsho.main`): `CONFIG_FILE_ENV = "BUNSHO_CONFIG_FILE"`, `ENV_FILE_ENV = "BUNSHO_ENV_FILE"`; `build_service_config(environ: Mapping[str, str] | None = None) -> ServiceConfig` (TOML file from `BUNSHO_CONFIG_FILE`, `.env` from `BUNSHO_ENV_FILE` or `./.env` when it exists, then the environment; raises `ConfigError` listing every problem); `create_app_from_env() -> FastAPI` (an `uvicorn --factory` target: `uv run uvicorn --factory bunsho.main:create_app_from_env`); `main() -> None` (the `bunsho` console script: logs a configuration error and exits with status 2, otherwise configures logging and runs uvicorn on `server.host:server.port`).

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_main.py`:

```python
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
    assert "username" in message and "password_hash" in message and "jwt_secret" in message


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
```

`tests/integration/test_api_end_to_end.py`:

```python
import dataclasses
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bunsho.api.app import create_app
from bunsho.api.services import ServiceOverrides
from bunsho.config.service import ServiceConfig
from bunsho.context import Context
from bunsho.orchestration.content_build import ContentBuildOrchestrator
from bunsho.services.anki_importer import AnkiDeckImporter
from bunsho.services.content_repository import ContentWriter
from bunsho.services.kana_source import KanaSource
from tests.apkg_builder import build_apkg, note
from tests.base import PASSWORD, FakeKanjiSource, make_service_config


def _config_with_a_synthetic_deck(tmp_path: Path) -> ServiceConfig:
    config = make_service_config(tmp_path)
    (tmp_path / "resources").mkdir()
    sha = build_apkg(
        config.app.deck_path,
        [note("日本", "日本[にほん]"), note("学生", "学生[がくせい]", "jlpt_N4")],
    )
    return dataclasses.replace(config, app=dataclasses.replace(config.app, deck_sha256=sha))


def _real_orchestrator(ctx: Context) -> ContentBuildOrchestrator:
    return ContentBuildOrchestrator(
        importer=AnkiDeckImporter(ctx.config.deck_sha256, ctx.logger),
        kana_provider=KanaSource(),
        kanji_source=FakeKanjiSource(),  # type: ignore[arg-type]
        writer=ContentWriter(),
        logger=ctx.logger,
    )


@pytest.mark.integration
def test_login_build_stream_and_restart(tmp_path: Path) -> None:
    config = _config_with_a_synthetic_deck(tmp_path)
    overrides = ServiceOverrides(orchestrator_factory=_real_orchestrator)
    with TestClient(create_app(config, overrides=overrides)) as client:
        tokens = client.post(
            "/api/v1/auth/login", json={"username": "james", "password": PASSWORD}
        ).json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        checks = client.get("/api/v1/admin/config-check", headers=headers).json()
        assert {c["name"]: c["ok"] for c in checks["checks"]}["deck_checksum"] is True

        with client.websocket_connect("/api/v1/ws/tasks") as ws:
            ws.send_json({"type": "auth", "token": tokens["access_token"]})
            assert ws.receive_json() == {"type": "ready"}
            assert client.post("/api/v1/admin/content/build", json={}, headers=headers).status_code == 202
            while True:
                event = ws.receive_json()["event"]
                if event["kind"] == "state" and event["state"] != "running":
                    break
        assert event["state"] == "succeeded"

        summary = client.get("/api/v1/content/summary", headers=headers).json()
        assert summary["built"] is True
        assert (summary["kana"], summary["kanji"], summary["vocab"]) == (208, 4, 2)
        assert client.get("/api/v1/health").json()["components"]["content_db"]["status"] == "ok"

    # A restarted service sees the same progress.db and the built content.db, without a backup.
    with TestClient(create_app(config, overrides=overrides)) as client:
        headers = {
            "Authorization": "Bearer "
            + client.post(
                "/api/v1/auth/login", json={"username": "james", "password": PASSWORD}
            ).json()["access_token"]
        }
        assert client.get("/api/v1/content/summary", headers=headers).json()["vocab"] == 2
    assert not (config.app.data_dir / "backups").exists()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_main.py tests/integration/test_api_end_to_end.py -q`
Expected: FAIL (`ModuleNotFoundError: bunsho.main`; the end-to-end test needs no new module and should already pass once routers exist — if it passes now, that is fine, it is a regression guard).

- [ ] **Step 3: Implement the launcher**

`src/bunsho/main.py`:

```python
"""Process entry points: build the app from the environment and run uvicorn."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from bunsho.api.app import create_app
from bunsho.config.loader import load_config
from bunsho.config.normalizer import ConfigError
from bunsho.config.service import ServiceConfig, load_service_config
from bunsho.logging_setup import configure_logging

CONFIG_FILE_ENV = "BUNSHO_CONFIG_FILE"
ENV_FILE_ENV = "BUNSHO_ENV_FILE"


def build_service_config(environ: Mapping[str, str] | None = None) -> ServiceConfig:
    """Load and validate the service configuration.

    Layers, lowest to highest precedence: the TOML file named by ``BUNSHO_CONFIG_FILE``,
    the ``.env`` file named by ``BUNSHO_ENV_FILE`` (default ``./.env`` when it exists),
    then the environment.

    Raises:
        ConfigError: Listing every problem found.
    """
    env = os.environ if environ is None else environ
    config_file = Path(env[CONFIG_FILE_ENV]) if env.get(CONFIG_FILE_ENV) else None
    if env.get(ENV_FILE_ENV):
        env_file: Path | None = Path(env[ENV_FILE_ENV])
    else:
        env_file = Path(".env") if Path(".env").is_file() else None
    return load_service_config(load_config(config_file=config_file, env_file=env_file, environ=env))


def create_app_from_env() -> FastAPI:
    """Application factory for ``uvicorn --factory bunsho.main:create_app_from_env``."""
    return create_app(build_service_config())


def main() -> None:  # pragma: no cover - thin process wrapper, exercised by hand
    """Run the service (the ``bunsho`` console script)."""
    configure_logging("INFO")
    try:
        config = build_service_config()
    except ConfigError as exc:
        logging.getLogger("bunsho").error("configuration_invalid\n%s", exc)
        raise SystemExit(2) from exc
    configure_logging(config.app.log_level)
    uvicorn.run(
        create_app(config), host=config.server.host, port=config.server.port, log_config=None
    )
```

Add to `pyproject.toml`, after the `[project.optional-dependencies]` table:

```toml
[project.scripts]
bunsho = "bunsho.main:main"
```

- [ ] **Step 4: Document how to run it**

Append to `README.md` (after the License section is fine; the sections below are new):

````markdown
## Running the service

Bunshō serves an authenticated REST + WebSocket API (interactive docs at `/docs`).

1. Create a password hash (it never leaves your machine):

   ```bash
   uv run python -c "import getpass; from pwdlib import PasswordHash; print(PasswordHash.recommended().hash(getpass.getpass()))"
   ```

2. Put the settings in a `.env` file next to where you start it (never commit it). Quote the hash: it contains `$`.

   ```env
   BUNSHO_AUTH__USERNAME=james
   BUNSHO_AUTH__PASSWORD_HASH='$argon2id$v=19$...'
   BUNSHO_AUTH__JWT_SECRET=<at least 32 random characters, e.g. python -c "import secrets; print(secrets.token_urlsafe(48))">
   ```

3. Start it with `uv run bunsho` (default `127.0.0.1:8192`). Log in with `POST /api/v1/auth/login`, then start a
   content build with `POST /api/v1/admin/content/build` and follow it over `WebSocket /api/v1/ws/tasks`
   (send `{"type": "auth", "token": "<access token>"}` first).

Other settings (environment variables `BUNSHO_<SECTION>__<KEY>`, or a TOML file named by `BUNSHO_CONFIG_FILE`):
`server.host`, `server.port` (never 8000), `server.cors_origins` (comma separated), `auth.access_ttl_minutes`,
`auth.refresh_ttl_days`, `paths.data_dir`, `paths.resources_dir`, `paths.jamdict_db`, `logging.level`.
`progress.db` (your study history) lives in `data_dir`; it is migrated at startup after a timestamped backup in
`data_dir/backups/`.
````

- [ ] **Step 5: Run the full suite and every gate**

Run:
```bash
uv run pytest --cov=src -q
uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run bandit -r src/ -l
uv build --wheel --out-dir <scratch dir>   # confirm migrations and the console script are in the wheel
```
Expected: all PASS; coverage `>= 90%`. Then start it by hand once: `uv run bunsho` with a real `.env`, open `http://127.0.0.1:8192/docs`, log in, run a **dry-run** build, and confirm the WebSocket reports progress (the real deck build takes about 30 seconds).

- [ ] **Step 6: Commit**

```bash
git add src/bunsho/main.py pyproject.toml README.md tests
git commit -m "feat: bunsho launcher, run instructions and end-to-end API test" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Self-review against the spec

- **`progress.db` + Alembic + timestamped backup at startup:** Task 3 (runner) and Task 6 (`build_services`), tested in Task 6 and Task 9.
- **JWT auth for all REST and WebSocket routes, single local user:** Tasks 4, 6, 7, 8 (login/refresh exempt, `/health` exempt).
- **`/api/v1` routes — health, config-check, content build with `dry_run`, background task, WebSocket progress:** Tasks 5–8.
- **Config validated at startup, all failures reported together; CORS explicit; port 8000 rejected:** Tasks 1, 6, 9.
- **Startup behaviour (`progress.db` fail-fast, `content.db` missing = first-run state, jamdict optional):** Task 6 (`build_services`, health `degraded`).
- **`bunsho` launcher (uvicorn, no click/rich):** Task 9.
- **Plan 1A carry-forward items closed here:** Windows `os.replace` retry, `on_progress` guard, `content_build_failed` log, dry run as a background task, `create_context` widening, loader `ConfigError` wrapping, `data_dir` validation, `verify_schema()` used by health, `configure_logging(force=False)` (Tasks 1, 2, 5, 6, 9).
- **Deliberately left for Plan 1C:** Dockerfile and compose (Python-only image first; the Node stage arrives with Plan 2), CI rewrite, `.claude/skills` and `settings.local.json` Jidou cleanup (needs the user's decision on the `.gitignore`), `py.typed`, `.pre-commit-config.yaml`, integration tests failing (not skipping) when `CI` is set, `bandit -c pyproject.toml` in CI.

Type-consistency check: `Services` fields used by the routers (`auth`, `throttle`, `tasks`, `health`, `ctx`, `config`) match Task 6's dataclass; `BuildTaskManager` methods used by routers (`start`, `get`, `latest`, `subscribe`, `unsubscribe`) match Task 5; schema converters (`build_status`, `config_check_response`, `health_response`, `build_event`) are defined in Tasks 6 and 8 with the names used in Tasks 7 and 8; `StubOrchestrator` and `make_build_report` are defined in Task 7 and used by Tasks 7–8.
