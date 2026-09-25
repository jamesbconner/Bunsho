# Session Revocation and Logout Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Log out end the login session on the server (refresh token and every access token of that login), close that session's open WebSockets, and stop a refresh in flight from undoing a logout.

**Architecture:** Every login gets a `sid` claim shared by all its tokens. A `revoked_session` table in `progress.db` (migration 0002) plus a write-through in-memory map holds revoked sids; `AuthService._decode` consults the map. `POST /auth/logout` revokes the sid and an orchestration function closes that sid's sockets from a `SessionSockets` registry. The frontend calls the endpoint best-effort on logout and guards `session.ts` with an epoch counter so late refresh results are dropped.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async + Alembic, PyJWT, pytest (no pytest-asyncio: async tests use `asyncio.run` / `run_with_database`); React 18+, TypeScript, Vitest, MSW, Testing Library.

**Spec:** `docs/superpowers/specs/2026-09-25-bunsho-session-revocation-design.md`

## Global Constraints

- Branch `feat/session-revocation` (already created; the spec is committed on it). Never merge; James reviews and merges.
- Commits: conventional commits, stage explicit paths only, `git commit -m "<subject>" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"` (the trailer is its own paragraph). Never stage `.gitignore`, `.github/`, `.python-version`, `.superpowers/`, `.env.example`.
- Version becomes **1.4.0** (Task 7 only). Every commit before that leaves the version alone.
- New table is `revoked_session` (singular, like `card_state`), Alembic revision `0002`, `down_revision = "0001"`.
- A revoked sid stays revoked until **now + `refresh_ttl_days`**, never until the presented token's own `exp`.
- `POST /auth/logout`: body `{refresh_token}`, no bearer, **always 204** for any verifiable-or-not token, never touches the login throttle.
- Open sockets of a revoked session close with code **1008**.
- Tokens without a `sid` claim are rejected (the user logs in once after the upgrade).
- `is_revoked` is synchronous and reads memory only (it runs on every request and socket connect).
- Python: type annotations on everything public, Google-style docstrings, `ruff check .`, `ruff format --check .`, `mypy src/`, `bandit -c pyproject.toml -r src/ -l`, coverage stays >= 90 (`pytest --cov`). Frontend: strict TypeScript, `npm run format:check`, `npm run lint`, `npm run build`, `npm run coverage`.
- Tests: no pytest-asyncio; async code is driven with `asyncio.run(...)` or `tests.base.run_with_database`. Frontend MSW runs with `onUnhandledRequest: 'error'`, so any test that logs out through the real `AuthProvider` needs a `/api/v1/auth/logout` handler.
- Windows quirks: `unset VIRTUAL_ENV` before every `uv` command; quote the `Bunshō` path; `PYTHONIOENCODING=utf-8` when printing Japanese; write files with the Write/Edit tools, not shell heredocs; Python edits can leave CRLF (`ruff format` fixes it); TS edits: run `npm run format` in `frontend/`.
- Subagents: this project's hook demands `graphify query "<question>"` before reading or grepping source files. Put that instruction in every subagent prompt.

## Review Focus

The five failure modes the spec implies but a per-task happy path would miss, most likely first. Each has a pinning test in the task named in brackets.

1. **Logout while the server is unreachable (or returns an error):** the user must still be logged out locally, with no unhandled rejection. [Task 6]
2. **Server restart between login and logout, and between logout and the next request:** the revocation must survive (`load()` from SQLite). A restart must not resurrect a revoked session. [Task 4]
3. **Garbage, expired, wrong-type, empty-body and already-revoked tokens sent to `/auth/logout`:** all 204 with no oracle, and an access token or a flood of bad calls must neither revoke anything nor block `/auth/login`. [Task 4]
4. **A token issued before the upgrade (no `sid`) sitting in `localStorage`:** refresh must answer 401, which the UI already treats as "signed out". [Task 2]
5. **A socket that connects after its session was revoked, and a second session's socket during a logout:** the first is refused with 1008; the second keeps streaming. [Task 4]

---

## File Structure

| File | Responsibility |
|---|---|
| `src/bunsho/db/models.py` (modify) | `RevokedSession` ORM model |
| `src/bunsho/db/migrations/versions/0002_revoked_session.py` (create) | Creates/drops the table |
| `src/bunsho/db/revoked_session_store.py` (create) | `RevokedSessionStore`: SQLite persistence + in-memory map |
| `src/bunsho/services/protocols.py` (modify) | `SessionRevocations` port |
| `src/bunsho/services/session_revocations.py` (create) | `MemorySessionRevocations` (default and test fake) |
| `src/bunsho/services/auth.py` (modify) | `sid` claim, `SessionClaims`, `authenticate_session`, `revoke` |
| `src/bunsho/orchestration/session_sockets.py` (create) | `SessionSockets` registry: sid -> open sockets |
| `src/bunsho/orchestration/session_logout.py` (create) | `logout_session`: revoke, then close sockets |
| `src/bunsho/api/services.py` (modify) | Wire the store (load at startup) and `SessionSockets` |
| `src/bunsho/api/schemas.py` (modify) | `LogoutRequest` |
| `src/bunsho/api/routers/auth.py` (modify) | `POST /auth/logout` |
| `src/bunsho/api/routers/ws.py` (modify) | Authenticate to a session, register/unregister the socket |
| `frontend/src/auth/session.ts` (modify) | Epoch counter, guarded `setTokens`/`expire` |
| `frontend/src/api/client.ts` (modify) | Epoch-aware refresh, `revokeSession` |
| `frontend/src/auth/AuthProvider.tsx` (modify) | Logout calls the server |
| `frontend/src/components/AppLayout.tsx` (modify) | Corrected note beside Log out |
| `frontend/src/realtime/streamLifecycle.test.tsx` (create) | Logout -> login stream lifecycle, StrictMode |

---

### Task 1: Revocation port, store and migration 0002

**Files:**
- Modify: `src/bunsho/db/models.py` (append a model)
- Create: `src/bunsho/db/migrations/versions/0002_revoked_session.py`
- Modify: `src/bunsho/services/protocols.py` (append a Protocol)
- Create: `src/bunsho/services/session_revocations.py`
- Create: `src/bunsho/db/revoked_session_store.py`
- Modify: `tests/unit/db/test_migrate.py` (revision assertions, add downgrade test)
- Create: `tests/unit/db/test_revoked_session_store.py`
- Create: `tests/unit/services/test_session_revocations.py`

**Interfaces:**
- Consumes: `ProgressDatabase.sessions()` (`bunsho.db.engine`), `format_timestamp`/`parse_timestamp` (`bunsho.db.timestamps`), `tests.base.run_with_database`.
- Produces:
  - `bunsho.services.protocols.SessionRevocations` (Protocol): `def is_revoked(self, sid: str) -> bool` and `async def revoke(self, sid: str, expires_at: datetime) -> None`.
  - `bunsho.services.session_revocations.MemorySessionRevocations()`: implements the port; extra `def expiry(self, sid: str) -> datetime | None`.
  - `bunsho.db.revoked_session_store.RevokedSessionStore(database: ProgressDatabase, *, clock: Callable[[], datetime] | None = None)`: implements the port; extra `async def load(self) -> None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/services/test_session_revocations.py`:

```python
import asyncio
from datetime import UTC, datetime, timedelta

from bunsho.services.session_revocations import MemorySessionRevocations

NOW = datetime(2026, 1, 2, tzinfo=UTC)


def test_a_session_is_revoked_only_after_revoke() -> None:
    revocations = MemorySessionRevocations()
    assert revocations.is_revoked("sid-a") is False
    asyncio.run(revocations.revoke("sid-a", NOW + timedelta(days=30)))
    assert revocations.is_revoked("sid-a") is True
    assert revocations.is_revoked("sid-b") is False


def test_expiry_reports_when_the_revocation_lapses() -> None:
    revocations = MemorySessionRevocations()
    assert revocations.expiry("sid-a") is None
    asyncio.run(revocations.revoke("sid-a", NOW + timedelta(days=30)))
    assert revocations.expiry("sid-a") == NOW + timedelta(days=30)
```

Create `tests/unit/db/test_revoked_session_store.py`:

```python
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from bunsho.db.engine import ProgressDatabase
from bunsho.db.models import RevokedSession
from bunsho.db.revoked_session_store import RevokedSessionStore
from tests.base import run_with_database

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


async def _stored_sids(database: ProgressDatabase) -> list[str]:
    async with database.sessions() as session:
        return sorted((await session.scalars(select(RevokedSession.sid))).all())


def test_a_revoked_session_is_revoked_and_another_is_not(tmp_path: Path) -> None:
    async def scenario(database: ProgressDatabase) -> tuple[bool, bool]:
        store = RevokedSessionStore(database, clock=lambda: NOW)
        await store.revoke("sid-a", NOW + timedelta(days=30))
        return store.is_revoked("sid-a"), store.is_revoked("sid-b")

    assert run_with_database(tmp_path, scenario) == (True, False)


def test_a_new_instance_sees_revocations_only_after_load(tmp_path: Path) -> None:
    async def scenario(database: ProgressDatabase) -> tuple[bool, bool]:
        first = RevokedSessionStore(database, clock=lambda: NOW)
        await first.revoke("sid-a", NOW + timedelta(days=30))
        second = RevokedSessionStore(database, clock=lambda: NOW)
        before = second.is_revoked("sid-a")
        await second.load()
        return before, second.is_revoked("sid-a")

    assert run_with_database(tmp_path, scenario) == (False, True)


def test_load_prunes_rows_whose_revocation_has_lapsed(tmp_path: Path) -> None:
    async def scenario(database: ProgressDatabase) -> tuple[bool, bool, list[str]]:
        early = RevokedSessionStore(database, clock=lambda: NOW)
        await early.revoke("old", NOW + timedelta(days=1))
        await early.revoke("fresh", NOW + timedelta(days=30))
        later = RevokedSessionStore(database, clock=lambda: NOW + timedelta(days=2))
        await later.load()
        return later.is_revoked("old"), later.is_revoked("fresh"), await _stored_sids(database)

    assert run_with_database(tmp_path, scenario) == (False, True, ["fresh"])


def test_revoke_prunes_lapsed_rows_and_forgets_them(tmp_path: Path) -> None:
    async def scenario(database: ProgressDatabase) -> tuple[bool, bool, list[str]]:
        clock = [NOW]
        store = RevokedSessionStore(database, clock=lambda: clock[0])
        await store.revoke("old", NOW + timedelta(days=1))
        clock[0] = NOW + timedelta(days=2)
        await store.revoke("new", clock[0] + timedelta(days=30))
        return store.is_revoked("old"), store.is_revoked("new"), await _stored_sids(database)

    assert run_with_database(tmp_path, scenario) == (False, True, ["new"])


def test_revoking_twice_keeps_one_row_and_the_later_expiry(tmp_path: Path) -> None:
    async def scenario(database: ProgressDatabase) -> tuple[list[str], bool]:
        store = RevokedSessionStore(database, clock=lambda: NOW)
        await store.revoke("sid-a", NOW + timedelta(days=1))
        await store.revoke("sid-a", NOW + timedelta(days=5))
        reloaded = RevokedSessionStore(database, clock=lambda: NOW + timedelta(days=2))
        await reloaded.load()  # a day-1 expiry would have been pruned by now
        return await _stored_sids(database), reloaded.is_revoked("sid-a")

    assert run_with_database(tmp_path, scenario) == (["sid-a"], True)


def test_a_failed_write_leaves_the_session_unrevoked(tmp_path: Path) -> None:
    class BrokenDatabase:
        def sessions(self) -> None:
            raise RuntimeError("database is down")

    async def scenario(_database: ProgressDatabase) -> bool:
        store = RevokedSessionStore(BrokenDatabase(), clock=lambda: NOW)  # type: ignore[arg-type]
        with pytest.raises(RuntimeError, match="database is down"):
            await store.revoke("sid-a", NOW + timedelta(days=30))
        return store.is_revoked("sid-a")

    assert run_with_database(tmp_path, scenario) is False
```

Edit `tests/unit/db/test_migrate.py`. In `test_fresh_database_is_created_without_backup` change the revision and table set:

```python
    assert (result.from_revision, result.to_revision) == (None, "0002")
    assert result.upgraded is True
    assert result.backup_path is None
    assert {
        "card_state",
        "review_log",
        "app_setting",
        "revoked_session",
        "alembic_version",
    } <= _tables(db)
```

In `test_second_run_is_a_no_op` change the assertion to:

```python
    assert (again.from_revision, again.upgraded, again.backup_path) == ("0002", False, None)
```

Add these imports to the top import block: `import importlib.util`, `from alembic.operations import Operations`, and (below the existing `from bunsho.db import migrate` line, which already exists) nothing else. Then append this test at the end of the file:

```python
def _migration_0002() -> object:
    path = Path(migrate.__file__).parent / "migrations" / "versions" / "0002_revoked_session.py"
    spec = importlib.util.spec_from_file_location("migration_0002", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_0002_downgrade_removes_only_its_table_and_upgrade_restores_it(
    tmp_path: Path,
) -> None:
    db = tmp_path / "progress.db"
    run_migrations(db, backup_dir=tmp_path / "backups", now=lambda: NOW)
    module = _migration_0002()
    engine = create_engine(URL.create("sqlite", database=str(db)))
    try:
        with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
            module.downgrade()  # type: ignore[attr-defined]
        assert "revoked_session" not in _tables(db)
        assert {"card_state", "review_log", "app_setting"} <= _tables(db)
        with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
            module.upgrade()  # type: ignore[attr-defined]
        assert "revoked_session" in _tables(db)
    finally:
        engine.dispose()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd "D:/Documents/Code/Bunshō" && unset VIRTUAL_ENV && uv run pytest tests/unit/db/test_revoked_session_store.py tests/unit/services/test_session_revocations.py tests/unit/db/test_migrate.py -q`
Expected: collection errors (`ModuleNotFoundError: bunsho.db.revoked_session_store` / `bunsho.services.session_revocations`) and failures in `test_migrate.py` (revision `0001` != `0002`).

- [ ] **Step 3: Write the implementation**

Append to `src/bunsho/db/models.py`:

```python


class RevokedSession(Base):
    """A login session that was logged out; its tokens are refused until ``expires_at``."""

    __tablename__ = "revoked_session"

    sid: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[str] = mapped_column(String(32))
```

Create `src/bunsho/db/migrations/versions/0002_revoked_session.py`:

```python
"""Revoked login sessions: the server-side half of logout.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``revoked_session`` table."""
    op.create_table(
        "revoked_session",
        sa.Column("sid", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("sid"),
    )


def downgrade() -> None:
    """Drop the ``revoked_session`` table."""
    op.drop_table("revoked_session")
```

Append to `src/bunsho/services/protocols.py` (after the last Protocol; `datetime` is already imported there):

```python


class SessionRevocations(Protocol):
    """Remembers which login sessions were logged out."""

    def is_revoked(self, sid: str) -> bool:
        """Return whether ``sid`` was revoked. Synchronous and free of I/O."""
        ...

    async def revoke(self, sid: str, expires_at: datetime) -> None:
        """Revoke ``sid`` until ``expires_at`` (after that no token of it can be valid anyway)."""
        ...
```

Create `src/bunsho/services/session_revocations.py`:

```python
"""In-memory session revocations: the default for ``AuthService`` and a fake for tests."""

from __future__ import annotations

from datetime import datetime


class MemorySessionRevocations:
    """A ``SessionRevocations`` that forgets everything when the process ends."""

    def __init__(self) -> None:
        """Create an empty set of revocations."""
        self._revoked: dict[str, datetime] = {}

    def is_revoked(self, sid: str) -> bool:
        """Return whether ``sid`` was revoked."""
        return sid in self._revoked

    async def revoke(self, sid: str, expires_at: datetime) -> None:
        """Revoke ``sid`` until ``expires_at``."""
        self._revoked[sid] = expires_at

    def expiry(self, sid: str) -> datetime | None:
        """Return when the revocation of ``sid`` lapses, or ``None`` if it is not revoked."""
        return self._revoked.get(sid)
```

Create `src/bunsho/db/revoked_session_store.py`:

```python
"""Persistent set of revoked login sessions (the ``revoked_session`` table in ``progress.db``).

``is_revoked`` reads memory only: ``AuthService`` calls it on every request and WebSocket
connect, inside async handlers, so it must never block the event loop on SQLite. That is
safe because the service runs as a single process (see ``bunsho.db.instance_lock``).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from bunsho.db.engine import ProgressDatabase
from bunsho.db.models import RevokedSession
from bunsho.db.timestamps import format_timestamp, parse_timestamp


class RevokedSessionStore:
    """Revoked session ids: SQLite for durability, a dict for the per-request check."""

    def __init__(
        self, database: ProgressDatabase, *, clock: Callable[[], datetime] | None = None
    ) -> None:
        """Create the store; call ``load`` once at startup before serving requests.

        Args:
            database: The async engine wrapper for ``progress.db``.
            clock: Time source for pruning (defaults to UTC now).
        """
        self._database = database
        self._clock = clock or (lambda: datetime.now(UTC))
        self._expiry: dict[str, datetime] = {}

    async def load(self) -> None:
        """Delete lapsed rows, then load the remaining revocations into memory."""
        now = format_timestamp(self._clock())
        async with self._database.sessions() as session, session.begin():
            await session.execute(delete(RevokedSession).where(RevokedSession.expires_at <= now))
            rows = (
                await session.execute(select(RevokedSession.sid, RevokedSession.expires_at))
            ).all()
        self._expiry = {sid: parse_timestamp(expires_at) for sid, expires_at in rows}

    def is_revoked(self, sid: str) -> bool:
        """Return whether ``sid`` was revoked (memory only, no I/O)."""
        return sid in self._expiry

    async def revoke(self, sid: str, expires_at: datetime) -> None:
        """Persist the revocation of ``sid`` until ``expires_at``, then remember it in memory.

        Lapsed rows are pruned in the same transaction. If the write fails nothing changes
        in memory and the error propagates.

        Raises:
            ValueError: ``expires_at`` is a naive datetime.
        """
        now = self._clock()
        stored = format_timestamp(expires_at)
        statement = sqlite_insert(RevokedSession).values(sid=sid, expires_at=stored)
        statement = statement.on_conflict_do_update(
            index_elements=[RevokedSession.sid], set_={"expires_at": stored}
        )
        async with self._database.sessions() as session, session.begin():
            await session.execute(
                delete(RevokedSession).where(RevokedSession.expires_at <= format_timestamp(now))
            )
            await session.execute(statement)
        self._expiry = {known: until for known, until in self._expiry.items() if until > now}
        self._expiry[sid] = expires_at
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd "D:/Documents/Code/Bunshō" && unset VIRTUAL_ENV && uv run pytest tests/unit/db tests/unit/services/test_session_revocations.py -q`
Expected: all pass, including `test_migration_matches_the_models` (the model and migration agree).

- [ ] **Step 5: Lint and type-check**

Run: `cd "D:/Documents/Code/Bunshō" && unset VIRTUAL_ENV && uv run ruff format src tests && uv run ruff check . && uv run mypy src/`
Expected: clean. (If `ruff format` rewrites the test files, keep its output.)

- [ ] **Step 6: Commit**

```bash
cd "D:/Documents/Code/Bunshō"
git add src/bunsho/db/models.py src/bunsho/db/migrations/versions/0002_revoked_session.py src/bunsho/db/revoked_session_store.py src/bunsho/services/protocols.py src/bunsho/services/session_revocations.py tests/unit/db/test_migrate.py tests/unit/db/test_revoked_session_store.py tests/unit/services/test_session_revocations.py
git commit -m "feat(auth): revoked-session store and migration 0002" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: AuthService session ids, `authenticate_session` and `revoke`

**Files:**
- Modify: `src/bunsho/services/auth.py` (replace the file with the version below)
- Modify: `tests/unit/services/test_auth.py` (append tests, add imports)

**Interfaces:**
- Consumes: `SessionRevocations` (Task 1), `MemorySessionRevocations` (Task 1, `.expiry(sid)`).
- Produces:
  - `AuthService(settings, *, clock=None, revocations: SessionRevocations | None = None)` (an omitted `revocations` means a fresh `MemorySessionRevocations`).
  - `AuthService.issue_tokens(username: str, sid: str | None = None) -> TokenPair` (both tokens carry `sid`; `None` mints a new one).
  - `AuthService.authenticate(access_token) -> str` (unchanged).
  - `AuthService.authenticate_session(access_token: str) -> SessionClaims`.
  - `async AuthService.revoke(refresh_token: str) -> str` (returns the sid; raises `AuthError` for anything that does not verify, is expired, is not a refresh token, or is already revoked).
  - `SessionClaims(username: str, sid: str)` frozen dataclass.

- [ ] **Step 1: Write the failing tests**

Edit the imports at the top of `tests/unit/services/test_auth.py` to:

```python
import asyncio
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from bunsho.services.auth import AuthError, AuthService, SessionClaims
from bunsho.services.session_revocations import MemorySessionRevocations
from tests.base import JWT_SECRET, PASSWORD, make_auth_settings
```

Append at the end of the file:

```python
def _claims(token: str) -> dict:  # type: ignore[type-arg]
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])


@pytest.fixture
def fresh_auth() -> AuthService:
    return AuthService(make_auth_settings(), revocations=MemorySessionRevocations())


def test_both_tokens_of_one_login_share_a_session_id(fresh_auth: AuthService) -> None:
    first = fresh_auth.issue_tokens("james")
    second = fresh_auth.issue_tokens("james")
    sid = _claims(first.access_token)["sid"]
    assert sid == _claims(first.refresh_token)["sid"]
    assert len(sid) == 32
    assert sid != _claims(second.access_token)["sid"]


def test_refresh_keeps_the_session_id(fresh_auth: AuthService) -> None:
    first = fresh_auth.issue_tokens("james")
    second = fresh_auth.refresh(first.refresh_token)
    assert _claims(second.access_token)["sid"] == _claims(first.access_token)["sid"]
    assert _claims(second.refresh_token)["sid"] == _claims(first.refresh_token)["sid"]


def test_authenticate_session_returns_the_username_and_session_id(
    fresh_auth: AuthService,
) -> None:
    tokens = fresh_auth.issue_tokens("james")
    assert fresh_auth.authenticate_session(tokens.access_token) == SessionClaims(
        username="james", sid=_claims(tokens.access_token)["sid"]
    )


def test_revoking_a_session_rejects_all_of_its_tokens(fresh_auth: AuthService) -> None:
    first = fresh_auth.issue_tokens("james")
    second = fresh_auth.refresh(first.refresh_token)  # a later pair of the same login
    sid = asyncio.run(fresh_auth.revoke(first.refresh_token))
    assert sid == _claims(first.access_token)["sid"]
    for token in (first.access_token, second.access_token):
        with pytest.raises(AuthError):
            fresh_auth.authenticate(token)
        with pytest.raises(AuthError):
            fresh_auth.authenticate_session(token)
    for token in (first.refresh_token, second.refresh_token):
        with pytest.raises(AuthError):
            fresh_auth.refresh(token)


def test_revoking_one_session_leaves_another_login_alone(fresh_auth: AuthService) -> None:
    one = fresh_auth.issue_tokens("james")
    two = fresh_auth.issue_tokens("james")
    asyncio.run(fresh_auth.revoke(one.refresh_token))
    assert fresh_auth.authenticate(two.access_token) == "james"
    assert fresh_auth.refresh(two.refresh_token).access_token


def test_a_revoked_session_stays_revoked_for_a_full_refresh_lifetime() -> None:
    revocations = MemorySessionRevocations()
    auth = AuthService(make_auth_settings(), revocations=revocations)
    tokens = auth.issue_tokens("james")
    before = datetime.now(UTC)
    sid = asyncio.run(auth.revoke(tokens.refresh_token))
    after = datetime.now(UTC)
    expires_at = revocations.expiry(sid)
    assert expires_at is not None
    # Not the presented token's own exp: a newer refresh token of the same login can outlive it.
    assert before + timedelta(days=30) <= expires_at <= after + timedelta(days=30)


@pytest.mark.parametrize("kind", ["access", "refresh"])
def test_a_token_without_a_session_id_is_rejected(fresh_auth: AuthService, kind: str) -> None:
    """Tokens issued before sessions existed carry no ``sid``; the user logs in again once."""
    legacy = jwt.encode(
        {"sub": "james", "typ": kind, "exp": datetime.now(UTC) + timedelta(days=1)},
        JWT_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(AuthError):
        fresh_auth.authenticate(legacy)
    with pytest.raises(AuthError):
        fresh_auth.refresh(legacy)
    with pytest.raises(AuthError):
        asyncio.run(fresh_auth.revoke(legacy))


def test_revoke_rejects_tokens_that_do_not_verify(fresh_auth: AuthService) -> None:
    tokens = fresh_auth.issue_tokens("james")
    past = AuthService(make_auth_settings(), clock=lambda: datetime(2020, 1, 1, tzinfo=UTC))
    for bad in ("garbage", "", tokens.access_token, past.issue_tokens("james").refresh_token):
        with pytest.raises(AuthError):
            asyncio.run(fresh_auth.revoke(bad))
    # A failed revoke revoked nothing.
    assert fresh_auth.authenticate(tokens.access_token) == "james"


def test_revoking_an_already_revoked_session_raises(fresh_auth: AuthService) -> None:
    tokens = fresh_auth.issue_tokens("james")
    asyncio.run(fresh_auth.revoke(tokens.refresh_token))
    with pytest.raises(AuthError):
        asyncio.run(fresh_auth.revoke(tokens.refresh_token))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd "D:/Documents/Code/Bunshō" && unset VIRTUAL_ENV && uv run pytest tests/unit/services/test_auth.py -q`
Expected: ImportError for `SessionClaims` (collection error).

- [ ] **Step 3: Write the implementation**

Replace the whole of `src/bunsho/services/auth.py` with:

```python
"""Single-user authentication: argon2 password check and JWT access/refresh tokens.

Every login gets a session id (``sid``) that all of its tokens share. Revoking the sid
(``AuthService.revoke``) ends the login's refresh token and every access token issued for it.
"""

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
from bunsho.services.protocols import SessionRevocations
from bunsho.services.session_revocations import MemorySessionRevocations

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
    token_type: str = "bearer"  # noqa: S105 - OAuth2 scheme name, not a secret


@dataclass(frozen=True, slots=True)
class SessionClaims:
    """Who a valid token belongs to and which login session it is part of."""

    username: str
    sid: str


class AuthService:
    """Verifies the single configured user and issues JWTs tied to revocable sessions."""

    def __init__(
        self,
        settings: AuthSettings,
        *,
        clock: Callable[[], datetime] | None = None,
        revocations: SessionRevocations | None = None,
    ) -> None:
        """Create the service.

        Args:
            settings: Validated auth settings (argon2 hash, JWT secret, lifetimes).
            clock: Time source used for ``iat``/``exp`` (defaults to UTC now).
            revocations: Where revoked sessions are remembered (defaults to an in-memory set
                that forgets them when the process ends).
        """
        self._settings = settings
        self._clock = clock or (lambda: datetime.now(UTC))
        self._revocations: SessionRevocations = (
            revocations if revocations is not None else MemorySessionRevocations()
        )
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

    def _encode(self, username: str, sid: str, token_type: TokenType, lifetime: timedelta) -> str:
        issued = self._clock()
        claims: dict[str, Any] = {
            "sub": username,
            "sid": sid,
            "typ": token_type,
            "iat": issued,
            "exp": issued + lifetime,
            "jti": uuid.uuid4().hex,
        }
        return jwt.encode(claims, self._settings.jwt_secret, algorithm=_ALGORITHM)

    def issue_tokens(self, username: str, sid: str | None = None) -> TokenPair:
        """Issue an access and a refresh token for ``username``.

        Args:
            username: The user the tokens are for.
            sid: The session the tokens belong to. ``None`` starts a new login session;
                a refresh passes the session of the token it exchanged.
        """
        session_id = sid or uuid.uuid4().hex
        access_ttl = timedelta(minutes=self._settings.access_ttl_minutes)
        refresh_ttl = timedelta(days=self._settings.refresh_ttl_days)
        return TokenPair(
            access_token=self._encode(username, session_id, "access", access_ttl),
            refresh_token=self._encode(username, session_id, "refresh", refresh_ttl),
            expires_in=int(access_ttl.total_seconds()),
        )

    def _decode(self, token: str, expected: TokenType) -> SessionClaims:
        try:
            claims = jwt.decode(
                token,
                self._settings.jwt_secret,
                algorithms=[_ALGORITHM],
                options={"require": ["exp", "sub", "typ", "sid"]},
            )
        except jwt.InvalidTokenError as exc:
            raise AuthError("invalid or expired token") from exc
        if claims["typ"] != expected or claims["sub"] != self._settings.username:
            raise AuthError("wrong token type or subject")
        sid = str(claims["sid"])
        if self._revocations.is_revoked(sid):
            raise AuthError("session revoked")
        return SessionClaims(username=str(claims["sub"]), sid=sid)

    def authenticate(self, access_token: str) -> str:
        """Validate an access token.

        Returns:
            The authenticated username.

        Raises:
            AuthError: The token is invalid, expired, of the wrong type, for another user,
                without a session id, or its session was revoked.
        """
        return self._decode(access_token, "access").username

    def authenticate_session(self, access_token: str) -> SessionClaims:
        """Validate an access token and return its username and session id.

        Raises:
            AuthError: As for ``authenticate``.
        """
        return self._decode(access_token, "access")

    def refresh(self, refresh_token: str) -> TokenPair:
        """Exchange a valid refresh token for a new token pair of the same session.

        Raises:
            AuthError: The token is invalid, expired, of the wrong type, for another user,
                without a session id, or its session was revoked.
        """
        claims = self._decode(refresh_token, "refresh")
        return self.issue_tokens(claims.username, claims.sid)

    async def revoke(self, refresh_token: str) -> str:
        """End the login session behind ``refresh_token``.

        The session stays revoked for a full refresh lifetime from now: any token of it,
        including a newer refresh token held by another browser tab, expires within that time.

        Returns:
            The revoked session id.

        Raises:
            AuthError: The token does not verify, is expired, is not a refresh token, or its
                session was already revoked.
        """
        claims = self._decode(refresh_token, "refresh")
        lifetime = timedelta(days=self._settings.refresh_ttl_days)
        await self._revocations.revoke(claims.sid, self._clock() + lifetime)
        return claims.sid
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd "D:/Documents/Code/Bunshō" && unset VIRTUAL_ENV && uv run pytest tests/unit/services/test_auth.py tests/unit/api/test_auth_routes.py tests/unit/api/test_deps.py tests/unit/api/test_ws_routes.py -q`
Expected: all pass (the old tests still hold: the default in-memory store behaves like "no revocations").

- [ ] **Step 5: Lint and type-check**

Run: `cd "D:/Documents/Code/Bunshō" && unset VIRTUAL_ENV && uv run ruff format src tests && uv run ruff check . && uv run mypy src/`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
cd "D:/Documents/Code/Bunshō"
git add src/bunsho/services/auth.py tests/unit/services/test_auth.py
git commit -m "feat(auth): session ids in tokens, authenticate_session and revoke" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: `SessionSockets` registry and `logout_session` orchestration

**Files:**
- Create: `src/bunsho/orchestration/session_sockets.py`
- Create: `src/bunsho/orchestration/session_logout.py`
- Create: `tests/unit/orchestration/test_session_sockets.py`
- Create: `tests/unit/orchestration/test_session_logout.py`

**Interfaces:**
- Consumes: `AuthService.revoke`, `AuthService.authenticate`, `AuthError`, `MemorySessionRevocations` (Tasks 1-2).
- Produces:
  - `bunsho.orchestration.session_sockets.ClosableSocket` (Protocol): `async def close(self, code: int = 1000) -> None`.
  - `SessionSockets()`: `register(sid: str, socket: ClosableSocket) -> None`, `unregister(sid: str, socket: ClosableSocket) -> None`, `count(sid: str | None = None) -> int`, `async close_session(sid: str, code: int = 1008) -> int` (returns how many sockets it asked to close).
  - `bunsho.orchestration.session_logout.logout_session(auth: AuthService, sockets: SessionSockets, refresh_token: str, *, logger: logging.Logger, client: str) -> bool` (`True` when a session was revoked, `False` when the token did not verify).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/orchestration/test_session_sockets.py`:

```python
import asyncio

from starlette.websockets import WebSocketDisconnect

from bunsho.orchestration.session_sockets import SessionSockets


class FakeSocket:
    """Records the close codes it was given; can be made to fail like a vanished client."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.closed_with: list[int] = []
        self._error = error

    async def close(self, code: int = 1000) -> None:
        if self._error is not None:
            raise self._error
        self.closed_with.append(code)


def test_close_session_closes_only_that_sessions_sockets_with_1008() -> None:
    sockets = SessionSockets()
    mine, also_mine, other = FakeSocket(), FakeSocket(), FakeSocket()
    sockets.register("sid-a", mine)
    sockets.register("sid-a", also_mine)
    sockets.register("sid-b", other)
    assert asyncio.run(sockets.close_session("sid-a")) == 2
    assert mine.closed_with == [1008]
    assert also_mine.closed_with == [1008]
    assert other.closed_with == []


def test_close_session_for_an_unknown_session_does_nothing() -> None:
    assert asyncio.run(SessionSockets().close_session("nobody")) == 0


def test_a_socket_that_is_already_gone_does_not_stop_the_others() -> None:
    sockets = SessionSockets()
    gone = FakeSocket(error=RuntimeError("Cannot call send once a close message has been sent."))
    dropped = FakeSocket(error=WebSocketDisconnect(1006))
    alive = FakeSocket()
    for socket in (gone, dropped, alive):
        sockets.register("sid-a", socket)
    assert asyncio.run(sockets.close_session("sid-a")) == 3
    assert alive.closed_with == [1008]


def test_unregister_forgets_a_socket_and_an_empty_session() -> None:
    sockets = SessionSockets()
    socket = FakeSocket()
    sockets.register("sid-a", socket)
    assert (sockets.count(), sockets.count("sid-a")) == (1, 1)
    sockets.unregister("sid-a", socket)
    assert (sockets.count(), sockets.count("sid-a")) == (0, 0)
    assert asyncio.run(sockets.close_session("sid-a")) == 0


def test_registering_twice_counts_once_and_unregistering_a_stranger_is_harmless() -> None:
    sockets = SessionSockets()
    socket = FakeSocket()
    sockets.register("sid-a", socket)
    sockets.register("sid-a", socket)
    assert sockets.count("sid-a") == 1
    sockets.unregister("sid-b", socket)
    sockets.unregister("sid-a", FakeSocket())
    assert sockets.count("sid-a") == 1
```

Create `tests/unit/orchestration/test_session_logout.py`:

```python
import asyncio
import logging

import pytest

from bunsho.orchestration.session_logout import logout_session
from bunsho.orchestration.session_sockets import SessionSockets
from bunsho.services.auth import AuthError, AuthService
from bunsho.services.session_revocations import MemorySessionRevocations
from tests.base import make_auth_settings

LOGGER = logging.getLogger("bunsho.tests")


class RecordingSocket:
    def __init__(self, on_close=None) -> None:  # type: ignore[no-untyped-def]
        self.closed_with: list[int] = []
        self._on_close = on_close

    async def close(self, code: int = 1000) -> None:
        if self._on_close is not None:
            self._on_close()
        self.closed_with.append(code)


def _auth() -> AuthService:
    return AuthService(make_auth_settings(), revocations=MemorySessionRevocations())


def test_logout_revokes_the_session_and_closes_its_sockets() -> None:
    auth, sockets = _auth(), SessionSockets()
    tokens = auth.issue_tokens("james")
    sid = auth.authenticate_session(tokens.access_token).sid
    socket = RecordingSocket()
    sockets.register(sid, socket)
    assert asyncio.run(
        logout_session(auth, sockets, tokens.refresh_token, logger=LOGGER, client="10.0.0.1")
    )
    assert socket.closed_with == [1008]
    with pytest.raises(AuthError):
        auth.authenticate(tokens.access_token)


def test_the_session_is_revoked_before_its_sockets_are_closed() -> None:
    """A client that reconnects the instant its socket closes must already be refused."""
    auth, sockets = _auth(), SessionSockets()
    tokens = auth.issue_tokens("james")
    sid = auth.authenticate_session(tokens.access_token).sid

    def assert_already_revoked() -> None:
        with pytest.raises(AuthError):
            auth.authenticate(tokens.access_token)

    sockets.register(sid, RecordingSocket(on_close=assert_already_revoked))
    asyncio.run(
        logout_session(auth, sockets, tokens.refresh_token, logger=LOGGER, client="10.0.0.1")
    )


@pytest.mark.parametrize("token", ["garbage", "not.a.jwt"])
def test_a_token_that_does_not_verify_changes_nothing(token: str) -> None:
    auth, sockets = _auth(), SessionSockets()
    tokens = auth.issue_tokens("james")
    sid = auth.authenticate_session(tokens.access_token).sid
    socket = RecordingSocket()
    sockets.register(sid, socket)
    assert not asyncio.run(logout_session(auth, sockets, token, logger=LOGGER, client="x"))
    assert socket.closed_with == []
    assert auth.authenticate(tokens.access_token) == "james"


def test_logging_out_twice_is_harmless() -> None:
    auth, sockets = _auth(), SessionSockets()
    tokens = auth.issue_tokens("james")
    first = asyncio.run(logout_session(auth, sockets, tokens.refresh_token, logger=LOGGER, client="x"))
    second = asyncio.run(logout_session(auth, sockets, tokens.refresh_token, logger=LOGGER, client="x"))
    assert (first, second) == (True, False)


def test_the_log_line_never_contains_a_token(caplog: pytest.LogCaptureFixture) -> None:
    auth, sockets = _auth(), SessionSockets()
    tokens = auth.issue_tokens("james")
    logger = logging.getLogger("bunsho.tests.logout")
    with caplog.at_level(logging.DEBUG, logger=logger.name):
        asyncio.run(
            logout_session(auth, sockets, tokens.refresh_token, logger=logger, client="10.0.0.1")
        )
        asyncio.run(logout_session(auth, sockets, "secret-garbage", logger=logger, client="10.0.0.1"))
    assert "logout sid=" in caplog.text
    assert "logout_ignored" in caplog.text
    assert tokens.refresh_token not in caplog.text
    assert "secret-garbage" not in caplog.text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd "D:/Documents/Code/Bunshō" && unset VIRTUAL_ENV && uv run pytest tests/unit/orchestration/test_session_sockets.py tests/unit/orchestration/test_session_logout.py -q`
Expected: collection errors (`ModuleNotFoundError: bunsho.orchestration.session_sockets`).

- [ ] **Step 3: Write the implementation**

Create `src/bunsho/orchestration/session_sockets.py`:

```python
"""Which authenticated WebSockets belong to which login session."""

from __future__ import annotations

from contextlib import suppress
from typing import Protocol

from starlette.websockets import WebSocketDisconnect

POLICY_VIOLATION = 1008
"""The close code the task stream already uses for authentication failures."""


class ClosableSocket(Protocol):
    """The slice of a WebSocket this registry uses."""

    async def close(self, code: int = 1000) -> None:
        """Close the connection with ``code``."""
        ...


class SessionSockets:
    """A registry of open, authenticated sockets keyed by session id.

    Used only from the event loop, so it needs no locking. Sockets are registered after
    they authenticate and unregistered when their handler ends.
    """

    def __init__(self) -> None:
        """Create an empty registry."""
        self._by_sid: dict[str, set[ClosableSocket]] = {}

    def register(self, sid: str, socket: ClosableSocket) -> None:
        """Remember ``socket`` as belonging to session ``sid``."""
        self._by_sid.setdefault(sid, set()).add(socket)

    def unregister(self, sid: str, socket: ClosableSocket) -> None:
        """Forget ``socket``; unknown sockets and sessions are ignored."""
        sockets = self._by_sid.get(sid)
        if sockets is None:
            return
        sockets.discard(socket)
        if not sockets:
            del self._by_sid[sid]

    def count(self, sid: str | None = None) -> int:
        """Return how many sockets are registered, for one session or for all."""
        if sid is not None:
            return len(self._by_sid.get(sid, ()))
        return sum(len(sockets) for sockets in self._by_sid.values())

    async def close_session(self, sid: str, code: int = POLICY_VIOLATION) -> int:
        """Close every socket of session ``sid``.

        A socket that is already closed or whose client vanished is skipped silently, so one
        dead socket never keeps the others open.

        Returns:
            How many sockets it asked to close.
        """
        sockets = list(self._by_sid.get(sid, ()))
        for socket in sockets:
            with suppress(RuntimeError, WebSocketDisconnect):
                await socket.close(code=code)
        return len(sockets)
```

Create `src/bunsho/orchestration/session_logout.py`:

```python
"""Logout: end a login session on the server, then close its open sockets."""

from __future__ import annotations

import logging

from bunsho.orchestration.session_sockets import SessionSockets
from bunsho.services.auth import AuthError, AuthService


async def logout_session(
    auth: AuthService,
    sockets: SessionSockets,
    refresh_token: str,
    *,
    logger: logging.Logger,
    client: str,
) -> bool:
    """Revoke the session behind ``refresh_token`` and close its sockets.

    The session is revoked first, so a client that reconnects the moment its socket closes
    is already refused. A token that does not verify (garbage, expired, an access token,
    or an already revoked session) changes nothing; the caller answers the same either way,
    so the endpoint never reveals whether a token was valid.

    Args:
        auth: The service that owns token validity.
        sockets: The registry of open sockets.
        refresh_token: The refresh token the client is logging out with.
        logger: Receives ``logout`` (info) or ``logout_ignored`` (debug); never the token.
        client: The caller's address, for the log line.

    Returns:
        ``True`` when a session was revoked, ``False`` when the token was ignored.
    """
    try:
        sid = await auth.revoke(refresh_token)
    except AuthError:
        logger.debug("logout_ignored client=%s", client)
        return False
    closed = await sockets.close_session(sid)
    logger.info("logout sid=%s client=%s sockets_closed=%d", sid, client, closed)
    return True
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd "D:/Documents/Code/Bunshō" && unset VIRTUAL_ENV && uv run pytest tests/unit/orchestration/test_session_sockets.py tests/unit/orchestration/test_session_logout.py -q`
Expected: all pass.

- [ ] **Step 5: Lint and type-check**

Run: `cd "D:/Documents/Code/Bunshō" && unset VIRTUAL_ENV && uv run ruff format src tests && uv run ruff check . && uv run mypy src/`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
cd "D:/Documents/Code/Bunshō"
git add src/bunsho/orchestration/session_sockets.py src/bunsho/orchestration/session_logout.py tests/unit/orchestration/test_session_sockets.py tests/unit/orchestration/test_session_logout.py
git commit -m "feat(auth): session socket registry and logout orchestration" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Wire it up: `POST /auth/logout`, WebSocket registration, OpenAPI

**Files:**
- Modify: `src/bunsho/api/services.py` (fields, load at startup, wiring)
- Modify: `src/bunsho/api/schemas.py` (add `LogoutRequest` after `RefreshRequest`)
- Modify: `src/bunsho/api/routers/auth.py` (add the route)
- Modify: `src/bunsho/api/routers/ws.py` (authenticate to a session, register)
- Modify: `tests/unit/api/test_auth_routes.py` (append tests)
- Modify: `tests/unit/api/test_ws_routes.py` (append tests)
- Modify: `tests/unit/api/test_openapi_snapshot.py` (add `"logout"` to the operation set)
- Regenerate: `frontend/openapi.json`, `frontend/src/api/schema.d.ts`

**Interfaces:**
- Consumes: `RevokedSessionStore` (Task 1), `AuthService(..., revocations=)`, `authenticate_session`, `SessionClaims` (Task 2), `SessionSockets`, `logout_session` (Task 3).
- Produces: `Services.sockets: SessionSockets`; HTTP `POST /api/v1/auth/logout` (`operationId: logout`, request `LogoutRequest{refresh_token: str}`, 204 no body); OpenAPI + `schema.d.ts` containing `logout` and `LogoutRequest` (Task 6 uses them).

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/api/test_auth_routes.py`. First extend the imports at the top of the file:

```python
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from bunsho.api.app import create_app
from bunsho.config.service import ServiceConfig
from bunsho.services.auth import AuthService
from tests.base import PASSWORD, make_auth_settings
```

(The file already imports `ThreadPoolExecutor`, `pytest`, `TestClient` and `PASSWORD`; add only what is missing.) Then append:

```python
LOGOUT = "/api/v1/auth/logout"
SUMMARY = "/api/v1/content/summary"


def _logout(client: TestClient, refresh_token: str):  # type: ignore[no-untyped-def]
    return client.post(LOGOUT, json={"refresh_token": refresh_token})


def _bearer(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def test_logout_revokes_the_whole_session(client: TestClient) -> None:
    tokens = _login(client).json()
    assert client.get(SUMMARY, headers=_bearer(tokens["access_token"])).status_code == 200
    response = _logout(client, tokens["refresh_token"])
    assert response.status_code == 204
    assert response.content == b""
    assert client.get(SUMMARY, headers=_bearer(tokens["access_token"])).status_code == 401
    assert client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]}).status_code == 401


def test_logout_also_ends_tokens_from_earlier_refreshes(client: TestClient) -> None:
    first = _login(client).json()
    second = client.post(REFRESH, json={"refresh_token": first["refresh_token"]}).json()
    assert _logout(client, first["refresh_token"]).status_code == 204
    assert client.get(SUMMARY, headers=_bearer(second["access_token"])).status_code == 401
    assert client.post(REFRESH, json={"refresh_token": second["refresh_token"]}).status_code == 401


def test_logout_leaves_another_login_alone(client: TestClient) -> None:
    one, two = _login(client).json(), _login(client).json()
    assert _logout(client, one["refresh_token"]).status_code == 204
    assert client.get(SUMMARY, headers=_bearer(two["access_token"])).status_code == 200
    assert client.post(REFRESH, json={"refresh_token": two["refresh_token"]}).status_code == 200


def test_logout_needs_no_bearer_token(client: TestClient) -> None:
    tokens = _login(client).json()
    assert client.post(LOGOUT, json={"refresh_token": tokens["refresh_token"]}).status_code == 204


def test_logging_out_twice_is_still_204(client: TestClient) -> None:
    tokens = _login(client).json()
    assert _logout(client, tokens["refresh_token"]).status_code == 204
    assert _logout(client, tokens["refresh_token"]).status_code == 204


@pytest.mark.parametrize("token", ["garbage", "a.b.c", "x" * 5000])
def test_a_token_that_does_not_verify_gets_the_same_204(client: TestClient, token: str) -> None:
    assert _logout(client, token).status_code == 204


def test_an_expired_refresh_token_gets_204_and_revokes_nothing(client: TestClient) -> None:
    past = AuthService(make_auth_settings(), clock=lambda: datetime(2020, 1, 1, tzinfo=UTC))
    assert _logout(client, past.issue_tokens("james").refresh_token).status_code == 204


def test_an_access_token_cannot_log_a_session_out(client: TestClient) -> None:
    tokens = _login(client).json()
    assert _logout(client, tokens["access_token"]).status_code == 204
    assert client.get(SUMMARY, headers=_bearer(tokens["access_token"])).status_code == 200


def test_logout_validates_its_body(client: TestClient) -> None:
    assert client.post(LOGOUT, json={}).status_code == 422
    assert client.post(LOGOUT, json={"refresh_token": ""}).status_code == 422


def test_a_flood_of_bad_logouts_cannot_block_login(client: TestClient) -> None:
    for _ in range(20):
        assert _logout(client, "garbage").status_code == 204
    assert _login(client).status_code == 200


def test_revocation_survives_a_restart(service_config: ServiceConfig) -> None:
    with TestClient(create_app(service_config)) as first:
        tokens = _login(first).json()
        assert _logout(first, tokens["refresh_token"]).status_code == 204
    with TestClient(create_app(service_config)) as second:
        assert second.post(REFRESH, json={"refresh_token": tokens["refresh_token"]}).status_code == 401
        assert second.get(SUMMARY, headers=_bearer(tokens["access_token"])).status_code == 401
        assert _login(second).status_code == 200  # a new login is unaffected
```

Append to `tests/unit/api/test_ws_routes.py`:

```python
LOGOUT = "/api/v1/auth/logout"


def _registered_sockets(client: TestClient) -> int:
    return client.app.state.services.sockets.count()  # type: ignore[no-any-return,attr-defined]


def _logout(client: TestClient, tokens: dict) -> int:  # type: ignore[type-arg]
    return client.post(LOGOUT, json={"refresh_token": tokens["refresh_token"]}).status_code


def _authenticate(ws: Any, tokens: dict) -> None:  # type: ignore[type-arg]
    ws.send_json({"type": "auth", "token": tokens["access_token"]})
    assert ws.receive_json() == {"type": "ready"}


def test_logout_closes_that_sessions_open_socket(stub_client: TestClient) -> None:
    tokens = _login(stub_client)
    with stub_client.websocket_connect(WS) as ws:
        _authenticate(ws, tokens)
        assert _registered_sockets(stub_client) == 1
        assert _logout(stub_client, tokens) == 204
        with pytest.raises(WebSocketDisconnect) as info:
            ws.receive_json()
        assert info.value.code == 1008
        close_and_wait_for_unsubscribe(stub_client, ws)
    assert _registered_sockets(stub_client) == 0


def test_logout_leaves_another_sessions_socket_streaming(stub_client: TestClient) -> None:
    one, two = _login(stub_client), _login(stub_client)
    headers_two = {"Authorization": f"Bearer {two['access_token']}"}
    with (
        stub_client.websocket_connect(WS) as ws_one,
        stub_client.websocket_connect(WS) as ws_two,
    ):
        _authenticate(ws_one, one)
        _authenticate(ws_two, two)
        assert _registered_sockets(stub_client) == 2
        assert _logout(stub_client, one) == 204
        with pytest.raises(WebSocketDisconnect) as info:
            ws_one.receive_json()
        assert info.value.code == 1008
        started = stub_client.post(BUILD, json={}, headers=headers_two)
        assert started.status_code == 202
        event = ws_two.receive_json()  # session two still streams
        assert event["type"] == "event"
        ws_one.close()
        close_and_wait_for_unsubscribe(stub_client, ws_two)
    assert _registered_sockets(stub_client) == 0


def test_a_revoked_sessions_token_cannot_open_a_socket(stub_client: TestClient) -> None:
    tokens = _login(stub_client)
    assert _logout(stub_client, tokens) == 204
    message = {"type": "auth", "token": tokens["access_token"]}
    assert _connect_and_expect_close(stub_client, message) == 1008
    assert _registered_sockets(stub_client) == 0
    assert _subscriber_count(stub_client) == 0


def test_a_socket_is_unregistered_when_its_client_disconnects(stub_client: TestClient) -> None:
    tokens = _login(stub_client)
    with stub_client.websocket_connect(WS) as ws:
        _authenticate(ws, tokens)
        assert _registered_sockets(stub_client) == 1
        close_and_wait_for_unsubscribe(stub_client, ws)
    assert _registered_sockets(stub_client) == 0
```

Edit `tests/unit/api/test_openapi_snapshot.py`: add `"logout",` after `"refreshToken",` in the expected operation-id set.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd "D:/Documents/Code/Bunshō" && unset VIRTUAL_ENV && uv run pytest tests/unit/api/test_auth_routes.py tests/unit/api/test_ws_routes.py tests/unit/api/test_openapi_snapshot.py -q -x`
Expected: failures: `POST /auth/logout` returns 404/405 and `services.sockets` does not exist.

- [ ] **Step 3: Write the implementation**

`src/bunsho/api/services.py`:

1. Add imports (keep the import block sorted the way ruff wants):

```python
from bunsho.db.revoked_session_store import RevokedSessionStore
from bunsho.orchestration.session_sockets import SessionSockets
```

2. Add a field to the `Services` dataclass, after `auth: AuthService`:

```python
    sockets: SessionSockets
```

3. In `build_services`, directly after `await progress_db.ping()` add:

```python
            revocations = RevokedSessionStore(progress_db)
            await revocations.load()
```

4. In the `Services(...)` call replace `auth=AuthService(config.auth),` with:

```python
                auth=AuthService(config.auth, revocations=revocations),
                sockets=SessionSockets(),
```

`src/bunsho/api/schemas.py`: after `class RefreshRequest`, add:

```python
class LogoutRequest(BaseModel):
    """Body of ``POST /auth/logout``."""

    refresh_token: str = Field(min_length=1)
```

`src/bunsho/api/routers/auth.py`: change the imports and add the route.

```python
from fastapi import APIRouter, HTTPException, Request, Response, status

from bunsho.api.deps import ServicesDep
from bunsho.api.responses import TOO_MANY_REQUESTS, UNAUTHORIZED
from bunsho.api.schemas import LoginRequest, LogoutRequest, RefreshRequest, TokenResponse
from bunsho.orchestration.session_logout import logout_session
from bunsho.services.auth import AuthError, TokenPair
```

Append at the end of the file:

```python


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    operation_id="logout",
)
async def logout(body: LogoutRequest, request: Request, services: ServicesDep) -> Response:
    """End the login session behind a refresh token and close its open streams.

    Always answers 204, whether or not the token was valid, so the endpoint tells a caller
    nothing about a token. It needs no bearer token (the access token may have expired),
    and it never touches the login throttle.
    """
    client = request.client.host if request.client else "unknown"
    await logout_session(
        services.auth,
        services.sockets,
        body.refresh_token,
        logger=services.ctx.logger,
        client=client,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

`src/bunsho/api/routers/ws.py`:

1. Change the import `from bunsho.services.auth import AuthError` to `from bunsho.services.auth import AuthError, SessionClaims`.
2. Replace the `_AuthOutcome` alias with:

```python
_FailedAuth = Literal[
    "disconnected", "timeout", "not_text", "oversized", "malformed", "invalid_token"
]
```

3. Replace `_check_first_message` and `_authenticate` with:

```python
def _check_first_message(
    message: Mapping[str, Any], services: ServicesDep
) -> SessionClaims | _FailedAuth:
    """Classify the first frame the client sent: the session it authenticates, or why not."""
    if message["type"] == "websocket.disconnect":
        return "disconnected"
    text = message.get("text")
    if text is None:
        return "not_text"
    if len(text) > MAX_AUTH_MESSAGE_CHARS:
        return "oversized"
    try:
        auth = WsAuthMessage.model_validate(json.loads(text))
    except (ValueError, RecursionError, ValidationError):
        return "malformed"
    try:
        return services.auth.authenticate_session(auth.token)
    except AuthError:
        return "invalid_token"


async def _authenticate(websocket: WebSocket, services: ServicesDep) -> SessionClaims | None:
    """Read the first message and validate the access token.

    Closes the socket with 1008 on any failure and never raises for client misbehaviour.

    Returns:
        The authenticated session, or ``None`` when the client did not authenticate.
    """
    try:
        message = await asyncio.wait_for(websocket.receive(), AUTH_TIMEOUT_SECONDS)
    except TimeoutError:
        outcome: SessionClaims | _FailedAuth = "timeout"
    else:
        outcome = _check_first_message(message, services)
    client = _client_host(websocket)
    if isinstance(outcome, SessionClaims):
        services.ctx.logger.info("ws_auth_ok client=%s", client)
        return outcome
    services.ctx.logger.warning("ws_auth_failed client=%s outcome=%s", client, outcome)
    if outcome != "disconnected":
        with suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close(code=POLICY_VIOLATION)
    return None
```

4. Replace the body of `task_stream` (after the docstring) with:

```python
    await websocket.accept()
    session = await _authenticate(websocket, services)
    if session is None:
        return
    # Nothing is awaited between the token check and this registration, so a logout cannot
    # slip in between and miss this socket.
    services.sockets.register(session.sid, websocket)
    try:
        await _stream(websocket, services)
    except Exception as exc:
        # A bug, not a client problem: log the type only (the text may hold internals).
        services.ctx.logger.error(
            "ws_stream_failed client=%s error_type=%s", _client_host(websocket), type(exc).__name__
        )
        with suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close(code=INTERNAL_ERROR)
    finally:
        services.sockets.unregister(session.sid, websocket)
```

Also extend the `task_stream` docstring's last sentence: after "Any other first message closes the socket with code 1008." add " A logout of the session that authenticated the socket closes it with 1008 too."

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd "D:/Documents/Code/Bunshō" && unset VIRTUAL_ENV && uv run pytest tests/unit/api -q`
Expected: everything passes except `tests/unit/api/test_openapi_snapshot.py::test_the_committed_snapshot_matches_the_app` (the snapshot is stale until Step 5).

- [ ] **Step 5: Regenerate the OpenAPI snapshot and the TypeScript types**

Run:

```bash
cd "D:/Documents/Code/Bunshō" && unset VIRTUAL_ENV && uv run python scripts/export_openapi.py
cd frontend && npm run gen:api
cd .. && git diff --stat -- frontend/openapi.json frontend/src/api/schema.d.ts
```

Expected: both files changed; `schema.d.ts` gains `logout` and `LogoutRequest`. (If `node_modules` is missing, run `npm ci` in `frontend/` first.)

Then run: `cd "D:/Documents/Code/Bunshō" && unset VIRTUAL_ENV && uv run pytest tests/unit/api/test_openapi_snapshot.py -q`
Expected: pass.

- [ ] **Step 6: Flake check (threads, sockets and TestClient teardown)**

Run in the background and wait for it (about 5-8 minutes):

```bash
cd "D:/Documents/Code/Bunshō" && unset VIRTUAL_ENV && for i in $(seq 1 40); do uv run pytest tests/unit/api/test_ws_routes.py tests/unit/api/test_auth_routes.py -q -p no:cacheprovider || { echo "FAILED on run $i"; break; }; done; echo done
```

Expected: 40 clean runs and `done`. Any failure: stop and fix the ordering (do not retry until green).

- [ ] **Step 7: Lint, type-check, full Python suite**

Run: `cd "D:/Documents/Code/Bunshō" && unset VIRTUAL_ENV && uv run ruff format src tests && uv run ruff check . && uv run mypy src/ && uv run bandit -c pyproject.toml -r src/ -l && uv run pytest --cov -q`
Expected: clean, all tests pass, coverage >= 90.

- [ ] **Step 8: Commit**

```bash
cd "D:/Documents/Code/Bunshō"
git add src/bunsho/api/services.py src/bunsho/api/schemas.py src/bunsho/api/routers/auth.py src/bunsho/api/routers/ws.py tests/unit/api/test_auth_routes.py tests/unit/api/test_ws_routes.py tests/unit/api/test_openapi_snapshot.py frontend/openapi.json frontend/src/api/schema.d.ts
git commit -m "feat(auth): POST /auth/logout revokes the session and closes its sockets" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Frontend session epoch

**Files:**
- Modify: `frontend/src/auth/session.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/auth/session.test.ts` (append)
- Modify: `frontend/src/api/client.test.ts` (append)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces (Task 6 relies on these):
  - `session.getEpoch(): number`
  - `session.setTokens(pair: TokenPair, now?: number, expectedEpoch?: number): boolean` (`false` = pair discarded because the epoch changed)
  - `session.expire(expectedEpoch?: number): void` (no-op when `expectedEpoch` is stale)
  - `session.clear()` now also increments the epoch.
  - `refreshSession()` keeps its signature; a discarded result rejects with `ApiError(401, 'Session changed')` without notifying `onExpired` listeners.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/auth/session.test.ts` (inside the file, after the existing `describe`):

```ts
describe('session epoch', () => {
  beforeEach(() => {
    session.clear();
  });

  it('clear and expire each start a new epoch, setTokens does not', () => {
    const start = session.getEpoch();
    session.setTokens(PAIR);
    expect(session.getEpoch()).toBe(start);
    session.clear();
    expect(session.getEpoch()).toBe(start + 1);
    session.expire();
    expect(session.getEpoch()).toBe(start + 2);
  });

  it('stores a pair that belongs to the current epoch and says so', () => {
    expect(session.setTokens(PAIR, 1_000, session.getEpoch())).toBe(true);
    expect(session.getRefreshToken()).toBe('refresh-1');
    expect(session.getAccessToken(1_000)).toBe('access-1');
  });

  it('discards a pair from an earlier epoch and says so', () => {
    const stale = session.getEpoch();
    session.clear();
    expect(session.setTokens(PAIR, 1_000, stale)).toBe(false);
    expect(session.getRefreshToken()).toBeNull();
    expect(session.getAccessToken(1_000)).toBeNull();
  });

  it('a login without an epoch always stores its pair', () => {
    session.clear();
    expect(session.setTokens(PAIR, 1_000)).toBe(true);
    expect(session.getRefreshToken()).toBe('refresh-1');
  });

  it('expire from an earlier epoch leaves a newer session and its listeners alone', () => {
    const listener = vi.fn();
    const stop = session.onExpired(listener);
    const stale = session.getEpoch();
    session.clear();
    session.setTokens(PAIR);
    session.expire(stale);
    expect(session.getRefreshToken()).toBe('refresh-1');
    expect(listener).not.toHaveBeenCalled();
    stop();
  });

  it('expire from the current epoch ends the session and tells the listeners', () => {
    const listener = vi.fn();
    const stop = session.onExpired(listener);
    session.setTokens(PAIR);
    session.expire(session.getEpoch());
    expect(session.getRefreshToken()).toBeNull();
    expect(listener).toHaveBeenCalledTimes(1);
    stop();
  });
});
```

Append to `frontend/src/api/client.test.ts`:

```ts
function deferred() {
  let release: () => void = () => {};
  const promise = new Promise<void>((resolve) => {
    release = resolve;
  });
  return { promise, release };
}

describe('a refresh that is overtaken by a logout', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens(pair(1));
  });

  it('cannot bring the logged-out session back', async () => {
    const gate = deferred();
    server.use(
      http.post(REFRESH, async () => {
        await gate.promise;
        return HttpResponse.json({ ...pair(2), token_type: 'bearer' });
      }),
    );
    const pending = refreshSession();
    const settled = expect(pending).rejects.toMatchObject({ status: 401 });
    session.clear(); // the user logs out while the refresh is in flight
    gate.release();
    await settled;
    expect(session.getRefreshToken()).toBeNull();
    expect(session.getAccessToken()).toBeNull();
  });

  it('a late 401 for the old token does not end a newer login', async () => {
    const expired = vi.fn();
    const stop = session.onExpired(expired);
    const gate = deferred();
    server.use(
      http.post(REFRESH, async () => {
        await gate.promise;
        return HttpResponse.json({ detail: 'Invalid or expired refresh token' }, { status: 401 });
      }),
    );
    const pending = refreshSession();
    const settled = expect(pending).rejects.toMatchObject({ status: 401 });
    session.clear();
    session.setTokens(pair(5)); // the user logs in again
    gate.release();
    await settled;
    expect(expired).not.toHaveBeenCalled();
    expect(session.getRefreshToken()).toBe('refresh-5');
    stop();
  });

  it('a new session refreshes on its own instead of joining the old refresh', async () => {
    const gate = deferred();
    const calls: string[] = [];
    server.use(
      http.post(REFRESH, async ({ request: incoming }) => {
        const body = (await incoming.json()) as { refresh_token: string };
        calls.push(body.refresh_token);
        if (body.refresh_token === 'refresh-1') await gate.promise;
        return HttpResponse.json({ ...pair(7), token_type: 'bearer' });
      }),
    );
    const stale = refreshSession();
    const staleSettled = expect(stale).rejects.toMatchObject({ status: 401 });
    await vi.waitFor(() => {
      expect(calls).toContain('refresh-1');
    });
    session.clear();
    session.setTokens(pair(6));
    await refreshSession();
    expect([...calls].sort()).toEqual(['refresh-1', 'refresh-6']);
    expect(session.getRefreshToken()).toBe('refresh-7');
    gate.release();
    await staleSettled;
    expect(session.getRefreshToken()).toBe('refresh-7'); // the old answer changed nothing
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd "D:/Documents/Code/Bunshō/frontend" && npx vitest run src/auth/session.test.ts src/api/client.test.ts`
Expected: failures (`session.getEpoch is not a function`; the late-success test resolves instead of rejecting).

- [ ] **Step 3: Write the implementation**

`frontend/src/auth/session.ts`: add the epoch next to the other module state and update the object. Change the state block and the `session` object methods to:

```ts
let accessToken: string | null = null;
let accessExpiresAt = 0;
/**
 * Counts how many times the session was ended (logout, expiry). A refresh remembers the epoch it
 * started in and its answer is dropped when the epoch has moved on, so a slow refresh can never
 * bring back a session the user has since left, or end the one they logged in to afterwards.
 */
let epoch = 0;
const expiredListeners = new Set<() => void>();
```

and inside `export const session = { ... }` replace `setTokens`, `clear` and `expire` and add `getEpoch`:

```ts
  /** The current epoch (see above); capture it before an asynchronous call that stores tokens. */
  getEpoch(): number {
    return epoch;
  },

  /**
   * Store a fresh token pair (after login or refresh). With `expectedEpoch`, a pair from an earlier
   * epoch is dropped. Returns whether the pair was stored.
   */
  setTokens(pair: TokenPair, now: number = Date.now(), expectedEpoch?: number): boolean {
    if (expectedEpoch !== undefined && expectedEpoch !== epoch) return false;
    accessToken = pair.access_token;
    accessExpiresAt = now + pair.expires_in * 1000;
    writeStoredRefreshToken(pair.refresh_token);
    return true;
  },

  /** Forget everything (logout) and start a new epoch. Does not notify. */
  clear(): void {
    epoch += 1;
    accessToken = null;
    accessExpiresAt = 0;
    writeStoredRefreshToken(null);
  },

  /**
   * The server rejected the refresh token: forget everything and tell the listeners. With
   * `expectedEpoch`, a rejection that belongs to an earlier epoch is ignored.
   */
  expire(expectedEpoch?: number): void {
    if (expectedEpoch !== undefined && expectedEpoch !== epoch) return;
    this.clear();
    for (const listener of [...expiredListeners]) {
      listener();
    }
  },
```

(Leave `getRefreshToken`, `getAccessToken` and `onExpired` as they are.)

`frontend/src/api/client.ts`: replace the refresh block (from `let refreshInFlight` through the end of `refreshSession`) with:

```ts
let refreshInFlight: { epoch: number; promise: Promise<void> } | null = null;

async function refreshOnce(epoch: number): Promise<void> {
  const refreshToken = session.getRefreshToken();
  if (refreshToken === null) {
    session.expire(epoch);
    throw new ApiError(401, 'Not signed in');
  }
  let pair: TokenResponse;
  try {
    pair = await rawRequest<TokenResponse>('/auth/refresh', {
      method: 'POST',
      body: { refresh_token: refreshToken },
    });
  } catch (error) {
    // A 401 only ends the session it belongs to: after a logout and a new login it is stale.
    if (error instanceof ApiError && error.status === 401) session.expire(epoch);
    throw error;
  }
  // The user logged out (or the session ended) while this was in flight: drop the answer.
  if (!session.setTokens(pair, Date.now(), epoch)) throw new ApiError(401, 'Session changed');
}

/**
 * Exchange the refresh token for a new pair. Concurrent callers of the same session share one
 * request. A 401 from the server ends the session (listeners of `session.onExpired` are told);
 * other errors propagate and leave the session untouched, so a server restart never logs anybody
 * out. If the session ended while the request was in flight the answer is discarded and this
 * rejects with a 401 without notifying anybody.
 */
export function refreshSession(): Promise<void> {
  const epoch = session.getEpoch();
  if (refreshInFlight?.epoch === epoch) return refreshInFlight.promise;
  const promise = refreshOnce(epoch).finally(() => {
    if (refreshInFlight?.promise === promise) refreshInFlight = null;
  });
  refreshInFlight = { epoch, promise };
  return promise;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd "D:/Documents/Code/Bunshō/frontend" && npx vitest run src/auth src/api src/realtime`
Expected: all pass, including the pre-existing session/client/AuthProvider/RealtimeProvider tests.

- [ ] **Step 5: Format, lint, type-check**

Run: `cd "D:/Documents/Code/Bunshō/frontend" && npm run format && npm run lint && npm run build`
Expected: clean. (`npm run format` may touch only the files above; check with `git status`.)

- [ ] **Step 6: Commit**

```bash
cd "D:/Documents/Code/Bunshō"
git add frontend/src/auth/session.ts frontend/src/api/client.ts frontend/src/auth/session.test.ts frontend/src/api/client.test.ts
git commit -m "fix(auth): a refresh in flight can no longer undo a logout" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Frontend logout call, corrected note, stream lifecycle tests

**Files:**
- Modify: `frontend/src/api/client.ts` (add `revokeSession`)
- Modify: `frontend/src/auth/AuthProvider.tsx`
- Modify: `frontend/src/components/AppLayout.tsx` (the note text)
- Modify: `frontend/src/components/AppLayout.test.tsx` (the note test)
- Modify: `frontend/src/auth/AuthProvider.test.tsx` (handler + new tests)
- Modify: `frontend/src/App.test.tsx` (`rememberLogin` gets a logout handler)
- Create: `frontend/src/realtime/streamLifecycle.test.tsx`

**Interfaces:**
- Consumes: `POST /api/v1/auth/logout` (Task 4), `session.getEpoch`/guards (Task 5).
- Produces: `revokeSession(refreshToken: string): Promise<void>` in `frontend/src/api/client.ts` (never rejects). `AuthProvider.logout()` keeps its signature `() => void`.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/auth/AuthProvider.test.tsx`, inside `describe('AuthProvider sessions', ...)` change the `beforeEach` to also register a default logout handler:

```tsx
  beforeEach(() => {
    session.clear();
    window.localStorage.setItem(REFRESH_TOKEN_KEY, 'r1');
    server.use(
      http.post('/api/v1/auth/refresh', () => HttpResponse.json(TOKENS)),
      http.post('/api/v1/auth/logout', () => new HttpResponse(null, { status: 204 })),
    );
  });
```

and add these tests at the end of that `describe`:

```tsx
  it('logout also asks the server to end the session it just left', async () => {
    let body: unknown = null;
    server.use(
      http.post('/api/v1/auth/logout', async ({ request }) => {
        body = await request.json();
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderProbe();
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated');
    });
    await userEvent.click(screen.getByRole('button', { name: 'logout' }));
    await waitFor(() => {
      expect(body).toEqual({ refresh_token: 'r2' }); // the token the restore stored
    });
  });

  it('logout still works here when the server cannot be reached', async () => {
    let attempted = false;
    server.use(
      http.post('/api/v1/auth/logout', () => {
        attempted = true;
        return HttpResponse.error();
      }),
    );
    renderProbe();
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated');
    });
    await userEvent.click(screen.getByRole('button', { name: 'logout' }));
    expect(screen.getByTestId('status')).toHaveTextContent('anonymous');
    expect(session.getRefreshToken()).toBeNull();
    await waitFor(() => {
      expect(attempted).toBe(true);
    });
  });

  it('logout still works here when the server answers with an error', async () => {
    let attempted = false;
    server.use(
      http.post('/api/v1/auth/logout', () => {
        attempted = true;
        return HttpResponse.json({ detail: 'boom' }, { status: 500 });
      }),
    );
    renderProbe();
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated');
    });
    await userEvent.click(screen.getByRole('button', { name: 'logout' }));
    expect(screen.getByTestId('status')).toHaveTextContent('anonymous');
    await waitFor(() => {
      expect(attempted).toBe(true);
    });
  });

  it('does not call the server when another tab logged out', async () => {
    let calls = 0;
    server.use(
      http.post('/api/v1/auth/logout', () => {
        calls += 1;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderProbe();
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated');
    });
    window.dispatchEvent(new StorageEvent('storage', { key: REFRESH_TOKEN_KEY, newValue: null }));
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('anonymous');
    });
    await new Promise((resolve) => setTimeout(resolve, 50)); // a call would have arrived by now
    expect(calls).toBe(0);
  });
```

In `frontend/src/App.test.tsx`, in `rememberLogin()` add one handler to the `server.use(...)` list (after the `refresh` handler):

```tsx
    http.post('/api/v1/auth/logout', () => new HttpResponse(null, { status: 204 })),
```

In `frontend/src/components/AppLayout.test.tsx` replace the note test (currently named `'says, in visible text, that logging out only affects this browser'`) with:

```tsx
  it('says, in visible text, that logging out also ends the session on the server', () => {
    renderLayout();
    const note = screen.getByText('Logging out also ends this session on the server.');
    expect(note).toBeVisible();
    expect(note).toHaveAttribute('id');
    expect(screen.getByRole('button', { name: 'Log out' })).toHaveAccessibleDescription(
      note.textContent,
    );
    expect(screen.getByRole('button', { name: 'Log out' })).toHaveAttribute(
      'aria-describedby',
      note.id,
    );
  });
```

Create `frontend/src/realtime/streamLifecycle.test.tsx`:

```tsx
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { StrictMode } from 'react';
import { Navigate, Outlet, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it } from 'vitest';

import { AuthProvider } from '../auth/AuthProvider';
import { useAuth } from '../auth/authContext';
import { RequireAuth } from '../auth/RequireAuth';
import { REFRESH_TOKEN_KEY, session } from '../auth/session';
import { FakeSocket } from '../test/fakeSocket';
import { renderWithProviders } from '../test/render';
import { server } from '../test/server';
import { RealtimeProvider } from './RealtimeProvider';

const TOKENS = { access_token: 'a2', refresh_token: 'r2', token_type: 'bearer', expires_in: 900 };

const sockets: FakeSocket[] = [];
function createSocket(url: string): FakeSocket {
  const socket = new FakeSocket(url);
  sockets.push(socket);
  return socket;
}
function liveSockets(): FakeSocket[] {
  return sockets.filter((socket) => !socket.closed);
}

/** Stands in for the login page: logs in on click, then goes to the app like the real page does. */
function LoginStub() {
  const { status, login } = useAuth();
  if (status === 'authenticated') return <Navigate to="/" replace />;
  return (
    <button
      onClick={() => {
        void login('james', 'pw');
      }}
    >
      Log in
    </button>
  );
}

function HomeStub() {
  const { logout } = useAuth();
  return <button onClick={logout}>Log out</button>;
}

/** The app's real gate (`RequireAuth`) and stream (`RealtimeProvider`) around stub pages. */
function renderApp({ strict = false }: { strict?: boolean } = {}) {
  const tree = (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginStub />} />
        <Route element={<RequireAuth />}>
          <Route
            element={
              <RealtimeProvider createSocket={createSocket}>
                <Outlet />
              </RealtimeProvider>
            }
          >
            <Route index element={<HomeStub />} />
          </Route>
        </Route>
      </Routes>
    </AuthProvider>
  );
  return renderWithProviders(strict ? <StrictMode>{tree}</StrictMode> : tree);
}

describe('the live stream across logout and login', () => {
  beforeEach(() => {
    sockets.length = 0;
    session.clear();
    window.localStorage.setItem(REFRESH_TOKEN_KEY, 'r1');
    server.use(
      http.post('/api/v1/auth/refresh', () => HttpResponse.json(TOKENS)),
      http.post('/api/v1/auth/login', () => HttpResponse.json(TOKENS)),
      http.post('/api/v1/auth/logout', () => new HttpResponse(null, { status: 204 })),
    );
  });

  it('closes the stream on logout and opens a new one after the next login', async () => {
    renderApp();
    await screen.findByRole('button', { name: 'Log out' });
    await waitFor(() => {
      expect(sockets).toHaveLength(1);
    });

    await userEvent.click(screen.getByRole('button', { name: 'Log out' }));
    await screen.findByRole('button', { name: 'Log in' });
    expect(liveSockets()).toHaveLength(0);
    expect(sockets).toHaveLength(1); // logging out opened nothing new

    await userEvent.click(screen.getByRole('button', { name: 'Log in' }));
    await screen.findByRole('button', { name: 'Log out' });
    await waitFor(() => {
      expect(sockets).toHaveLength(2);
    });
    expect(liveSockets()).toEqual([sockets[1]]); // the old one stays closed
  });

  it('keeps exactly one live stream under StrictMode double mounting, and none after logout', async () => {
    renderApp({ strict: true });
    await screen.findByRole('button', { name: 'Log out' });
    await waitFor(() => {
      expect(liveSockets()).toHaveLength(1);
    });

    await userEvent.click(screen.getByRole('button', { name: 'Log out' }));
    await screen.findByRole('button', { name: 'Log in' });
    expect(liveSockets()).toHaveLength(0); // a leaked socket from the double mount would show here
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd "D:/Documents/Code/Bunshō/frontend" && npx vitest run src/auth/AuthProvider.test.tsx src/components/AppLayout.test.tsx src/realtime/streamLifecycle.test.tsx`
Expected: the new AuthProvider tests fail (the logout handler is never called), the AppLayout note test fails (old copy), the stream lifecycle tests may already pass (they pin existing behaviour) except that the `logout` call is missing.

- [ ] **Step 3: Write the implementation**

`frontend/src/api/client.ts`: append at the end of the file:

```ts

/**
 * Ask the server to end the login session behind `refreshToken`. Best effort: it never throws.
 * The caller has already forgotten the session locally, so when the server cannot be reached the
 * token simply stays valid until it expires, as it did before logout reached the server.
 */
export async function revokeSession(refreshToken: string): Promise<void> {
  try {
    await rawRequest<void>('/auth/logout', {
      method: 'POST',
      body: { refresh_token: refreshToken },
    });
  } catch {
    // Nothing to do: logging the error could only leak information, and the user is logged out here.
  }
}
```

`frontend/src/auth/AuthProvider.tsx`: change the import `import { refreshSession } from '../api/client';` to `import { refreshSession, revokeSession } from '../api/client';` and replace `logout` with:

```tsx
  const logout = useCallback(() => {
    const refreshToken = session.getRefreshToken(); // read before the session is cleared
    session.clear();
    queryClient.clear();
    setSessionExpired(false);
    setStatus('anonymous');
    // The screen has already changed; ending the session on the server (and closing its live
    // stream) happens in the background. Other tabs follow through the `storage` event and only
    // clear their own state.
    if (refreshToken !== null) void revokeSession(refreshToken);
  }, [queryClient]);
```

`frontend/src/components/AppLayout.tsx`: change the note text (line 72) to:

```tsx
              Logging out also ends this session on the server.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd "D:/Documents/Code/Bunshō/frontend" && npx vitest run`
Expected: the whole frontend suite passes (App.test's logout test now has its handler; nothing else logs out through the real provider).

- [ ] **Step 5: Format, lint, type-check, coverage**

Run: `cd "D:/Documents/Code/Bunshō/frontend" && npm run format && npm run lint && npm run build && npm run coverage`
Expected: clean; coverage thresholds (if configured) hold.

- [ ] **Step 6: Commit**

```bash
cd "D:/Documents/Code/Bunshō"
git add frontend/src/api/client.ts frontend/src/auth/AuthProvider.tsx frontend/src/auth/AuthProvider.test.tsx frontend/src/components/AppLayout.tsx frontend/src/components/AppLayout.test.tsx frontend/src/App.test.tsx frontend/src/realtime/streamLifecycle.test.tsx
git commit -m "feat(auth): Log out ends the session on the server" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: Release 1.4.0: version, CHANGELOG, README, TODO, full verification

**Files:**
- Modify: `pyproject.toml`, `src/bunsho/__init__.py`, `uv.lock` (version strings)
- Modify: `frontend/package.json`, `frontend/package-lock.json`, `frontend/openapi.json` (version strings)
- Modify: `CHANGELOG.md`
- Modify: `README.md` (three spots)
- Modify: `TODO.md` (move three items)

**Interfaces:** none (documentation and version only).

- [ ] **Step 1: Bump the version to 1.4.0**

Edit the version line from `1.3.0` to `1.4.0` in:
- `pyproject.toml` (`version = "1.3.0"`)
- `src/bunsho/__init__.py` (`__version__ = "1.3.0"`)
- `uv.lock`: the `version = "1.3.0"` line that belongs to `name = "bunsho"` (edit by hand; do not run `uv lock`, the local uv 0.6.14 may reformat the file)

Then:

```bash
cd "D:/Documents/Code/Bunshō/frontend" && npm version 1.4.0 --no-git-tag-version
cd .. && unset VIRTUAL_ENV && uv run python scripts/export_openapi.py
git diff --stat
```

Expected: `frontend/package.json`, `frontend/package-lock.json` (two places) and `frontend/openapi.json` (`info.version`) show a single-line version change each. If `git diff` shows anything else in those files, revert the extra hunks.

- [ ] **Step 2: CHANGELOG**

In `CHANGELOG.md`, directly under `## [Unreleased]` and above `## [1.3.0] - 2026-09-24`, add:

```markdown
## [1.4.0] - 2026-09-25

### Added

- `POST /api/v1/auth/logout` ends a login session on the server: its refresh token, every access
  token issued for it and its open live connections stop working. It answers 204 for any token, so
  it never reveals whether a token was valid, and it needs no access token.
- The UI's Log out now calls it (best effort: if the server cannot be reached you are still logged
  out in this browser, and the token stays valid until it expires).

### Changed

- Every login now has a session id in its tokens. Tokens issued before this version are rejected,
  so you have to log in once after upgrading.
- The note beside Log out now says it also ends the session on the server.

### Fixed

- A token refresh that was in flight when you logged out could sign you back in. A refresh answer
  that arrives after the session ended is now discarded, and a late rejection of the old token no
  longer signs you out of a newer login.
```

- [ ] **Step 3: README**

Make three edits in `README.md`:

1. In "Using the API", replace the `POST /api/v1/auth/login` bullet's ending so it reads (keep the words before it as they are):

```markdown
- `POST /api/v1/auth/login` with `{"username": ..., "password": ...}` returns an access and a refresh
  token; send the access token as `Authorization: Bearer <token>`. `POST /api/v1/auth/refresh` exchanges a
  refresh token for a new pair of the same login session. `POST /api/v1/auth/logout` with
  `{"refresh_token": ...}` ends that session on the server: the refresh token, every access token of the
  login and its open WebSocket streams stop working (streams close with code 1008). It answers `204` for
  any token, valid or not, and needs no access token. Revoked sessions are stored in `progress.db`, so
  they stay revoked across restarts.
```

2. In the WebSocket bullet, change the last sentence `Any invalid first message, a refresh token, or silence closes the socket with code 1008.` to:

```markdown
Any invalid first message, a refresh token, a token of a revoked session, or silence closes the
  socket with code 1008, and so does logging out the session that authenticated it.
```

3. In the "Web UI" paragraph, replace `The UI's Log out only clears the tokens in this browser; the server does not revoke them.` with:

```markdown
The UI's Log out clears the tokens in this browser and asks the server to end the session; if the server cannot be reached the token stays valid until it expires (30 days by default).
```

(Check the default in `config/service.py` — `refresh_ttl_days` — and use that number if it is not 30.)

- [ ] **Step 4: TODO.md**

In `TODO.md`, delete the three items from "Security & Auth" (the bullets starting `- [ ] Logout / revocation for the stateless refresh tokens`, `- [ ] Logout can be undone by a refresh that is in flight` and `- [ ] Test the logout -> login stream lifecycle`, each with its continuation line). Then, under `## Completed`, immediately before the `### Decisions` heading, add:

```markdown
### Session revocation (1.4.0)

- [x] Server-side logout: every login has a `sid` claim, `POST /auth/logout` revokes it (stored in
      `progress.db`, migration 0002), old tokens without a `sid` are rejected, and the session's open
      WebSockets are closed with 1008
- [x] Logout can no longer be undone by a refresh in flight: `session.ts` has an epoch and a late
      refresh answer (success or 401) from an earlier epoch is dropped
- [x] Tested the logout -> login stream lifecycle (stream closes on logout, a new one opens after
      login) and the StrictMode double mount
```

- [ ] **Step 5: Full verification (mirrors CI)**

Run:

```bash
cd "D:/Documents/Code/Bunshō" && unset VIRTUAL_ENV
uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run bandit -c pyproject.toml -r src/ -l
uv run pytest --cov --cov-report=term-missing -q
cd frontend && npm run format:check && npm run lint && npm run gen:api && git diff --exit-code -- src/api/schema.d.ts && npm run build && npm run coverage
```

Expected: everything clean and green, `git diff --exit-code` prints nothing. If `uv lock --check` is run locally and complains only because the local uv is older than the pinned CI version, note it in the PR body rather than rewriting the lockfile.

- [ ] **Step 6: Commit**

```bash
cd "D:/Documents/Code/Bunshō"
git add pyproject.toml src/bunsho/__init__.py uv.lock frontend/package.json frontend/package-lock.json frontend/openapi.json CHANGELOG.md README.md TODO.md
git commit -m "chore(release): bump version to 1.4.0" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Not verified by the plan (hand to James in the PR body)

- Authenticated screens cannot be exercised by the controller in a browser (the controller never types the password). Ask James to check in a real browser: Log out then Back button, two tabs where one logs out, and the Log out note wording at phone width.
- No tag or release is created (that one-way step is James's).
