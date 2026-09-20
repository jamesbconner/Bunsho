# Bunshō Plan 2B-1: Frontend Skeleton and Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a deployed, working UI: a Vite + React + TypeScript app (login, app shell, Home, and the content Build screen with live WebSocket progress) served by the FastAPI backend from the Docker image, with CI, Dependabot and smoke-test coverage.

**Architecture:** `frontend/` holds the SPA. The API's OpenAPI document is committed as `frontend/openapi.json` and turned into `src/api/schema.d.ts` (two drift checks keep backend and frontend in step). A single `request()` wrapper adds the bearer token, refreshes once on a 401 (single-flight) and retries once. The refresh token lives in `localStorage`, the access token in memory. A framework-free `BuildStream` class talks to the server's `/ws/tasks` stream with backoff, wrapped by a `RealtimeProvider`. FastAPI serves the built assets with a single-page-app fallback (`paths.frontend_dir`); the Dockerfile gains a Node build stage.

**Tech Stack:** React 19, Vite 8, TypeScript 6.0 (see "Version exceptions"), Mantine 9 (+ `@mantine/form`, `@mantine/notifications`), React Router 8 (declarative mode), TanStack Query 5, ofetch, openapi-typescript, Vitest 5 + React Testing Library + MSW 2, ESLint 10, Prettier 3, Node 24 (LTS). Backend: Python 3.13, FastAPI.

**Spec:** `docs/superpowers/specs/2026-09-20-bunsho-2b1-frontend-skeleton-design.md` (parent: `2026-09-20-bunsho-2a-review-engine-design.md`). Read it before starting.

## Global Constraints

Every task's requirements include this section.

- **Latest stable versions of every library and tool** (James, 2026-09-20): install with `@latest` at execution time and record the resolved versions in the PR. An older major is allowed only when the newest cannot work with something else in the stack; the single exception known today is below.
- Backend: Python `>=3.13`; ruff line length `100`; mypy `strict`; bandit clean (no `assert` in `src/`); coverage `fail_under = 90`. Google-style docstrings on public Python code.
- Frontend: strict TypeScript (`strict`, `noUncheckedIndexedAccess`, `erasableSyntaxOnly`: no enums, no parameter properties, no namespaces; use `import type`); ESLint (flat config, `recommendedTypeChecked`, `react-hooks`, `react-refresh`) with zero errors; Prettier (`singleQuote`, `printWidth: 100`, `trailingComma: all`) with `format:check` clean; coverage gate 80% (lines, functions, branches, statements).
- Hand-written API types are forbidden: every request/response type comes from `src/api/schema.d.ts` (generated from `frontend/openapi.json`).
- All UI text is English; every Japanese text run carries `lang="ja"`; the HTML root is `lang="en"`.
- Tokens (access or refresh) are never put in URLs, logs, query keys or the query cache. The refresh token is stored only under `localStorage` key `bunsho.refresh_token`.
- API base path `/api/v1`; the WebSocket protocol is the server's: send `{"type":"auth","token":<access token>}` first; receive `ready`, then `snapshot`, then `event` messages; close code `1008` means authentication failed.
- Port `8192` for the API (never `8000`). Frontend dev server proxies `/api` (WebSocket included) to `http://127.0.0.1:8192` (override `VITE_API_TARGET`).
- Commits: conventional commits, stage explicit paths only (never `git add .` / `-A`), trailer as its own paragraph: `git commit -m "<subject>" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"`. Never stage `.gitignore` (the repo root one is user-owned; the frontend has its own inside `frontend/`), `.python-version`, `.superpowers/`. **This plan explicitly authorises** editing `.gitattributes`, `.github/workflows/ci.yml`, `.github/dependabot.yml` (Tasks 1 and 4). Never merge to `main`; James merges.
- Windows / Git Bash quirks: run `unset VIRTUAL_ENV` before `uv`; quote paths (`Bunshō` contains ō); set `PYTHONIOENCODING=utf-8` when printing Japanese; re-read files containing Japanese or backslash escapes after writing them; add an import only together with its first use (a formatter hook can drop unused imports).
- Verification commands. Backend (repo root): `uv run ruff format . && uv run ruff check . && uv run mypy && uv run bandit -c pyproject.toml -r src -q && uv run pytest -q`. Frontend (`frontend/`): `npm run format:check && npm run lint && npm run build && npm run coverage`.

## Version exceptions (verified 2026-09-20)

Resolved latest versions on that day: react/react-dom 19.3.0, vite 8.3.0, @vitejs/plugin-react 6.1.1, @mantine/* 9.6.1, react-router 8.4.0, @tanstack/react-query 5.103.1, ofetch 1.5.1, openapi-typescript 7.13.0, vitest/@vitest/coverage-v8 5.0.1, jsdom 30.1.0, @testing-library/react 16.3.3 (+ dom 10.4.2, user-event 14.6.7, jest-dom 7.0.1), msw 2.15.0, eslint 10.11.0, typescript-eslint 8.70.0, prettier 3.9.8, Node 24 LTS ("Krypton"; Node 26 is not LTS yet).

**One exception, recorded for the PR:** TypeScript is pinned to **6.0.3**, not the newest 7.0.2, because `typescript-eslint` 8.70 supports only `typescript <6.1.0` and `openapi-typescript` 7.13 needs the JavaScript compiler API (declared `^5.x`; verified to run on 6.0.3 with an `overrides` entry, which npm needs to accept its peer range). Move to TypeScript 7 as soon as both tools support it (Dependabot will not do this by itself because of the pin: note it in `TODO.md`). `@types/node` is pinned to the `24` line to match the Node 24 runtime.

## Refinements to the spec

1. The HTML root is `lang="en"` (English UI text); every Japanese run carries `lang="ja"`. (The spec said `lang="ja"` on the root: that would make screen readers read English in a Japanese voice.)
2. Task order differs from the spec: the real-time provider (Task 7) and the Build screen (Task 8) come before the shell, Home page and routing (Task 9), so each screen is tested on its own before it is wired and no file is written in two versions.
3. React Router is used in **declarative** mode (`BrowserRouter`, `Routes`, `Route`, `Navigate`, `Outlet`); TanStack Query owns data fetching.
4. `ConnectionBadge` shows "Reconnecting in N s"; a Mantine `SegmentedControl` provides the theme toggle.
5. `POST` to an unknown non-API path served by the static mount answers 405 (Starlette's `StaticFiles` only allows GET and HEAD); unknown `GET /api/...` paths keep their JSON 404.

## Verified prototype

The tooling configs and the code marked "verified" below were written and run in a scratch project with exactly these versions (tsc, ESLint, Prettier, 102 tests in 19 files, about 98% line coverage, production build all green). They are inlined verbatim; if a command disagrees, fix the disagreement minimally and report it, never weaken a check.

## File Structure

New (backend): `src/bunsho/api/openapi_snapshot.py`, `src/bunsho/api/static.py`, `scripts/export_openapi.py`, `tests/unit/api/test_openapi_snapshot.py`, `tests/unit/api/test_static.py`. Modified (backend): `src/bunsho/config/settings.py`, `src/bunsho/api/app.py`, `.gitattributes`, `Dockerfile`, `.github/workflows/ci.yml`, `.github/dependabot.yml`, `scripts/smoke_test.py`, `tests/unit/config/test_settings.py`, README/CHANGELOG/TODO.

New (frontend, all under `frontend/`): `package.json`, `package-lock.json`, `tsconfig*.json`, `vite.config.ts`, `eslint.config.js`, `.prettierrc`, `.prettierignore`, `.gitignore`, `postcss.config.cjs`, `index.html`, `openapi.json`, and under `src/`: `main.tsx`, `App.tsx`, `theme.ts`, `queryClient.ts`, `api/{schema.d.ts,errors.ts,http.ts,client.ts,endpoints.ts,queries.ts}`, `auth/{session.ts,authContext.ts,AuthProvider.tsx,RequireAuth.tsx}`, `hooks/useCountdown.ts`, `realtime/{backoff.ts,messages.ts,BuildStream.ts,applyMessage.ts,realtimeContext.ts,RealtimeProvider.tsx,ConnectionBadge.tsx}`, `components/{AppLayout.tsx,ColorSchemeToggle.tsx,ErrorBoundary.tsx}`, `features/{login/LoginPage.tsx,home/HomePage.tsx,build/*,NotFoundPage.tsx}`, `test/{setup.ts,server.ts,render.tsx,fakeSocket.ts}`, plus a `*.test.ts(x)` next to each.

---

## Task 0: Branch and draft PR

**Files:** none.

- [ ] **Step 1: Confirm the docs PR (spec and this plan) is merged**

Run: `gh pr list --state all --limit 3`
Expected: the `docs/plan-2b1` PR shows `MERGED`. If it does not, stop and ask James (no stacked branches).

- [ ] **Step 2: Branch from a fresh main**

```bash
git checkout main && git pull
git checkout -b feat/plan-2b1-frontend-skeleton
```

- [ ] **Step 3: Draft PR after the first commit (Task 1)**

After Task 1's commit: `git push -u origin feat/plan-2b1-frontend-skeleton`, then `gh pr create --draft --title "Plan 2B-1: frontend skeleton and delivery" --body "<summary>\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"`. CI then runs on every push (ubuntu, windows, macOS).

---

## Task 1: OpenAPI snapshot export and drift test

**Files:**
- Create: `src/bunsho/api/openapi_snapshot.py`, `scripts/export_openapi.py`, `frontend/openapi.json` (generated), `tests/unit/api/test_openapi_snapshot.py`
- Modify: `.gitattributes`

**Interfaces:**
- Consumes: `bunsho.api.app.create_app`, `ServiceConfig`/`ServerSettings`/`AuthSettings`, `AppConfig`.
- Produces: `bunsho.api.openapi_snapshot.openapi_document() -> dict[str, Any]` and `render_openapi_snapshot() -> str` (JSON, `indent=2`, `sort_keys=True`, `ensure_ascii=False`, trailing newline); `frontend/openapi.json`; the command `uv run python scripts/export_openapi.py`.

- [ ] **Step 1: Write the failing drift tests**

Create `tests/unit/api/test_openapi_snapshot.py`:

```python
import json
from pathlib import Path

import pytest

from bunsho.api.openapi_snapshot import openapi_document, render_openapi_snapshot

SNAPSHOT = Path(__file__).resolve().parents[3] / "frontend" / "openapi.json"


def test_the_committed_snapshot_matches_the_app() -> None:
    assert SNAPSHOT.read_text(encoding="utf-8") == render_openapi_snapshot(), (
        "frontend/openapi.json is stale: run `uv run python scripts/export_openapi.py`, "
        "then `npm run gen:api` in frontend/, and commit both files"
    )


def test_the_rendering_is_deterministic_with_sorted_keys() -> None:
    first = render_openapi_snapshot()
    assert first == render_openapi_snapshot()
    assert first.endswith("}\n")
    document = json.loads(first)
    assert list(document) == sorted(document)
    assert list(document["paths"]) == sorted(document["paths"])


def test_the_document_describes_the_routes_the_frontend_uses() -> None:
    document = openapi_document()
    operations = {
        operation["operationId"]
        for methods in document["paths"].values()
        for operation in methods.values()
    }
    assert {
        "login",
        "refreshToken",
        "getContentSummary",
        "getConfigCheck",
        "startContentBuild",
        "getLatestContentBuild",
        "getContentBuild",
        "getNextReview",
        "answerReview",
    } <= operations
    schemas = document["components"]["schemas"]
    assert {"WsAuthMessage", "WsSnapshot", "WsEvent", "BuildStatusResponse"} <= set(schemas)


def test_building_the_document_touches_no_filesystem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    render_openapi_snapshot()
    assert list(tmp_path.iterdir()) == []
```

Run: `unset VIRTUAL_ENV; uv run pytest tests/unit/api/test_openapi_snapshot.py -q`
Expected: FAIL (`ModuleNotFoundError: bunsho.api.openapi_snapshot`).

- [ ] **Step 2: Implement the snapshot module**

Create `src/bunsho/api/openapi_snapshot.py`:

```python
"""The API's OpenAPI document as the frontend's committed type source.

``frontend/openapi.json`` is generated from the app itself, so the TypeScript client can never
describe an API that does not exist. ``scripts/export_openapi.py`` writes the file; a unit test
fails when the committed copy is stale.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from bunsho.api.app import create_app
from bunsho.config.service import AuthSettings, ServerSettings, ServiceConfig
from bunsho.config.settings import DEFAULT_DECK_FILENAME, DEFAULT_DECK_SHA256, AppConfig

# Never used: the lifespan does not run, so nothing ever logs in.
_PLACEHOLDER_HASH = "$argon2id$placeholder"


def _placeholder_config(root: Path) -> ServiceConfig:
    """A configuration that only has to satisfy the constructors: the lifespan never runs."""
    return ServiceConfig(
        app=AppConfig(
            data_dir=root / "data",
            resources_dir=root / "resources",
            deck_filename=DEFAULT_DECK_FILENAME,
            deck_sha256=DEFAULT_DECK_SHA256,
            jamdict_db=None,
            log_level="INFO",
        ),
        server=ServerSettings(host="127.0.0.1", port=8192, cors_origins=()),
        auth=AuthSettings(
            username="openapi",
            password_hash=_PLACEHOLDER_HASH,
            jwt_secret="x" * 32,
            access_ttl_minutes=15,
            refresh_ttl_days=30,
        ),
    )


def openapi_document() -> dict[str, Any]:
    """Build the app (without starting it) and return its OpenAPI document."""
    with tempfile.TemporaryDirectory() as tmp:
        return create_app(_placeholder_config(Path(tmp))).openapi()


def render_openapi_snapshot() -> str:
    """The document as stable text: sorted keys, two-space indent, UTF-8, trailing newline."""
    return json.dumps(openapi_document(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
```

- [ ] **Step 3: Add the export script and generate the snapshot**

Create `scripts/export_openapi.py`:

```python
"""Write the API's OpenAPI document to frontend/openapi.json (the frontend's type source).

Usage: ``uv run python scripts/export_openapi.py``. Then run ``npm run gen:api`` in ``frontend/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from bunsho.api.openapi_snapshot import render_openapi_snapshot

SNAPSHOT = Path(__file__).resolve().parent.parent / "frontend" / "openapi.json"


def main() -> int:
    """Write the snapshot and report where."""
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(render_openapi_snapshot(), encoding="utf-8", newline="\n")
    sys.stderr.write(f"wrote {SNAPSHOT}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Append to `.gitattributes` (a tracked file; the repo-root `.gitignore` is not touched):

```
frontend/** text eol=lf
```

Run:
```bash
unset VIRTUAL_ENV
uv run python scripts/export_openapi.py
uv run pytest tests/unit/api/test_openapi_snapshot.py -q
```
Expected: `wrote .../frontend/openapi.json`, then all four tests PASS.

- [ ] **Step 4: Lint, full suite, commit**

```bash
uv run ruff format . && uv run ruff check . && uv run mypy && uv run bandit -c pyproject.toml -r src -q
uv run pytest -q
git add src/bunsho/api/openapi_snapshot.py scripts/export_openapi.py frontend/openapi.json tests/unit/api/test_openapi_snapshot.py .gitattributes
git commit -m "feat: committed OpenAPI snapshot with a drift test" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
Expected: all clean and green. Then push and open the draft PR (Task 0, Step 3).

---

## Task 2: Backend static serving of the built UI

**Files:**
- Modify: `src/bunsho/config/settings.py`, `src/bunsho/api/app.py`, `tests/unit/config/test_settings.py` (append)
- Create: `src/bunsho/api/static.py`, `tests/unit/api/test_static.py`

**Interfaces:**
- Consumes: `AppConfig`, `ServiceConfig`, `create_app`.
- Produces: `AppConfig.frontend_dir: Path | None` (default `None`; env `BUNSHO_PATHS__FRONTEND_DIR`); `bunsho.api.static.SPAStaticFiles(directory, html=True)`; behaviour: `GET /` and unknown extension-less non-API paths return `index.html` (`Cache-Control: no-cache`), `assets/*` are `public, max-age=31536000, immutable`, every response has `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`; unknown `/api/...` GETs keep their JSON 404; the mount is last, so API routes, `/docs` and `/openapi.json` win.

- [ ] **Step 1: Write the failing configuration tests**

Append to `tests/unit/config/test_settings.py` (its imports already cover `Path`, `ConfigNormalizer`, `load_app_config`, `validate_config`):

```python
def test_frontend_dir_is_unset_by_default() -> None:
    assert load_app_config(ConfigNormalizer()).frontend_dir is None


def test_frontend_dir_is_read_from_the_paths_section(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    config = load_app_config(ConfigNormalizer({"paths": {"frontend_dir": str(dist)}}))
    assert config.frontend_dir == dist


def test_frontend_dir_must_be_a_directory(tmp_path: Path) -> None:
    errors = validate_config(ConfigNormalizer({"paths": {"frontend_dir": str(tmp_path / "nope")}}))
    assert any("frontend_dir" in error and "not a directory" in error for error in errors)
```

Run: `uv run pytest tests/unit/config/test_settings.py -q` → Expected: the three new tests FAIL.

- [ ] **Step 2: Add the setting**

In `src/bunsho/config/settings.py`: add to the `AppConfig` dataclass, after `log_level: str`:

```python
    frontend_dir: Path | None = None
```
(update the class docstring with: "``frontend_dir`` is the built web UI to serve; ``None`` serves the API only."), in `from_normalizer` read it and pass it:

```python
        frontend = cfg.get_string("paths", "frontend_dir")
```
and add `frontend_dir=Path(frontend) if frontend else None,` to the `cls(...)` call; in `validate_config`, before `return errors`:

```python
    frontend = cfg.get_string("paths", "frontend_dir")
    if frontend and not Path(frontend).is_dir():
        errors.append(
            f"[paths] frontend_dir={frontend!r} is not a directory; build the UI with "
            "'npm run build' in frontend/, or unset it to serve the API only"
        )
```
Run: `uv run pytest tests/unit/config -q` → Expected: PASS.

- [ ] **Step 3: Write the failing static-serving tests**

Create `tests/unit/api/test_static.py`:

```python
import dataclasses
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bunsho.api.app import create_app
from bunsho.config.service import ServiceConfig

INDEX_HTML = '<!doctype html><html><body><div id="root"></div></body></html>'
SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
}


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (root / "assets" / "app-abc123.js").write_text("console.log(1);", encoding="utf-8")
    (root / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("top secret", encoding="utf-8")
    return root


@pytest.fixture
def ui_client(service_config: ServiceConfig, dist: Path) -> Iterator[TestClient]:
    app_config = dataclasses.replace(service_config.app, frontend_dir=dist)
    config = dataclasses.replace(service_config, app=app_config)
    with TestClient(create_app(config)) as client:
        yield client


def test_the_root_serves_the_app_shell_without_caching(ui_client: TestClient) -> None:
    response = ui_client.get("/")
    assert response.status_code == 200
    assert response.text == INDEX_HTML
    assert response.headers["cache-control"] == "no-cache"
    for name, value in SECURITY_HEADERS.items():
        assert response.headers[name] == value


@pytest.mark.parametrize("path", ["/build", "/some/nested/route", "/login"])
def test_client_side_routes_fall_back_to_the_shell(ui_client: TestClient, path: str) -> None:
    response = ui_client.get(path)
    assert response.status_code == 200
    assert response.text == INDEX_HTML
    assert response.headers["cache-control"] == "no-cache"


def test_hashed_assets_are_cached_forever(ui_client: TestClient) -> None:
    response = ui_client.get("/assets/app-abc123.js")
    assert response.status_code == 200
    assert response.text == "console.log(1);"
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_other_files_are_served_but_not_cached(ui_client: TestClient) -> None:
    response = ui_client.get("/favicon.svg")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize("path", ["/assets/missing.js", "/nope.png", "/assets/missing.css"])
def test_missing_files_are_a_404_not_the_shell(ui_client: TestClient, path: str) -> None:
    assert ui_client.get(path).status_code == 404


@pytest.mark.parametrize("path", ["/api/v1/does-not-exist", "/api/nothing", "/api"])
def test_unknown_api_paths_keep_their_json_404(ui_client: TestClient, path: str) -> None:
    response = ui_client.get(path)
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_api_routes_docs_and_the_schema_still_win(ui_client: TestClient) -> None:
    health = ui_client.get("/api/v1/health")
    assert health.status_code == 200
    assert "components" in health.json()
    assert ui_client.get("/api/v1/reviews/next").status_code == 401
    assert ui_client.get("/openapi.json").json()["openapi"].startswith("3.")
    assert ui_client.get("/docs").status_code == 200


def test_head_works_and_other_methods_are_refused(ui_client: TestClient) -> None:
    assert ui_client.head("/").status_code == 200
    assert ui_client.post("/", json={}).status_code == 405


def test_a_path_traversal_cannot_leave_the_frontend_folder(ui_client: TestClient) -> None:
    response = ui_client.get("/%2e%2e/secret.txt")
    assert "top secret" not in response.text


def test_without_a_frontend_folder_the_root_is_a_plain_json_404(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
```

Run: `uv run pytest tests/unit/api/test_static.py -q` → Expected: FAIL (`ModuleNotFoundError` / 404 for the shell).

- [ ] **Step 4: Implement `SPAStaticFiles` and mount it**

Create `src/bunsho/api/static.py`:

```python
"""Serving the built frontend: hashed assets, the single-page-app shell and deep-link fallback."""

from __future__ import annotations

from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

INDEX = "index.html"
_IMMUTABLE = "public, max-age=31536000, immutable"
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


def _posix(path: str) -> str:
    """The mount-relative path with forward slashes (Starlette hands over OS separators)."""
    return path.replace("\\", "/")


def _is_client_route(path: str) -> bool:
    """Whether the single-page app should answer this path: not an API path, no file extension."""
    if path == "api" or path.startswith("api/"):
        return False
    return "." not in path.rsplit("/", 1)[-1]


def _decorate(response: Response, path: str) -> None:
    """Cache hashed assets forever, never cache the shell, and add the security headers."""
    response.headers["Cache-Control"] = _IMMUTABLE if path.startswith("assets/") else "no-cache"
    for name, value in _SECURITY_HEADERS.items():
        response.headers[name] = value


class SPAStaticFiles(StaticFiles):
    """``StaticFiles`` for a single-page app.

    An unknown path without a file extension gets ``index.html`` so a deep link such as
    ``/build`` survives a page reload; unknown API paths and missing files stay 404.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        """Serve ``path`` from the build folder, falling back to the app shell for client routes.

        Args:
            path: The path relative to the mount (``""`` for the root).
            scope: The ASGI scope.

        Returns:
            The file response with cache and security headers.

        Raises:
            HTTPException: 404 for unknown API paths and for missing files.
        """
        served = _posix(path)  # on Windows Starlette passes "api\nothing", not "api/nothing"
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or not _is_client_route(served):
                raise
            response = await super().get_response(INDEX, scope)
            served = INDEX
        _decorate(response, served)
        return response
```

In `src/bunsho/api/app.py`: add `from bunsho.api.static import SPAStaticFiles` (sorted with the other `bunsho.api` imports); in the `lifespan`, right after `configure_logging(config.app.log_level, force=False)`, add:

```python
        if config.app.frontend_dir is None:
            logging.getLogger("bunsho").info("frontend_not_configured api_only=true")
        else:
            logging.getLogger("bunsho").info("frontend_serving dir=%s", config.app.frontend_dir)
```
and in `create_app`, after the last `app.include_router(...)` line and before `_publish_websocket_schemas(app)`:

```python
    if config.app.frontend_dir is not None:
        # Last on purpose: API routes, /docs and /openapi.json must win over the catch-all mount.
        app.mount("/", SPAStaticFiles(directory=config.app.frontend_dir, html=True), name="frontend")
```
Run: `uv run pytest tests/unit/api/test_static.py tests/unit/config -q` → Expected: PASS. (On Windows Starlette passes `get_response` a path with backslashes; the `_posix` helper is why the cache headers and the `/api` rule work there too: keep it, the Windows CI job depends on it.)

- [ ] **Step 5: Lint, full suite, commit**

```bash
uv run ruff format . && uv run ruff check . && uv run mypy && uv run bandit -c pyproject.toml -r src -q
uv run pytest -q
git add src/bunsho/config/settings.py src/bunsho/api/app.py src/bunsho/api/static.py tests/unit/config/test_settings.py tests/unit/api/test_static.py
git commit -m "feat: serve the built frontend with a single-page-app fallback" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
Expected: all clean and green (the OpenAPI snapshot test must still pass: mounting static files does not change the document; if it fails, regenerate with `scripts/export_openapi.py` and include the file in the commit).

## Task 3: Frontend scaffold

**Files:** everything under `frontend/` listed below.

**Interfaces:**
- Consumes: `frontend/openapi.json` (Task 1).
- Produces: a buildable, linted, tested Vite + React + TypeScript app whose page is a "hello" wordmark; scripts `dev`, `build`, `preview`, `lint`, `format`, `format:check`, `test`, `test:watch`, `coverage`, `gen:api`; `src/api/schema.d.ts` (generated, committed); `src/theme.ts` (`theme`, `UI_FONT_FAMILY`); test helpers `src/test/{setup.ts,server.ts,render.tsx}` (`renderWithProviders`, `createTestQueryClient`, the shared MSW `server`).

- [ ] **Step 1: Create the package with the latest versions**

```bash
mkdir -p frontend && cd frontend
```
Create `frontend/package.json`:

```json
{
  "name": "bunsho-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "engines": { "node": ">=24" },
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "lint": "eslint .",
    "format": "prettier --write .",
    "format:check": "prettier --check .",
    "test": "vitest run",
    "test:watch": "vitest",
    "coverage": "vitest run --coverage",
    "gen:api": "openapi-typescript openapi.json -o src/api/schema.d.ts"
  },
  "overrides": {
    "openapi-typescript": { "typescript": "$typescript" }
  }
}
```
Then install (from `frontend/`; this resolves the newest versions, and npm writes them into `package.json` and `package-lock.json`):

```bash
npm install --save react@latest react-dom@latest react-router@latest @tanstack/react-query@latest ofetch@latest @mantine/core@latest @mantine/hooks@latest @mantine/notifications@latest @mantine/form@latest
npm install --save-dev vite@latest @vitejs/plugin-react@latest typescript@6.0.3 @types/react@latest @types/react-dom@latest @types/node@24 eslint@latest @eslint/js@latest typescript-eslint@latest eslint-plugin-react-hooks@latest eslint-plugin-react-refresh@latest globals@latest prettier@latest vitest@latest @vitest/coverage-v8@latest jsdom@latest @testing-library/react@latest @testing-library/dom@latest @testing-library/user-event@latest @testing-library/jest-dom@latest msw@latest openapi-typescript@latest postcss@latest postcss-preset-mantine@latest postcss-simple-vars@latest
```
Expected: `found 0 vulnerabilities`; a warning that `msw`'s postinstall script is not approved is harmless (it only installs the browser worker, which Node tests do not use). **Why `typescript@6.0.3` and the `overrides` entry:** see "Version exceptions". Check `npx tsc -v` prints `Version 6.0.3` and that the resolved versions match "Version exceptions" (record any difference).

- [ ] **Step 2: Add the tooling configuration (verified files)**

Create `frontend/tsconfig.json`:

```json
{
  "files": [],
  "references": [{ "path": "./tsconfig.app.json" }, { "path": "./tsconfig.node.json" }]
}
```

Create `frontend/tsconfig.app.json`:

```json
{
  "compilerOptions": {
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.app.tsbuildinfo",
    "target": "ES2023",
    "useDefineForClassFields": true,
    "lib": ["ES2023", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "types": ["vite/client"],
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "verbatimModuleSyntax": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "erasableSyntaxOnly": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"]
}
```

Create `frontend/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.node.tsbuildinfo",
    "target": "ES2023",
    "lib": ["ES2023"],
    "module": "ESNext",
    "types": ["node"],
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "verbatimModuleSyntax": true,
    "moduleDetection": "force",
    "noEmit": true,
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "erasableSyntaxOnly": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["vite.config.ts", "eslint.config.js"]
}
```

Create `frontend/vite.config.ts`:

```ts
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// Development proxy: the browser talks to the Vite server, which forwards the API (and its
// WebSocket) to the backend, so the dev setup needs no CORS. Override the target with
// VITE_API_TARGET when the backend is not on the default port.
const apiTarget = process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8192';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: apiTarget, ws: true },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/api/schema.d.ts', 'src/test/**', 'src/main.tsx', 'src/**/*.test.{ts,tsx}'],
      thresholds: { lines: 80, functions: 80, branches: 80, statements: 80 },
    },
  },
});
```

Create `frontend/eslint.config.js`:

```js
import js from '@eslint/js';
import { defineConfig, globalIgnores } from 'eslint/config';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default defineConfig([
  globalIgnores(['dist', 'coverage', 'src/api/schema.d.ts']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommendedTypeChecked,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2023,
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },
]);
```

Create `frontend/.prettierrc`:

```json
{
  "singleQuote": true,
  "printWidth": 100,
  "trailingComma": "all"
}
```

Create `frontend/.prettierignore`:

```text
dist
coverage
node_modules
src/api/schema.d.ts
openapi.json
package.json
package-lock.json
```

Create `frontend/postcss.config.cjs`:

```js
module.exports = {
  plugins: {
    'postcss-preset-mantine': {},
    'postcss-simple-vars': {
      variables: {
        'mantine-breakpoint-xs': '36em',
        'mantine-breakpoint-sm': '48em',
        'mantine-breakpoint-md': '62em',
        'mantine-breakpoint-lg': '75em',
        'mantine-breakpoint-xl': '88em',
      },
    },
  },
};
```

Create `frontend/.gitignore`:

```
node_modules
dist
coverage
*.tsbuildinfo
```

Create `frontend/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Bunshō</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 3: Add the source files (verified files)**

Create `frontend/src/theme.ts`:

```ts
import { createTheme } from '@mantine/core';

/** UI font stack: Latin text first, then the Japanese system fonts of macOS, Windows and Linux. */
export const UI_FONT_FAMILY =
  "system-ui, -apple-system, 'Segoe UI', 'Hiragino Sans', 'Yu Gothic UI', 'Noto Sans JP', sans-serif";

export const theme = createTheme({
  fontFamily: UI_FONT_FAMILY,
  headings: { fontFamily: UI_FONT_FAMILY },
  primaryColor: 'indigo',
});
```

Create `frontend/src/App.tsx` (a temporary hello page; Task 9 replaces it):

```tsx
import { Container, MantineProvider, Text, Title } from '@mantine/core';
import { Notifications } from '@mantine/notifications';

import { theme } from './theme';

import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';

export function App() {
  return (
    <MantineProvider theme={theme} defaultColorScheme="auto">
      <Notifications />
      <Container py="xl">
        <Title order={1}>
          Bunshō{' '}
          <span lang="ja" data-testid="wordmark-ja">
            文章
          </span>
        </Title>
        <Text c="dimmed">Hello from the frontend skeleton.</Text>
      </Container>
    </MantineProvider>
  );
}
```


Create `frontend/src/main.tsx`:

```tsx
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from './App';

const container = document.getElementById('root');
if (container === null) {
  throw new Error('Missing #root element in index.html');
}
createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

Create `frontend/src/test/server.ts`:

```ts
import { setupServer } from 'msw/node';

/** The shared MSW server. Tests add handlers with `server.use(...)`; each test starts clean. */
export const server = setupServer();
```

Create `frontend/src/test/setup.ts`:

```ts
import '@testing-library/jest-dom/vitest';

import { notifications } from '@mantine/notifications';
import { cleanup } from '@testing-library/react';
import { afterAll, afterEach, beforeAll } from 'vitest';

import { server } from './server';

// jsdom lacks a few browser APIs that Mantine components use.
const originalGetComputedStyle = window.getComputedStyle.bind(window);
window.getComputedStyle = (element) => originalGetComputedStyle(element);
window.HTMLElement.prototype.scrollIntoView = () => {};
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.ResizeObserver = ResizeObserverStub;

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' });
});
afterEach(() => {
  cleanup();
  notifications.clean();
  window.localStorage.clear();
  server.resetHandlers();
});
afterAll(() => {
  server.close();
});
```

Create `frontend/src/test/render.tsx`:

```tsx
import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, type RenderResult } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter, type InitialEntry } from 'react-router';

import { theme } from '../theme';

/** A query client for tests: no retries, so a failing request fails the test immediately. */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

interface RenderOptions {
  initialEntries?: InitialEntry[];
  queryClient?: QueryClient;
}

/** Render `ui` inside the providers every screen needs (theme, query client, router). */
export function renderWithProviders(
  ui: ReactElement,
  { initialEntries = ['/'], queryClient = createTestQueryClient() }: RenderOptions = {},
): RenderResult & { queryClient: QueryClient } {
  const result = render(
    <MantineProvider theme={theme} env="test">
      <Notifications />
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
  return { ...result, queryClient };
}
```

Create `frontend/src/App.test.tsx` (temporary; Task 9 replaces it):

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { App } from './App';

describe('App', () => {
  it('renders the wordmark with the Japanese run marked as Japanese', () => {
    render(<App />);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Bunshō');
    expect(screen.getByTestId('wordmark-ja')).toHaveAttribute('lang', 'ja');
  });
});
```


- [ ] **Step 4: Generate the API types**

```bash
npm run gen:api
```
Expected: `openapi.json → src/api/schema.d.ts`. In the generated file, response fields that have defaults are **required** (for example `TypeCounts` has `kana: number;`, not `kana?: number;`); if they are optional, the backend's `json_schema_serialization_defaults_required` change is missing: stop and report.

- [ ] **Step 5: Run the whole frontend gate**

```bash
npm run format          # formats what you just created
npm run format:check && npm run lint && npm run build && npm run coverage
```
Expected: Prettier clean, ESLint clean, `tsc -b` and `vite build` succeed (`dist/index.html`, one CSS and one JS asset), 1 test passes, coverage thresholds met. (`vitest` may take about 20 seconds the first time: jsdom start-up.)

- [ ] **Step 6: Commit**

```bash
cd ..
git add frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/tsconfig.app.json frontend/tsconfig.node.json frontend/vite.config.ts frontend/eslint.config.js frontend/.prettierrc frontend/.prettierignore frontend/.gitignore frontend/postcss.config.cjs frontend/index.html frontend/src
git commit -m "feat: frontend scaffold (Vite, React, TypeScript, Mantine, Vitest)" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
(`frontend/openapi.json` was committed in Task 1; `git status` must be clean afterwards.)

---

## Task 4: Delivery: Docker Node stage, CI job, Dependabot, smoke test

**Files:**
- Modify: `Dockerfile`, `.dockerignore`, `.github/workflows/ci.yml`, `.github/dependabot.yml`, `scripts/smoke_test.py`

**Interfaces:**
- Consumes: Tasks 2 and 3 (`BUNSHO_PATHS__FRONTEND_DIR`, `frontend/` scripts).
- Produces: an image that serves the UI at `http://<host>:8192/`; a CI `frontend` job; a Dependabot `npm` entry; smoke-test checks `expect_frontend_served()`.

- [ ] **Step 1: Add the Node build stage to the Dockerfile**

In `Dockerfile`, replace the first lines (`# syntax=...` stays) so the top reads:

```dockerfile
# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.13
ARG NODE_VERSION=24

# ---- frontend: build the static UI (no Python needed: the API types are committed) ----
FROM node:${NODE_VERSION}-bookworm-slim AS frontend
WORKDIR /frontend
# Dependencies first so this layer is cached until package.json or the lockfile change.
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci
COPY frontend ./
RUN npm run build
```
then the existing `# ---- build: resolve and install locked dependencies ...` stage and everything after it stays. In the runtime stage, directly after `COPY --from=builder /app/.venv /app/.venv` add:

```dockerfile
COPY --from=frontend /frontend/dist /app/frontend
```
and add one line to the `ENV` block of the runtime stage:

```dockerfile
    BUNSHO_PATHS__FRONTEND_DIR=/app/frontend \
```
(placed before `BUNSHO_PATHS__DATA_DIR=/data \`, keep the backslash continuations valid). Add `frontend/coverage` to `.dockerignore` (next to `frontend/dist`).

- [ ] **Step 2: Add the `frontend` CI job and update the header comment**

In `.github/workflows/ci.yml` change the comment line `# Frontend checks (tsc -b, eslint, vitest) arrive with Plan 2.` to `# The frontend job runs Prettier, ESLint, the type-check/build and vitest with coverage.` and add this job after the `lint` job:

```yaml
  frontend:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v7

      - name: Set up Node
        # Pinned by commit (the release tag is in the comment).
        uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0
        with:
          node-version: "24"
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        run: npm ci

      - name: Prettier
        run: npm run format:check

      - name: ESLint
        run: npm run lint

      - name: API types are up to date
        run: |
          npm run gen:api
          git diff --exit-code -- src/api/schema.d.ts

      - name: Type-check and build
        run: npm run build

      - name: Tests with coverage
        run: npm run coverage
```

- [ ] **Step 3: Add the Dependabot `npm` entry**

In `.github/dependabot.yml` remove the `#   - "npm" for /frontend        (Plan 2: React + Vite)` line from the header comment (leave the rest of the comment coherent) and add this entry after the `uv` one:

```yaml
  - package-ecosystem: "npm"
    directory: "/frontend"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
    cooldown:
      default-days: 7
    commit-message:
      prefix: "chore(deps)"
    groups:
      frontend-minor-patch:
        update-types: ["minor", "patch"]
```

- [ ] **Step 4: Extend the smoke test**

In `scripts/smoke_test.py`: add `import re` to the standard-library imports, add the constant after `BASE = ...`:

```python
ORIGIN = f"http://127.0.0.1:{PORT}"
```
add these two functions after `request()`:

```python
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
```
In `run()`, call it right after `wait_healthy()` (before `expect_health("degraded")`):

```python
    log("checking that the container serves the web UI")
    expect_frontend_served()
```
Update the module docstring's first sentence to "(build, start, serve the UI, log in, build content, review a card, restart)".

- [ ] **Step 5: Verify locally**

```bash
unset VIRTUAL_ENV
uv run ruff format . && uv run ruff check . && uv run python -c "import ast; ast.parse(open('scripts/smoke_test.py', encoding='utf-8').read())"
docker build -t bunsho:frontend-check . 
uv run python scripts/smoke_test.py
```
Expected: the image builds (the Node stage runs `npm ci` and `npm run build`), and the smoke test ends `[smoke] PASS` (about 2 to 3 minutes; it needs the real deck and Docker). Record the image size change (the UI adds roughly 1 MB). If Docker is unavailable, say so: CI runs it.

- [ ] **Step 6: Commit**

```bash
git add Dockerfile .dockerignore .github/workflows/ci.yml .github/dependabot.yml scripts/smoke_test.py
git commit -m "feat: build the UI in Docker, add a frontend CI job, Dependabot npm and smoke checks" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
Then push; the draft PR's CI must show the new `frontend` job green.

## Task 5: API layer: session, errors, HTTP client, endpoints

**Files (all under `frontend/src/`):**
- Create: `auth/session.ts`, `api/errors.ts`, `api/http.ts`, `api/client.ts`, `api/endpoints.ts`, `queryClient.ts`
- Test: `auth/session.test.ts`, `api/errors.test.ts`, `api/client.test.ts`, `api/endpoints.test.ts`, `queryClient.test.ts`

**Interfaces:**
- Consumes: `src/api/schema.d.ts` (generated), `src/test/server.ts` (the MSW server), `ofetch`.
- Produces:
  - `session` (`auth/session.ts`): `getRefreshToken()`, `getAccessToken(now?)` (null when missing or within 30 s of expiry), `setTokens({access_token, refresh_token, expires_in})`, `clear()`, `expire()` (clears and notifies), `onExpired(listener) -> unsubscribe`; `REFRESH_TOKEN_KEY = 'bunsho.refresh_token'`.
  - `ApiError(status, detail, fieldErrors?, retryAfterSeconds?)`, `NetworkError`, `toClientError(error)`, `messageFor(error) -> string` (`api/errors.ts`).
  - `apiUrl(path)`, `wsUrl(path)`, `RequestOptions`, `rawRequest<T>(path, options?)` (`api/http.ts`): absolute URLs, no auth, no retries, errors normalized.
  - `refreshSession()` (single-flight; a 401 from the server calls `session.expire()`), `ensureAccessToken()`, `request<T>(path, options?)` (bearer token, one refresh + one retry on a 401) (`api/client.ts`).
  - `endpoints` (`contentSummary`, `configCheck`, `startBuild(dryRun)`, `latestBuild()` (null on 404), `getBuild(taskId)`) and the types `ContentSummary`, `ConfigCheck`, `BuildStatus` (`api/endpoints.ts`).
  - `shouldRetry(failureCount, error)`, `createQueryClient()` (`queryClient.ts`).

- [ ] **Step 1: Write the tests (verified files)**

Create `frontend/src/auth/session.test.ts`:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { session } from './session';

const PAIR = { access_token: 'access-1', refresh_token: 'refresh-1', expires_in: 900 };

describe('session', () => {
  beforeEach(() => {
    session.clear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('remembers the refresh token in localStorage and the access token in memory', () => {
    session.setTokens(PAIR, 1_000);
    expect(session.getRefreshToken()).toBe('refresh-1');
    expect(window.localStorage.getItem('bunsho.refresh_token')).toBe('refresh-1');
    expect(session.getAccessToken(1_000)).toBe('access-1');
    // The access token itself never reaches storage.
    expect(JSON.stringify({ ...window.localStorage })).not.toContain('access-1');
  });

  it('treats an access token as expired 30 seconds early', () => {
    session.setTokens(PAIR, 0);
    expect(session.getAccessToken(869_000)).toBe('access-1');
    expect(session.getAccessToken(870_000)).toBeNull();
  });

  it('clear forgets both tokens without notifying', () => {
    const listener = vi.fn();
    session.onExpired(listener);
    session.setTokens(PAIR);
    session.clear();
    expect(session.getRefreshToken()).toBeNull();
    expect(session.getAccessToken()).toBeNull();
    expect(listener).not.toHaveBeenCalled();
  });

  it('expire forgets both tokens and notifies every listener once', () => {
    const first = vi.fn();
    const second = vi.fn();
    const stopFirst = session.onExpired(first);
    session.onExpired(second);
    session.setTokens(PAIR);
    session.expire();
    expect(session.getRefreshToken()).toBeNull();
    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(1);
    stopFirst();
    session.expire();
    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(2);
  });

  it('keeps working when storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(() => {
      session.setTokens(PAIR, 0);
    }).not.toThrow();
    expect(session.getRefreshToken()).toBeNull(); // not remembered
    expect(session.getAccessToken(0)).toBe('access-1'); // but this tab still works
    expect(() => {
      session.clear();
    }).not.toThrow();
  });
});
```

Create `frontend/src/api/errors.test.ts`:

```ts
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { server } from '../test/server';
import { ApiError, messageFor, NetworkError } from './errors';
import { rawRequest } from './http';

describe('error normalization', () => {
  it('maps an HTTP error to an ApiError with a string detail', async () => {
    server.use(http.get('/api/v1/x', () => HttpResponse.json({ detail: 'Nope' }, { status: 404 })));
    await expect(rawRequest('/x')).rejects.toMatchObject({
      name: 'ApiError',
      status: 404,
      detail: 'Nope',
    });
  });

  it('maps a 422 list to per-field messages (first message per field)', async () => {
    server.use(
      http.post('/api/v1/x', () =>
        HttpResponse.json(
          {
            detail: [
              { loc: ['body', 'username'], msg: 'Field required', type: 'missing' },
              { loc: ['body', 'username'], msg: 'Second message', type: 'x' },
              { loc: ['body', 'password'], msg: 'Too short', type: 'string_too_short' },
            ],
          },
          { status: 422 },
        ),
      ),
    );
    const error = (await rawRequest('/x', { method: 'POST', body: {} }).catch(
      (caught: unknown) => caught,
    )) as ApiError;
    expect(error.status).toBe(422);
    expect(error.fieldErrors).toEqual({ username: 'Field required', password: 'Too short' });
  });

  it('reads Retry-After from a 429', async () => {
    server.use(
      http.post('/api/v1/x', () =>
        HttpResponse.json(
          { detail: 'slow down' },
          { status: 429, headers: { 'Retry-After': '7' } },
        ),
      ),
    );
    await expect(rawRequest('/x', { method: 'POST', body: {} })).rejects.toMatchObject({
      status: 429,
      retryAfterSeconds: 7,
    });
  });

  it('maps a connection failure to a NetworkError', async () => {
    server.use(http.get('/api/v1/x', () => HttpResponse.error()));
    await expect(rawRequest('/x')).rejects.toBeInstanceOf(NetworkError);
  });

  it('does not retry on its own', async () => {
    let calls = 0;
    server.use(
      http.get('/api/v1/x', () => {
        calls += 1;
        return HttpResponse.json({ detail: 'busy' }, { status: 503 });
      }),
    );
    await expect(rawRequest('/x')).rejects.toBeInstanceOf(ApiError);
    expect(calls).toBe(1);
  });
});

describe('messageFor', () => {
  it('never shows raw status codes', () => {
    const cases: [unknown, RegExp][] = [
      [new NetworkError(), /can't reach the server/i],
      [new ApiError(401, 'x'), /session has expired/i],
      [new ApiError(409, 'A build is already running'), /already running/i],
      [new ApiError(422, 'x'), /invalid/i],
      [new ApiError(429, 'x', {}, 7), /7 seconds/],
      [new ApiError(429, 'x'), /wait a moment/i],
      [new ApiError(503, 'x'), /isn't built yet/i],
      [new ApiError(500, 'boom'), /server had a problem/i],
      [new ApiError(404, 'Not found'), /not found/i],
      [new Error('weird'), /something went wrong/i],
    ];
    for (const [error, pattern] of cases) {
      const message = messageFor(error);
      expect(message).toMatch(pattern);
      expect(message).not.toMatch(/\b(401|409|422|429|500|503)\b/);
    }
  });
});
```

Create `frontend/src/api/client.test.ts`:

```ts
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { session } from '../auth/session';
import { server } from '../test/server';
import { ensureAccessToken, refreshSession, request } from './client';
import { ApiError, NetworkError } from './errors';

const SUMMARY = '/api/v1/content/summary';
const REFRESH = '/api/v1/auth/refresh';

function pair(n: number) {
  return {
    access_token: `access-${String(n)}`,
    refresh_token: `refresh-${String(n)}`,
    expires_in: 900,
  };
}

function refreshHandler(counter: { calls: number }) {
  return http.post(REFRESH, async ({ request: incoming }) => {
    counter.calls += 1;
    const body = (await incoming.json()) as { refresh_token: string };
    return body.refresh_token === 'refresh-1'
      ? HttpResponse.json({ ...pair(2), token_type: 'bearer' })
      : HttpResponse.json({ detail: 'Invalid or expired refresh token' }, { status: 401 });
  });
}

describe('request', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens(pair(1));
  });

  it('attaches the bearer token', async () => {
    let seen: string | null = null;
    server.use(
      http.get(SUMMARY, ({ request: incoming }) => {
        seen = incoming.headers.get('Authorization');
        return HttpResponse.json({ ok: true });
      }),
    );
    await expect(request('/content/summary')).resolves.toEqual({ ok: true });
    expect(seen).toBe('Bearer access-1');
  });

  it('on a 401 refreshes the session once and retries the call once', async () => {
    const refresh = { calls: 0 };
    server.use(
      refreshHandler(refresh),
      http.get(SUMMARY, ({ request: incoming }) =>
        incoming.headers.get('Authorization') === 'Bearer access-2'
          ? HttpResponse.json({ ok: true })
          : HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 }),
      ),
    );
    await expect(request('/content/summary')).resolves.toEqual({ ok: true });
    expect(refresh.calls).toBe(1);
    expect(session.getRefreshToken()).toBe('refresh-2');
  });

  it('shares one refresh between concurrent calls that all get a 401', async () => {
    const refresh = { calls: 0 };
    server.use(
      refreshHandler(refresh),
      http.get(SUMMARY, ({ request: incoming }) =>
        incoming.headers.get('Authorization') === 'Bearer access-2'
          ? HttpResponse.json({ ok: true })
          : HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 }),
      ),
    );
    const results = await Promise.all([
      request('/content/summary'),
      request('/content/summary'),
      request('/content/summary'),
    ]);
    expect(results).toHaveLength(3);
    expect(refresh.calls).toBe(1);
  });

  it('refreshes first when the access token is about to expire', async () => {
    session.setTokens({ ...pair(1), expires_in: 10 });
    const refresh = { calls: 0 };
    server.use(
      refreshHandler(refresh),
      http.get(SUMMARY, () => HttpResponse.json({ ok: true })),
    );
    await request('/content/summary');
    expect(refresh.calls).toBe(1);
  });

  it('ends the session when the refresh token is rejected', async () => {
    const expired = vi.fn();
    session.onExpired(expired);
    session.setTokens({ ...pair(9) }); // refresh-9 is unknown to the server
    server.use(
      refreshHandler({ calls: 0 }),
      http.get(SUMMARY, () => HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })),
    );
    await expect(request('/content/summary')).rejects.toMatchObject({ status: 401 });
    expect(expired).toHaveBeenCalledTimes(1);
    expect(session.getRefreshToken()).toBeNull();
  });

  it('does not end the session when the server cannot be reached during a refresh', async () => {
    const expired = vi.fn();
    session.onExpired(expired);
    session.setTokens({ ...pair(1), expires_in: 10 });
    server.use(http.post(REFRESH, () => HttpResponse.error()));
    await expect(request('/content/summary')).rejects.toBeInstanceOf(NetworkError);
    expect(expired).not.toHaveBeenCalled();
    expect(session.getRefreshToken()).toBe('refresh-1');
  });

  it('does not retry errors other than 401', async () => {
    let calls = 0;
    server.use(
      http.get(SUMMARY, () => {
        calls += 1;
        return HttpResponse.json({ detail: 'busy' }, { status: 503 });
      }),
    );
    await expect(request('/content/summary')).rejects.toBeInstanceOf(ApiError);
    expect(calls).toBe(1);
  });

  it('gives up after one retry when the retried call is rejected again', async () => {
    let calls = 0;
    server.use(
      refreshHandler({ calls: 0 }),
      http.get(SUMMARY, () => {
        calls += 1;
        return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 });
      }),
    );
    await expect(request('/content/summary')).rejects.toMatchObject({ status: 401 });
    expect(calls).toBe(2);
  });
});

describe('sessions without a refresh token', () => {
  beforeEach(() => {
    session.clear();
  });

  it('cannot refresh: the session is reported expired', async () => {
    const expired = vi.fn();
    session.onExpired(expired);
    await expect(refreshSession()).rejects.toMatchObject({ status: 401 });
    expect(expired).toHaveBeenCalledTimes(1);
  });

  it('ensureAccessToken returns a fresh token without calling the server', async () => {
    session.setTokens(pair(1));
    await expect(ensureAccessToken()).resolves.toBe('access-1');
  });
});
```

Create `frontend/src/api/endpoints.test.ts`:

```ts
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { session } from '../auth/session';
import { server } from '../test/server';
import { endpoints } from './endpoints';

const TASK = {
  task_id: 'abc 123',
  state: 'running',
  dry_run: false,
  started_at: '2026-09-20T12:00:00Z',
  finished_at: null,
  progress: { stage: 'import_deck', current: 0, total: 1 },
  report: null,
  error: null,
};

describe('endpoints', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  it('reads the content summary and the environment checks', async () => {
    server.use(
      http.get('/api/v1/content/summary', () => HttpResponse.json({ built: false })),
      http.get('/api/v1/admin/config-check', () => HttpResponse.json({ ok: true, checks: [] })),
    );
    await expect(endpoints.contentSummary()).resolves.toEqual({ built: false });
    await expect(endpoints.configCheck()).resolves.toEqual({ ok: true, checks: [] });
  });

  it('starts a build with the dry-run flag in the body', async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post('/api/v1/admin/content/build', async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(TASK, { status: 202 });
      }),
    );
    await endpoints.startBuild(true);
    await endpoints.startBuild(false);
    expect(bodies).toEqual([{ dry_run: true }, { dry_run: false }]);
  });

  it('treats "no build yet" (404) as null and passes other errors on', async () => {
    server.use(
      http.get('/api/v1/admin/content/build', () =>
        HttpResponse.json({ detail: 'no build has run yet' }, { status: 404 }),
      ),
    );
    await expect(endpoints.latestBuild()).resolves.toBeNull();

    server.use(
      http.get('/api/v1/admin/content/build', () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    );
    await expect(endpoints.latestBuild()).rejects.toMatchObject({ status: 500 });
  });

  it('reads the latest build and a build by id (the id is URL-encoded)', async () => {
    let requestedPath = '';
    server.use(
      http.get('/api/v1/admin/content/build', () => HttpResponse.json(TASK)),
      http.get('/api/v1/admin/content/build/:id', ({ request }) => {
        requestedPath = new URL(request.url).pathname;
        return HttpResponse.json(TASK);
      }),
    );
    await expect(endpoints.latestBuild()).resolves.toMatchObject({ task_id: 'abc 123' });
    await endpoints.getBuild('abc 123');
    expect(requestedPath).toBe('/api/v1/admin/content/build/abc%20123');
  });
});
```

Create `frontend/src/queryClient.test.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { ApiError, NetworkError } from './api/errors';
import { createQueryClient, shouldRetry } from './queryClient';

describe('shouldRetry', () => {
  it('retries connection failures and server errors, twice at most', () => {
    expect(shouldRetry(0, new NetworkError())).toBe(true);
    expect(shouldRetry(1, new ApiError(503, 'busy'))).toBe(true);
    expect(shouldRetry(2, new NetworkError())).toBe(false);
  });

  it('never retries client errors or unknown errors', () => {
    expect(shouldRetry(0, new ApiError(401, 'no'))).toBe(false);
    expect(shouldRetry(0, new ApiError(404, 'no'))).toBe(false);
    expect(shouldRetry(0, new ApiError(422, 'no'))).toBe(false);
    expect(shouldRetry(0, new Error('bug'))).toBe(false);
  });
});

describe('createQueryClient', () => {
  it('uses the retry policy for queries and never retries mutations', () => {
    const defaults = createQueryClient().getDefaultOptions();
    expect(defaults.queries?.retry).toBe(shouldRetry);
    expect(defaults.mutations?.retry).toBe(false);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`): `npm test`
Expected: FAIL: the test files cannot import `./session`, `./errors`, `./client`, `./endpoints`, `./queryClient` (modules not found).

- [ ] **Step 3: Implement (verified files)**

Create `frontend/src/auth/session.ts`:

```ts
/**
 * The login session: the refresh token is remembered in localStorage, the short-lived access
 * token only in memory. Nothing here ever logs or exposes a token outside this module's API.
 */

export const REFRESH_TOKEN_KEY = 'bunsho.refresh_token';
/** Treat an access token as expired this long before it really is, so requests never race it. */
const EXPIRY_MARGIN_MS = 30_000;

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

let accessToken: string | null = null;
let accessExpiresAt = 0;
const expiredListeners = new Set<() => void>();

function readStoredRefreshToken(): string | null {
  try {
    return window.localStorage.getItem(REFRESH_TOKEN_KEY);
  } catch {
    return null; // storage blocked (private mode, policy): the session is simply not remembered
  }
}

function writeStoredRefreshToken(value: string | null): void {
  try {
    if (value === null) {
      window.localStorage.removeItem(REFRESH_TOKEN_KEY);
    } else {
      window.localStorage.setItem(REFRESH_TOKEN_KEY, value);
    }
  } catch {
    // storage blocked: keep going with the in-memory access token only
  }
}

export const session = {
  /** The remembered refresh token, or null when there is none (or storage is blocked). */
  getRefreshToken: readStoredRefreshToken,

  /** The access token, or null when missing or about to expire. */
  getAccessToken(now: number = Date.now()): string | null {
    return accessToken !== null && now < accessExpiresAt - EXPIRY_MARGIN_MS ? accessToken : null;
  },

  /** Store a fresh token pair (after login or refresh). */
  setTokens(pair: TokenPair, now: number = Date.now()): void {
    accessToken = pair.access_token;
    accessExpiresAt = now + pair.expires_in * 1000;
    writeStoredRefreshToken(pair.refresh_token);
  },

  /** Forget everything (logout). Does not notify. */
  clear(): void {
    accessToken = null;
    accessExpiresAt = 0;
    writeStoredRefreshToken(null);
  },

  /** The server rejected the refresh token: forget everything and tell the listeners. */
  expire(): void {
    this.clear();
    for (const listener of [...expiredListeners]) {
      listener();
    }
  },

  /** Be told when the session expired. Returns an unsubscribe function. */
  onExpired(listener: () => void): () => void {
    expiredListeners.add(listener);
    return () => {
      expiredListeners.delete(listener);
    };
  },
};
```

Create `frontend/src/api/errors.ts`:

```ts
import { FetchError } from 'ofetch';

/** An HTTP error answered by the API. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  /** For 422 responses: the first message per field name. */
  readonly fieldErrors: Readonly<Record<string, string>>;
  /** For 429 responses: seconds to wait, from the Retry-After header. */
  readonly retryAfterSeconds: number | null;

  constructor(
    status: number,
    detail: string,
    fieldErrors: Record<string, string> = {},
    retryAfterSeconds: number | null = null,
  ) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.fieldErrors = fieldErrors;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

/** The server could not be reached at all (offline, restarting, DNS...). */
export class NetworkError extends Error {
  constructor() {
    super("Can't reach the server");
    this.name = 'NetworkError';
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function fieldErrorsOf(detail: unknown[]): Record<string, string> {
  const result: Record<string, string> = {};
  for (const item of detail) {
    if (!isRecord(item) || !Array.isArray(item.loc) || typeof item.msg !== 'string') continue;
    const location: unknown[] = item.loc;
    const name = location.at(-1);
    if (typeof name === 'string' && !(name in result)) result[name] = item.msg;
  }
  return result;
}

/** Turn an ofetch failure into an ApiError or NetworkError; leave every other error alone. */
export function toClientError(error: unknown): unknown {
  if (!(error instanceof FetchError)) return error;
  if (error.response === undefined) return new NetworkError();
  const data: unknown = error.data;
  const body = isRecord(data) ? data.detail : undefined;
  const retryAfter = Number.parseInt(error.response.headers.get('Retry-After') ?? '', 10);
  return new ApiError(
    error.response.status,
    typeof body === 'string' ? body : 'Request failed',
    Array.isArray(body) ? fieldErrorsOf(body) : {},
    Number.isNaN(retryAfter) ? null : retryAfter,
  );
}

/** A message for the user: never a raw status code or stack. */
export function messageFor(error: unknown): string {
  if (error instanceof NetworkError) {
    return "Can't reach the server. Check that Bunshō is running, then try again.";
  }
  if (error instanceof ApiError) {
    switch (error.status) {
      case 401:
        return 'Your session has expired. Please log in again.';
      case 409:
        return error.detail;
      case 422:
        return 'Some fields are invalid.';
      case 429:
        return error.retryAfterSeconds === null
          ? 'Too many attempts. Please wait a moment and try again.'
          : `Too many attempts. Please wait ${String(error.retryAfterSeconds)} seconds and try again.`;
      case 503:
        return "Content isn't built yet.";
      default:
        return error.status >= 500
          ? 'The server had a problem. Please try again in a moment.'
          : error.detail;
    }
  }
  return 'Something went wrong. Please try again.';
}
```

Create `frontend/src/api/http.ts`:

```ts
import { ofetch } from 'ofetch';

import { toClientError } from './errors';

/** Absolute URL of an API path. Node's fetch (used by the tests) cannot resolve relative URLs. */
export function apiUrl(path: string): string {
  return new URL(`/api/v1${path}`, window.location.origin).toString();
}

/** Absolute ws:// or wss:// URL of an API WebSocket path. */
export function wsUrl(path: string): string {
  const url = new URL(`/api/v1${path}`, window.location.origin);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT';
  body?: Record<string, unknown>;
  headers?: Record<string, string>;
}

/** One HTTP call with JSON in and out. No authentication and no retries; errors are normalized. */
export async function rawRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  try {
    return await ofetch<T>(apiUrl(path), { ...options, retry: 0 });
  } catch (error) {
    throw toClientError(error);
  }
}
```

Create `frontend/src/api/client.ts`:

```ts
import { session } from '../auth/session';
import { ApiError } from './errors';
import { rawRequest, type RequestOptions } from './http';
import type { components } from './schema';

type TokenResponse = components['schemas']['TokenResponse'];

let refreshInFlight: Promise<void> | null = null;

async function refreshOnce(): Promise<void> {
  const refreshToken = session.getRefreshToken();
  if (refreshToken === null) {
    session.expire();
    throw new ApiError(401, 'Not signed in');
  }
  try {
    const pair = await rawRequest<TokenResponse>('/auth/refresh', {
      method: 'POST',
      body: { refresh_token: refreshToken },
    });
    session.setTokens(pair);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) session.expire();
    throw error;
  }
}

/**
 * Exchange the refresh token for a new pair. Concurrent callers share one request. A 401 from the
 * server ends the session (listeners of `session.onExpired` are told); other errors propagate and
 * leave the session untouched, so a server restart never logs anybody out.
 */
export function refreshSession(): Promise<void> {
  refreshInFlight ??= refreshOnce().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

/** A usable access token, refreshing first when there is none or it is about to expire. */
export async function ensureAccessToken(): Promise<string> {
  const current = session.getAccessToken();
  if (current !== null) return current;
  await refreshSession();
  const refreshed = session.getAccessToken();
  if (refreshed === null) throw new ApiError(401, 'Not signed in');
  return refreshed;
}

/**
 * An authenticated API call: attaches the bearer token and, when the server answers 401,
 * refreshes the session once and retries the call once.
 */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const send = async (): Promise<T> =>
    rawRequest<T>(path, {
      ...options,
      headers: { ...options.headers, Authorization: `Bearer ${await ensureAccessToken()}` },
    });
  try {
    return await send();
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      await refreshSession();
      return send();
    }
    throw error;
  }
}
```

Create `frontend/src/api/endpoints.ts`:

```ts
import { request } from './client';
import { ApiError } from './errors';
import type { components } from './schema';

type Schemas = components['schemas'];

export type ContentSummary = Schemas['ContentSummaryResponse'];
export type ConfigCheck = Schemas['ConfigCheckResponse'];
export type BuildStatus = Schemas['BuildStatusResponse'];

/** Every authenticated API call the screens make, typed from the generated schema. */
export const endpoints = {
  contentSummary: () => request<ContentSummary>('/content/summary'),

  configCheck: () => request<ConfigCheck>('/admin/config-check'),

  startBuild: (dryRun: boolean) =>
    request<BuildStatus>('/admin/content/build', { method: 'POST', body: { dry_run: dryRun } }),

  /** The most recent build, or null when none has run yet (the server answers 404). */
  latestBuild: async (): Promise<BuildStatus | null> => {
    try {
      return await request<BuildStatus>('/admin/content/build');
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  },

  getBuild: (taskId: string) =>
    request<BuildStatus>(`/admin/content/build/${encodeURIComponent(taskId)}`),
};
```

Create `frontend/src/queryClient.ts`:

```ts
import { QueryClient } from '@tanstack/react-query';

import { ApiError, NetworkError } from './api/errors';

const MAX_RETRIES = 2;

/** Retry only what can succeed later: connection failures and server errors, never a 4xx. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (failureCount >= MAX_RETRIES) return false;
  return error instanceof NetworkError || (error instanceof ApiError && error.status >= 500);
}

/** The application's query client (tests use `createTestQueryClient`, which never retries). */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: shouldRetry, staleTime: 30_000 },
      mutations: { retry: false },
    },
  });
}
```

- [ ] **Step 4: Run the gate**

```bash
npm run format && npm run format:check && npm run lint && npm run build && npm run coverage
```
Expected: everything passes (about 35 tests so far); coverage above the 80% gate. `errors.ts`'s `toClientError` branches and `client.ts`'s refresh paths are exercised by the tests: if a coverage gap appears there, add a test rather than lowering the gate.

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/src
git commit -m "feat: authenticated API client with single-flight token refresh" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 6: Authentication UI: provider, route guard, login page

**Files (all under `frontend/src/`):**
- Create: `auth/authContext.ts`, `auth/AuthProvider.tsx`, `auth/RequireAuth.tsx`, `hooks/useCountdown.ts`, `features/login/LoginPage.tsx`
- Test: `auth/AuthProvider.test.tsx`, `hooks/useCountdown.test.ts`, `features/login/LoginPage.test.tsx`

**Interfaces:**
- Consumes: Task 5 (`session`, `refreshSession`, `rawRequest`, `ApiError`, `messageFor`, `NetworkError`), Task 3 (`renderWithProviders`, `server`).
- Produces:
  - `AuthContext`, `useAuth() -> { status: 'checking'|'authenticated'|'anonymous'|'unreachable', sessionExpired: boolean, login(username, password), logout(), retry() }` (`auth/authContext.ts`).
  - `<AuthProvider>` (needs a `QueryClientProvider` above it): restores a remembered login on start (only a 401 means "logged out": a network error or 5xx gives `unreachable` and keeps the token), follows `session.onExpired`, follows a logout in another tab (`storage` event), clears the query cache on logout.
  - `<RequireAuth>`: `<Outlet />` when authenticated, a spinner while checking, a retry screen when unreachable, otherwise `<Navigate to="/login" state={{from}} />`.
  - `useSecondsUntil(deadline)`, `useCountdown() -> { remaining, start(seconds) }`.
  - `<LoginPage>` (`/login`): validation, 401 and 429 handling (countdown from `Retry-After`), "session expired" notice, redirect back to the page the visitor wanted.

- [ ] **Step 1: Write the tests (verified files)**

Create `frontend/src/auth/AuthProvider.test.tsx`:

```tsx
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { server } from '../test/server';
import { renderWithProviders } from '../test/render';
import { AuthProvider } from './AuthProvider';
import { useAuth } from './authContext';
import { REFRESH_TOKEN_KEY, session } from './session';

function Probe() {
  const { status, sessionExpired, logout, retry } = useAuth();
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="expired">{String(sessionExpired)}</span>
      <button onClick={logout}>logout</button>
      <button onClick={retry}>retry</button>
    </div>
  );
}

function renderProbe() {
  return renderWithProviders(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );
}

const TOKENS = { access_token: 'a2', refresh_token: 'r2', token_type: 'bearer', expires_in: 900 };

describe('AuthProvider bootstrap', () => {
  beforeEach(() => {
    session.clear();
  });

  it('is anonymous without a remembered login', async () => {
    renderProbe();
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('anonymous');
    });
    expect(screen.getByTestId('expired')).toHaveTextContent('false');
  });

  it('logs in again from the remembered refresh token', async () => {
    window.localStorage.setItem(REFRESH_TOKEN_KEY, 'r1');
    server.use(http.post('/api/v1/auth/refresh', () => HttpResponse.json(TOKENS)));
    renderProbe();
    expect(screen.getByTestId('status')).toHaveTextContent('checking');
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated');
    });
    expect(session.getRefreshToken()).toBe('r2');
  });

  it('is anonymous, and tells the user, when the server rejects the remembered login', async () => {
    window.localStorage.setItem(REFRESH_TOKEN_KEY, 'stale');
    server.use(
      http.post('/api/v1/auth/refresh', () =>
        HttpResponse.json({ detail: 'Invalid or expired refresh token' }, { status: 401 }),
      ),
    );
    renderProbe();
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('anonymous');
    });
    expect(screen.getByTestId('expired')).toHaveTextContent('true');
    expect(session.getRefreshToken()).toBeNull();
  });

  it('keeps the remembered login when the server cannot be reached, and retries', async () => {
    window.localStorage.setItem(REFRESH_TOKEN_KEY, 'r1');
    server.use(http.post('/api/v1/auth/refresh', () => HttpResponse.error()));
    renderProbe();
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('unreachable');
    });
    expect(session.getRefreshToken()).toBe('r1');

    server.use(http.post('/api/v1/auth/refresh', () => HttpResponse.json(TOKENS)));
    await userEvent.click(screen.getByRole('button', { name: 'retry' }));
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated');
    });
  });
});

describe('AuthProvider sessions', () => {
  beforeEach(() => {
    session.clear();
    window.localStorage.setItem(REFRESH_TOKEN_KEY, 'r1');
    server.use(http.post('/api/v1/auth/refresh', () => HttpResponse.json(TOKENS)));
  });

  it('logout forgets the tokens and clears the query cache', async () => {
    const { queryClient } = renderProbe();
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated');
    });
    queryClient.setQueryData(['content', 'summary'], { built: true });
    await userEvent.click(screen.getByRole('button', { name: 'logout' }));
    expect(screen.getByTestId('status')).toHaveTextContent('anonymous');
    expect(session.getRefreshToken()).toBeNull();
    expect(queryClient.getQueryData(['content', 'summary'])).toBeUndefined();
  });

  it('follows another tab that logged out', async () => {
    renderProbe();
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated');
    });
    window.dispatchEvent(new StorageEvent('storage', { key: REFRESH_TOKEN_KEY, newValue: null }));
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('anonymous');
    });
  });

  it('becomes anonymous when the session expires while in use', async () => {
    renderProbe();
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated');
    });
    session.expire();
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('anonymous');
    });
    expect(screen.getByTestId('expired')).toHaveTextContent('true');
  });
});
```

Create `frontend/src/hooks/useCountdown.test.ts`:

```ts
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useCountdown, useSecondsUntil } from './useCountdown';

describe('useCountdown', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(0);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('is idle until started, then counts whole seconds down to zero', () => {
    const { result } = renderHook(() => useCountdown());
    expect(result.current.remaining).toBe(0);
    act(() => {
      result.current.start(3);
    });
    expect(result.current.remaining).toBe(3);
    act(() => {
      vi.advanceTimersByTime(1_000);
    });
    expect(result.current.remaining).toBe(2);
    act(() => {
      vi.advanceTimersByTime(5_000);
    });
    expect(result.current.remaining).toBe(0);
  });

  it('can be restarted', () => {
    const { result } = renderHook(() => useCountdown());
    act(() => {
      result.current.start(2);
    });
    act(() => {
      vi.advanceTimersByTime(5_000);
    });
    expect(result.current.remaining).toBe(0);
    act(() => {
      result.current.start(10);
    });
    expect(result.current.remaining).toBe(10);
  });
});

describe('useSecondsUntil', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(0);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('is zero without a deadline and rounds partial seconds up', () => {
    expect(renderHook(() => useSecondsUntil(null)).result.current).toBe(0);
    const { result } = renderHook(() => useSecondsUntil(2_500));
    expect(result.current).toBe(3);
    act(() => {
      vi.advanceTimersByTime(1_000);
    });
    expect(result.current).toBe(2);
  });
});
```

Create `frontend/src/features/login/LoginPage.test.tsx`:

```tsx
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it } from 'vitest';

import { AuthProvider } from '../../auth/AuthProvider';
import { RequireAuth } from '../../auth/RequireAuth';
import { REFRESH_TOKEN_KEY, session } from '../../auth/session';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { LoginPage } from './LoginPage';

const TOKENS = { access_token: 'a1', refresh_token: 'r1', token_type: 'bearer', expires_in: 900 };

function renderApp(initialEntries: Parameters<typeof renderWithProviders>[1] = {}) {
  return renderWithProviders(
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth />}>
          <Route path="/" element={<p>Home page</p>} />
          <Route path="/build" element={<p>Build page</p>} />
        </Route>
      </Routes>
    </AuthProvider>,
    initialEntries,
  );
}

async function fillAndSubmit(username: string, password: string) {
  const user = userEvent.setup();
  if (username !== '') await user.type(screen.getByLabelText('Username'), username);
  if (password !== '') await user.type(screen.getByLabelText('Password'), password);
  await user.click(screen.getByRole('button', { name: 'Log in' }));
}

describe('LoginPage', () => {
  beforeEach(() => {
    session.clear();
  });

  it('sends anonymous visitors to the login page', async () => {
    renderApp();
    expect(await screen.findByLabelText('Username')).toBeInTheDocument();
  });

  it('asks for both fields before contacting the server', async () => {
    renderApp({ initialEntries: ['/login'] });
    await fillAndSubmit('', '');
    expect(await screen.findByText('Enter your username')).toBeInTheDocument();
    expect(screen.getByText('Enter your password')).toBeInTheDocument();
  });

  it('logs in and lands on the home page', async () => {
    let body: unknown = null;
    server.use(
      http.post('/api/v1/auth/login', async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(TOKENS);
      }),
    );
    renderApp({ initialEntries: ['/login'] });
    await fillAndSubmit(' james ', 'secret');
    expect(await screen.findByText('Home page')).toBeInTheDocument();
    expect(body).toEqual({ username: 'james', password: 'secret' });
    expect(session.getRefreshToken()).toBe('r1');
  });

  it('returns to the page the visitor was heading for', async () => {
    server.use(http.post('/api/v1/auth/login', () => HttpResponse.json(TOKENS)));
    renderApp({ initialEntries: ['/build'] });
    await fillAndSubmit('james', 'secret');
    expect(await screen.findByText('Build page')).toBeInTheDocument();
  });

  it('says so when the credentials are wrong', async () => {
    server.use(
      http.post('/api/v1/auth/login', () =>
        HttpResponse.json({ detail: 'Invalid credentials' }, { status: 401 }),
      ),
    );
    renderApp({ initialEntries: ['/login'] });
    await fillAndSubmit('james', 'wrong');
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid username or password.');
    expect(screen.queryByText('Home page')).not.toBeInTheDocument();
  });

  it('shows a countdown and disables the button while throttled', async () => {
    server.use(
      http.post('/api/v1/auth/login', () =>
        HttpResponse.json(
          { detail: 'Too many failed logins; try again later' },
          { status: 429, headers: { 'Retry-After': '42' } },
        ),
      ),
    );
    renderApp({ initialEntries: ['/login'] });
    await fillAndSubmit('james', 'secret');
    expect(await screen.findByRole('alert')).toHaveTextContent(/too many attempts.*42 s left/i);
    expect(screen.getByRole('button', { name: 'Log in' })).toBeDisabled();
  });

  it('explains an expired remembered login', async () => {
    window.localStorage.setItem(REFRESH_TOKEN_KEY, 'stale');
    server.use(
      http.post('/api/v1/auth/refresh', () =>
        HttpResponse.json({ detail: 'Invalid or expired refresh token' }, { status: 401 }),
      ),
    );
    renderApp();
    expect(await screen.findByText(/your session has expired/i)).toBeInTheDocument();
  });

  it('lets a user with a remembered login straight in', async () => {
    window.localStorage.setItem(REFRESH_TOKEN_KEY, 'r1');
    server.use(http.post('/api/v1/auth/refresh', () => HttpResponse.json(TOKENS)));
    renderApp();
    await waitFor(() => {
      expect(screen.getByText('Home page')).toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm test`
Expected: FAIL (modules not found).

- [ ] **Step 3: Implement (verified files)**

Create `frontend/src/auth/authContext.ts`:

```ts
import { createContext, useContext } from 'react';

export type AuthStatus = 'checking' | 'authenticated' | 'anonymous' | 'unreachable';

export interface AuthContextValue {
  status: AuthStatus;
  /** True after the server ended the session (or the remembered login had expired). */
  sessionExpired: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  /** Try again after "unreachable". */
  retry: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (value === null) throw new Error('useAuth must be used inside <AuthProvider>');
  return value;
}
```

Create `frontend/src/auth/AuthProvider.tsx`:

```tsx
import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';

import { refreshSession } from '../api/client';
import { ApiError } from '../api/errors';
import { rawRequest } from '../api/http';
import type { components } from '../api/schema';
import { AuthContext, type AuthContextValue, type AuthStatus } from './authContext';
import { REFRESH_TOKEN_KEY, session } from './session';

type TokenResponse = components['schemas']['TokenResponse'];

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<AuthStatus>(() =>
    session.getRefreshToken() === null ? 'anonymous' : 'checking',
  );
  const [sessionExpired, setSessionExpired] = useState(false);

  const restore = useCallback(async () => {
    try {
      await refreshSession();
      setStatus('authenticated');
    } catch (error) {
      // Only a rejected refresh token means "logged out". A network error or a 5xx keeps the
      // remembered login: a server restart must never log anybody out.
      setStatus(error instanceof ApiError && error.status === 401 ? 'anonymous' : 'unreachable');
    }
  }, []);

  useEffect(() => {
    if (session.getRefreshToken() !== null) {
      // A one-off synchronisation with the server on mount: restore the remembered login.
      // eslint-disable-next-line react-hooks/set-state-in-effect -- setState runs after an await
      void restore();
    }
  }, [restore]);

  useEffect(
    () =>
      session.onExpired(() => {
        queryClient.clear();
        setSessionExpired(true);
        setStatus('anonymous');
      }),
    [queryClient],
  );

  // Another tab logged out: this one follows.
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key === REFRESH_TOKEN_KEY && event.newValue === null) {
        session.clear();
        queryClient.clear();
        setStatus('anonymous');
      }
    };
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener('storage', onStorage);
    };
  }, [queryClient]);

  const login = useCallback(async (username: string, password: string) => {
    const pair = await rawRequest<TokenResponse>('/auth/login', {
      method: 'POST',
      body: { username, password },
    });
    session.setTokens(pair);
    setSessionExpired(false);
    setStatus('authenticated');
  }, []);

  const logout = useCallback(() => {
    session.clear();
    queryClient.clear();
    setSessionExpired(false);
    setStatus('anonymous');
  }, [queryClient]);

  const retry = useCallback(() => {
    setStatus('checking');
    void restore();
  }, [restore]);

  const value = useMemo<AuthContextValue>(
    () => ({ status, sessionExpired, login, logout, retry }),
    [status, sessionExpired, login, logout, retry],
  );
  return <AuthContext value={value}>{children}</AuthContext>;
}
```

Create `frontend/src/auth/RequireAuth.tsx`:

```tsx
import { Button, Center, Loader, Stack, Text } from '@mantine/core';
import { Navigate, Outlet, useLocation } from 'react-router';

import { messageFor, NetworkError } from '../api/errors';
import { useAuth } from './authContext';

/** Renders the nested routes for a logged-in user; everybody else waits, retries or logs in. */
export function RequireAuth() {
  const { status, retry } = useAuth();
  const location = useLocation();

  switch (status) {
    case 'checking':
      return (
        <Center h="100vh">
          <Loader aria-label="Checking your session" />
        </Center>
      );
    case 'unreachable':
      return (
        <Center h="100vh">
          <Stack align="center">
            <Text>{messageFor(new NetworkError())}</Text>
            <Button onClick={retry}>Try again</Button>
          </Stack>
        </Center>
      );
    case 'anonymous':
      return <Navigate to="/login" replace state={{ from: location.pathname }} />;
    case 'authenticated':
      return <Outlet />;
  }
}
```

Create `frontend/src/hooks/useCountdown.ts`:

```ts
import { useCallback, useState, useSyncExternalStore } from 'react';

/** Whole seconds left until `deadline` (a Date.now() timestamp); re-renders twice a second. */
export function useSecondsUntil(deadline: number | null): number {
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (deadline === null) return () => {};
      const timer = setInterval(onChange, 500);
      return () => {
        clearInterval(timer);
      };
    },
    [deadline],
  );
  return useSyncExternalStore(subscribe, () =>
    deadline === null ? 0 : Math.max(0, Math.ceil((deadline - Date.now()) / 1000)),
  );
}

/** A countdown started on demand: `remaining` is 0 until `start(seconds)` is called. */
export function useCountdown(): { remaining: number; start: (seconds: number) => void } {
  const [deadline, setDeadline] = useState<number | null>(null);
  const remaining = useSecondsUntil(deadline);
  const start = useCallback((seconds: number) => {
    setDeadline(Date.now() + seconds * 1000);
  }, []);
  return { remaining, start };
}
```

Create `frontend/src/features/login/LoginPage.tsx`:

```tsx
import {
  Alert,
  Button,
  Center,
  Paper,
  PasswordInput,
  Stack,
  TextInput,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useState } from 'react';
import { Navigate, useLocation } from 'react-router';

import { ApiError, messageFor } from '../../api/errors';
import { useAuth } from '../../auth/authContext';
import { useCountdown } from '../../hooks/useCountdown';

function returnPath(state: unknown): string {
  if (typeof state === 'object' && state !== null && 'from' in state) {
    const from = state.from;
    if (typeof from === 'string' && from.startsWith('/') && !from.startsWith('//')) return from;
  }
  return '/';
}

export function LoginPage() {
  const { status, sessionExpired, login } = useAuth();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { remaining, start } = useCountdown();
  const form = useForm({
    mode: 'uncontrolled',
    initialValues: { username: '', password: '' },
    validate: {
      username: (value) => (value.trim() === '' ? 'Enter your username' : null),
      password: (value) => (value === '' ? 'Enter your password' : null),
    },
  });

  if (status === 'authenticated') {
    return <Navigate to={returnPath(location.state)} replace />;
  }

  const submit = form.onSubmit(async (values) => {
    setError(null);
    setSubmitting(true);
    try {
      await login(values.username.trim(), values.password);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        setError('Invalid username or password.');
      } else {
        if (caught instanceof ApiError && caught.status === 429) {
          start(caught.retryAfterSeconds ?? 30);
        }
        setError(messageFor(caught));
      }
    } finally {
      setSubmitting(false);
    }
  });

  return (
    <Center mih="100vh" p="md">
      <Paper withBorder shadow="sm" p="xl" radius="md" w={380} maw="100%">
        <form
          onSubmit={(event) => {
            void submit(event);
          }}
          noValidate
        >
          <Stack>
            <Title order={2}>
              Bunshō <span lang="ja">文章</span>
            </Title>
            {sessionExpired && (
              <Alert color="yellow" title="Signed out">
                Your session has expired. Please log in again.
              </Alert>
            )}
            {error !== null && (
              <Alert color="red" role="alert">
                {remaining > 0 ? `${error} (${String(remaining)} s left)` : error}
              </Alert>
            )}
            <TextInput
              label="Username"
              autoComplete="username"
              data-autofocus
              key={form.key('username')}
              {...form.getInputProps('username')}
            />
            <PasswordInput
              label="Password"
              autoComplete="current-password"
              key={form.key('password')}
              {...form.getInputProps('password')}
            />
            <Button type="submit" loading={submitting} disabled={remaining > 0}>
              Log in
            </Button>
          </Stack>
        </form>
      </Paper>
    </Center>
  );
}
```

Notes for the implementer: the `eslint-disable-next-line react-hooks/set-state-in-effect` comment in `AuthProvider.tsx` is intentional (the rule cannot see that `setStatus` runs after an `await`); keep the explanation next to it. Do not add other suppressions.

- [ ] **Step 4: Run the gate**

```bash
npm run format && npm run format:check && npm run lint && npm run build && npm run coverage
```
Expected: everything passes (about 60 tests so far).

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/src
git commit -m "feat: authentication provider, route guard and login page" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 7: Real-time build stream: `BuildStream`, provider, badge, queries

**Files (all under `frontend/src/`):**
- Create: `realtime/backoff.ts`, `realtime/messages.ts`, `realtime/BuildStream.ts`, `realtime/applyMessage.ts`, `realtime/realtimeContext.ts`, `realtime/RealtimeProvider.tsx`, `realtime/ConnectionBadge.tsx`, `api/queries.ts`, `test/fakeSocket.ts`, `test/fixtures.ts`
- Test: `realtime/BuildStream.test.ts`, `realtime/applyMessage.test.ts`, `realtime/RealtimeProvider.test.tsx`, `api/queries.test.ts`

**Interfaces:**
- Consumes: Tasks 5 and 6 (`ensureAccessToken`, `refreshSession`, `wsUrl`, `endpoints`, `useSecondsUntil`).
- Produces:
  - `nextDelayMs(attempt, random?)`: 1 s doubling to a 30 s cap, full jitter, floor 250 ms.
  - `parseServerMessage(text) -> ServerMessage | null` and the types `ServerMessage` (`ready` | `snapshot` | `event`), `BuildStatus`, `BuildEvent`.
  - `BuildStream(options)` with `start()` / `stop()` and `ConnectionState` (`connecting` | `connected` | `retrying{retryAt}` | `disconnected`): sends `{type:'auth', token}` as the first message, reconnects with backoff, on close code 1008 refreshes the session and reconnects once, then gives up.
  - `applyMessage(queryClient, message)`: folds snapshots and events into the query cache.
  - `queryKeys`, `pollInterval(build, streamConnected)`, `BUILD_POLL_MS`, hooks `useContentSummary()`, `useConfigCheck()`, `useLatestBuild(streamConnected)`.
  - `<RealtimeProvider createSocket?>`, `useConnectionState()`, `RealtimeContext`, `<ConnectionBadge>`.
  - Test helpers: `FakeSocket` (scriptable socket: `open()`, `receive(payload)`, `serverClose(code)`, `sent`, `closed`), `makeBuildStatus()`, `makeReport()`.

- [ ] **Step 1: Write the tests and test helpers (verified files)**

Create `frontend/src/test/fakeSocket.ts`:

```ts
import type { SocketLike } from '../realtime/BuildStream';

/** A scriptable stand-in for the browser WebSocket. */
export class FakeSocket implements SocketLike {
  readonly url: string;
  readonly sent: string[] = [];
  closed = false;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(url: string) {
    this.url = url;
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    this.closed = true;
  }

  /** The connection was established (the client will send its auth message). */
  open(): void {
    this.onopen?.(new Event('open'));
  }

  /** The server sent a frame: an object is sent as JSON, a string as is. */
  receive(payload: unknown): void {
    const data = typeof payload === 'string' ? payload : JSON.stringify(payload);
    this.onmessage?.(new MessageEvent('message', { data }));
  }

  /** The server (or the network) closed the connection. */
  serverClose(code: number): void {
    this.onclose?.(new CloseEvent('close', { code }));
  }
}
```

Create `frontend/src/test/fixtures.ts`:

```ts
import type { BuildStatus } from '../api/endpoints';

export type BuildReport = NonNullable<BuildStatus['report']>;

export function makeBuildStatus(overrides: Partial<BuildStatus> = {}): BuildStatus {
  return {
    task_id: 'task-1',
    state: 'running',
    dry_run: false,
    started_at: '2026-09-20T12:00:00Z',
    finished_at: null,
    progress: { stage: 'import_deck', current: 0, total: 1 },
    report: null,
    error: null,
    ...overrides,
  };
}

export function makeReport(overrides: Partial<BuildReport> = {}): BuildReport {
  return {
    dry_run: false,
    target: '/data/content.db',
    deck_sha256: 'a'.repeat(64),
    kana_count: 208,
    kanji_count: 3088,
    unleveled_kanji_count: 979,
    vocab_count: 7734,
    sentence_count: 6775,
    vocab_by_level: { N5: 667, N4: 630, N3: 1647, N2: 1737, N1: 3053 },
    kanji_by_level: { N5: 480, N4: 352, N3: 544, N2: 357, N1: 376 },
    kanji_without_details: 12,
    duration_seconds: 31.4,
    ...overrides,
  };
}
```

Create `frontend/src/realtime/BuildStream.test.ts`:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { FakeSocket } from '../test/fakeSocket';
import { nextDelayMs } from './backoff';
import { BuildStream, type BuildStreamOptions, type ConnectionState } from './BuildStream';
import { parseServerMessage } from './messages';

const URL = 'ws://localhost/api/v1/ws/tasks';

function harness(overrides: Partial<BuildStreamOptions> = {}) {
  const sockets: FakeSocket[] = [];
  const states: ConnectionState[] = [];
  const messages: unknown[] = [];
  const refreshAuth = vi.fn(() => Promise.resolve(true));
  let tokenCalls = 0;
  const stream = new BuildStream({
    url: URL,
    getToken: () => {
      tokenCalls += 1;
      return Promise.resolve(`token-${String(tokenCalls)}`);
    },
    refreshAuth,
    onState: (state) => states.push(state),
    onMessage: (message) => messages.push(message),
    createSocket: (url) => {
      const socket = new FakeSocket(url);
      sockets.push(socket);
      return socket;
    },
    random: () => 1, // the longest jitter draw: delays equal the exponential ceiling
    ...overrides,
  });
  return { stream, sockets, states, messages, refreshAuth, tokenCalls: () => tokenCalls };
}

function last(sockets: FakeSocket[]): FakeSocket {
  const socket = sockets.at(-1);
  if (socket === undefined) throw new Error('no socket was created');
  return socket;
}

function lastState(states: ConnectionState[]): ConnectionState {
  const state = states.at(-1);
  if (state === undefined) throw new Error('no state was reported');
  return state;
}

const flush = () => vi.advanceTimersByTimeAsync(0);
const READY = { type: 'ready' };

describe('BuildStream', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(0);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('authenticates with its first message, then reports connected on ready', async () => {
    const { stream, sockets, states } = harness();
    stream.start();
    await flush();
    expect(lastState(states)).toEqual({ kind: 'connecting' });
    const socket = last(sockets);
    expect(socket.url).toBe(URL);
    expect(socket.sent).toEqual([]); // nothing is sent before the connection opens
    socket.open();
    expect(JSON.parse(socket.sent[0] ?? 'null')).toEqual({ type: 'auth', token: 'token-1' });
    socket.receive(READY);
    expect(lastState(states)).toEqual({ kind: 'connected' });
  });

  it('forwards snapshots and events and ignores anything else', async () => {
    const { stream, sockets, messages } = harness();
    stream.start();
    await flush();
    const socket = last(sockets);
    socket.open();
    socket.receive(READY);
    const task = { task_id: 't1', state: 'running' };
    const event = {
      kind: 'progress',
      task_id: 't1',
      state: 'running',
      progress: null,
      error: null,
    };
    socket.receive({ type: 'snapshot', task });
    socket.receive({ type: 'event', event });
    socket.receive('not json at all');
    socket.receive({ type: 'mystery' });
    socket.receive({ type: 'snapshot' }); // malformed: no task
    expect(messages).toEqual([
      { type: 'snapshot', task },
      { type: 'event', event },
    ]);
  });

  it('reconnects with exponentially growing delays and reports when it will retry', async () => {
    const { stream, sockets, states } = harness();
    stream.start();
    await flush();
    for (const delay of [1_000, 2_000, 4_000, 8_000]) {
      const before = Date.now();
      last(sockets).serverClose(1006);
      expect(lastState(states)).toEqual({ kind: 'retrying', retryAt: before + delay });
      await vi.advanceTimersByTimeAsync(delay - 1);
      const count = sockets.length;
      await vi.advanceTimersByTimeAsync(1);
      expect(sockets).toHaveLength(count + 1);
    }
  });

  it('starts the backoff over once a connection became ready', async () => {
    const { stream, sockets, states } = harness();
    stream.start();
    await flush();
    last(sockets).serverClose(1006);
    await vi.advanceTimersByTimeAsync(1_000);
    last(sockets).serverClose(1006);
    await vi.advanceTimersByTimeAsync(2_000);
    const socket = last(sockets);
    socket.open();
    socket.receive(READY);
    const before = Date.now();
    socket.serverClose(1006);
    expect(lastState(states)).toEqual({ kind: 'retrying', retryAt: before + 1_000 });
  });

  it('refreshes the session and reconnects once when the server closes with 1008', async () => {
    const { stream, sockets, states, refreshAuth, tokenCalls } = harness();
    stream.start();
    await flush();
    last(sockets).serverClose(1008);
    await flush();
    expect(refreshAuth).toHaveBeenCalledTimes(1);
    expect(sockets).toHaveLength(2); // reconnected at once, without a backoff delay
    expect(tokenCalls()).toBe(2);
    // The second attempt is rejected as well: no more refreshes, no more sockets.
    last(sockets).serverClose(1008);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(refreshAuth).toHaveBeenCalledTimes(1);
    expect(sockets).toHaveLength(2);
    expect(lastState(states)).toEqual({ kind: 'disconnected' });
  });

  it('gives up when the session cannot be refreshed', async () => {
    const refreshAuth = vi.fn(() => Promise.resolve(false));
    const { stream, sockets, states } = harness({ refreshAuth });
    stream.start();
    await flush();
    last(sockets).serverClose(1008);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(refreshAuth).toHaveBeenCalledTimes(1);
    expect(sockets).toHaveLength(1);
    expect(lastState(states)).toEqual({ kind: 'disconnected' });
  });

  it('retries when no access token can be obtained', async () => {
    let calls = 0;
    const { stream, sockets, states } = harness({
      getToken: () => {
        calls += 1;
        return calls === 1 ? Promise.reject(new Error('offline')) : Promise.resolve('token');
      },
    });
    stream.start();
    await flush();
    expect(sockets).toHaveLength(0);
    expect(lastState(states)).toEqual({ kind: 'retrying', retryAt: 1_000 });
    await vi.advanceTimersByTimeAsync(1_000);
    expect(sockets).toHaveLength(1);
  });

  it('stop closes the socket, cancels a pending retry and ignores late events', async () => {
    const { stream, sockets, states } = harness();
    stream.start();
    await flush();
    const socket = last(sockets);
    socket.open();
    socket.receive(READY);
    stream.stop();
    expect(socket.closed).toBe(true);
    expect(lastState(states)).toEqual({ kind: 'disconnected' });
    socket.serverClose(1006); // a late close event from the abandoned socket
    await vi.advanceTimersByTimeAsync(60_000);
    expect(sockets).toHaveLength(1);

    stream.start();
    await flush();
    last(sockets).serverClose(1006); // now waiting to retry
    stream.stop();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(sockets).toHaveLength(2);
  });

  it('start is idempotent while running', async () => {
    const { stream, sockets } = harness();
    stream.start();
    stream.start();
    await flush();
    expect(sockets).toHaveLength(1);
  });
});

describe('nextDelayMs', () => {
  it('grows exponentially from one second and is capped at thirty', () => {
    const delays = [0, 1, 2, 3, 4, 5, 6, 10].map((attempt) => nextDelayMs(attempt, () => 1));
    expect(delays).toEqual([1_000, 2_000, 4_000, 8_000, 16_000, 30_000, 30_000, 30_000]);
  });

  it('applies full jitter but never waits less than a quarter second', () => {
    expect(nextDelayMs(3, () => 0.5)).toBe(4_000);
    expect(nextDelayMs(3, () => 0)).toBe(250);
  });
});

describe('parseServerMessage', () => {
  it('accepts the three server message types', () => {
    expect(parseServerMessage('{"type":"ready"}')).toEqual({ type: 'ready' });
    const task = { task_id: 't', state: 'running' };
    expect(parseServerMessage(JSON.stringify({ type: 'snapshot', task }))).toEqual({
      type: 'snapshot',
      task,
    });
    const event = { kind: 'state', task_id: 't', state: 'failed' };
    expect(parseServerMessage(JSON.stringify({ type: 'event', event }))).toEqual({
      type: 'event',
      event,
    });
  });

  it('rejects malformed input', () => {
    for (const text of [
      '',
      'null',
      '[]',
      '{"type":"event","event":{"kind":"other","task_id":"t","state":"x"}}',
      '{"type":"snapshot","task":{"task_id":1,"state":"x"}}',
    ]) {
      expect(parseServerMessage(text)).toBeNull();
    }
  });
});
```

Create `frontend/src/realtime/applyMessage.test.ts`:

```ts
import { QueryClient } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest';

import type { BuildStatus } from '../api/endpoints';
import { queryKeys } from '../api/queries';
import { makeBuildStatus } from '../test/fixtures';
import { applyMessage } from './applyMessage';

let queryClient: QueryClient;
let invalidate: MockInstance<QueryClient['invalidateQueries']>;

function event(overrides: Record<string, unknown> = {}) {
  return {
    type: 'event' as const,
    event: {
      kind: 'progress' as const,
      task_id: 'task-1',
      state: 'running' as const,
      progress: { stage: 'enrich_kanji', current: 5, total: 10 },
      error: null,
      ...overrides,
    },
  };
}

function invalidatedKeys(): unknown[] {
  return invalidate.mock.calls.map((call) => call[0]?.queryKey);
}

describe('applyMessage', () => {
  beforeEach(() => {
    queryClient = new QueryClient();
    invalidate = vi.spyOn(queryClient, 'invalidateQueries');
  });

  it('a snapshot replaces the latest build', () => {
    const task = makeBuildStatus({ task_id: 'task-9', state: 'succeeded' });
    applyMessage(queryClient, { type: 'snapshot', task });
    expect(queryClient.getQueryData(queryKeys.latestBuild)).toEqual(task);
    expect(invalidate).not.toHaveBeenCalled();
  });

  it('a progress event updates the build it belongs to', () => {
    queryClient.setQueryData(queryKeys.latestBuild, makeBuildStatus());
    applyMessage(queryClient, event());
    const cached = queryClient.getQueryData<BuildStatus>(queryKeys.latestBuild);
    expect(cached?.progress).toEqual({ stage: 'enrich_kanji', current: 5, total: 10 });
    expect(cached?.state).toBe('running');
    expect(invalidate).not.toHaveBeenCalled();
  });

  it('keeps the previous progress and error when an event carries none', () => {
    queryClient.setQueryData(
      queryKeys.latestBuild,
      makeBuildStatus({ progress: { stage: 'write', current: 1, total: 2 } }),
    );
    applyMessage(queryClient, event({ progress: null }));
    expect(queryClient.getQueryData<BuildStatus>(queryKeys.latestBuild)?.progress).toEqual({
      stage: 'write',
      current: 1,
      total: 2,
    });
  });

  it('fetches the latest build when the event is about a build we have not seen', () => {
    queryClient.setQueryData(queryKeys.latestBuild, makeBuildStatus({ task_id: 'older' }));
    applyMessage(queryClient, event());
    expect(invalidatedKeys()).toEqual([queryKeys.latestBuild]);
    queryClient.clear();
    invalidate.mockClear();
    applyMessage(queryClient, event()); // nothing cached at all
    expect(invalidatedKeys()).toEqual([queryKeys.latestBuild]);
  });

  it('a build that ended refreshes the build, the content summary and the checks', () => {
    queryClient.setQueryData(queryKeys.latestBuild, makeBuildStatus());
    applyMessage(queryClient, event({ kind: 'state', state: 'succeeded', progress: null }));
    expect(queryClient.getQueryData<BuildStatus>(queryKeys.latestBuild)?.state).toBe('succeeded');
    expect(invalidatedKeys()).toEqual([
      queryKeys.latestBuild,
      queryKeys.contentSummary,
      queryKeys.configCheck,
    ]);
  });

  it('a failed build carries its error message into the cache', () => {
    queryClient.setQueryData(queryKeys.latestBuild, makeBuildStatus());
    applyMessage(
      queryClient,
      event({ kind: 'state', state: 'failed', progress: null, error: 'the deck is missing' }),
    );
    const cached = queryClient.getQueryData<BuildStatus>(queryKeys.latestBuild);
    expect(cached?.state).toBe('failed');
    expect(cached?.error).toBe('the deck is missing');
  });
});
```

Create `frontend/src/realtime/RealtimeProvider.test.tsx`:

```tsx
import { screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { BuildStatus } from '../api/endpoints';
import { queryKeys } from '../api/queries';
import { session } from '../auth/session';
import { FakeSocket } from '../test/fakeSocket';
import { makeBuildStatus } from '../test/fixtures';
import { renderWithProviders } from '../test/render';
import { ConnectionBadge } from './ConnectionBadge';
import { RealtimeProvider } from './RealtimeProvider';
import { RealtimeContext, useConnectionState } from './realtimeContext';

const sockets: FakeSocket[] = [];
function createSocket(url: string): FakeSocket {
  const socket = new FakeSocket(url);
  sockets.push(socket);
  return socket;
}

function firstSocket(): FakeSocket {
  const socket = sockets[0];
  if (socket === undefined) throw new Error('no socket was created');
  return socket;
}

function Probe() {
  return <span data-testid="state">{useConnectionState().kind}</span>;
}

describe('RealtimeProvider', () => {
  beforeEach(() => {
    sockets.length = 0;
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  it('connects with the session token and reports the connection state', async () => {
    renderWithProviders(
      <RealtimeProvider createSocket={createSocket}>
        <Probe />
      </RealtimeProvider>,
    );
    await waitFor(() => {
      expect(sockets).toHaveLength(1);
    });
    expect(firstSocket().url).toMatch(/^ws:\/\/.*\/api\/v1\/ws\/tasks$/);
    firstSocket().open();
    expect(JSON.parse(firstSocket().sent[0] ?? 'null')).toEqual({ type: 'auth', token: 'a1' });
    expect(screen.getByTestId('state')).toHaveTextContent('connecting');
    firstSocket().receive({ type: 'ready' });
    await waitFor(() => {
      expect(screen.getByTestId('state')).toHaveTextContent('connected');
    });
  });

  it('folds snapshots and events into the query cache', async () => {
    const { queryClient } = renderWithProviders(
      <RealtimeProvider createSocket={createSocket}>
        <Probe />
      </RealtimeProvider>,
    );
    await waitFor(() => {
      expect(sockets).toHaveLength(1);
    });
    const socket = firstSocket();
    socket.open();
    socket.receive({ type: 'ready' });
    const task = makeBuildStatus();
    socket.receive({ type: 'snapshot', task });
    expect(queryClient.getQueryData(queryKeys.latestBuild)).toEqual(task);
    socket.receive({
      type: 'event',
      event: {
        kind: 'progress',
        task_id: task.task_id,
        state: 'running',
        progress: { stage: 'write', current: 1, total: 2 },
        error: null,
      },
    });
    expect(queryClient.getQueryData<BuildStatus>(queryKeys.latestBuild)?.progress?.stage).toBe(
      'write',
    );
  });

  it('closes the connection when it is unmounted', async () => {
    const { unmount } = renderWithProviders(
      <RealtimeProvider createSocket={createSocket}>
        <Probe />
      </RealtimeProvider>,
    );
    await waitFor(() => {
      expect(sockets).toHaveLength(1);
    });
    unmount();
    expect(firstSocket().closed).toBe(true);
  });
});

describe('ConnectionBadge', () => {
  it.each([
    [{ kind: 'connected' }, 'Live'],
    [{ kind: 'connecting' }, 'Connecting…'],
    [{ kind: 'disconnected' }, 'Offline'],
  ] as const)('shows %j as "%s"', (state, label) => {
    renderWithProviders(
      <RealtimeContext value={state}>
        <ConnectionBadge />
      </RealtimeContext>,
    );
    expect(screen.getByRole('status')).toHaveTextContent(label);
  });

  it('counts down to the next reconnection attempt', () => {
    vi.useFakeTimers();
    vi.setSystemTime(0);
    try {
      renderWithProviders(
        <RealtimeContext value={{ kind: 'retrying', retryAt: 4_000 }}>
          <ConnectionBadge />
        </RealtimeContext>,
      );
      expect(screen.getByRole('status')).toHaveTextContent('Reconnecting in 4 s');
    } finally {
      vi.useRealTimers();
    }
  });
});
```

Create `frontend/src/api/queries.test.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { makeBuildStatus } from '../test/fixtures';
import { BUILD_POLL_MS, pollInterval } from './queries';

describe('pollInterval', () => {
  it('polls only while a build runs and the live stream is not connected', () => {
    const running = makeBuildStatus({ state: 'running' });
    expect(pollInterval(running, false)).toBe(BUILD_POLL_MS);
    expect(pollInterval(running, true)).toBe(false);
  });

  it('never polls a finished build, no build, or an unknown state', () => {
    expect(pollInterval(makeBuildStatus({ state: 'succeeded' }), false)).toBe(false);
    expect(pollInterval(makeBuildStatus({ state: 'failed' }), false)).toBe(false);
    expect(pollInterval(null, false)).toBe(false);
    expect(pollInterval(undefined, false)).toBe(false);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm test`
Expected: FAIL (modules not found: `./backoff`, `./messages`, `./BuildStream`, `./applyMessage`, `./RealtimeProvider`, `./queries`, ...).

- [ ] **Step 3: Implement (verified files)**

Create `frontend/src/realtime/backoff.ts`:

```ts
const BASE_DELAY_MS = 1_000;
const MAX_DELAY_MS = 30_000;
/** Even a lucky jitter draw waits a little, so a broken server is never hammered. */
const MIN_DELAY_MS = 250;

/**
 * Reconnect delay after `attempt` failed attempts (0 for the first retry): exponential growth from
 * one second, capped at 30 seconds, with full jitter (a uniform draw between zero and the cap).
 */
export function nextDelayMs(attempt: number, random: () => number = Math.random): number {
  const ceiling = Math.min(MAX_DELAY_MS, BASE_DELAY_MS * 2 ** attempt);
  return Math.max(MIN_DELAY_MS, Math.round(random() * ceiling));
}
```

Create `frontend/src/realtime/messages.ts`:

```ts
import type { components } from '../api/schema';

type Schemas = components['schemas'];

export type BuildStatus = Schemas['BuildStatusResponse'];
export type BuildEvent = Schemas['BuildEventModel'];

/** What the server sends on `/ws/tasks` after the client authenticated. */
export type ServerMessage =
  | { type: 'ready' }
  | { type: 'snapshot'; task: BuildStatus }
  | { type: 'event'; event: BuildEvent };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

/** Parse one text frame. Anything that is not a well-formed server message returns null. */
export function parseServerMessage(text: string): ServerMessage | null {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    return null;
  }
  if (!isRecord(value)) return null;
  switch (value.type) {
    case 'ready':
      return { type: 'ready' };
    case 'snapshot':
      return isRecord(value.task) &&
        typeof value.task.task_id === 'string' &&
        typeof value.task.state === 'string'
        ? { type: 'snapshot', task: value.task as BuildStatus }
        : null;
    case 'event':
      return isRecord(value.event) &&
        typeof value.event.task_id === 'string' &&
        typeof value.event.state === 'string' &&
        (value.event.kind === 'progress' || value.event.kind === 'state')
        ? { type: 'event', event: value.event as BuildEvent }
        : null;
    default:
      return null;
  }
}
```

Create `frontend/src/realtime/BuildStream.ts`:

```ts
import { nextDelayMs } from './backoff';
import { parseServerMessage, type ServerMessage } from './messages';

export type ConnectionState =
  | { kind: 'connecting' }
  | { kind: 'connected' }
  | { kind: 'retrying'; retryAt: number }
  | { kind: 'disconnected' };

/** The part of the browser WebSocket this class uses (so tests can substitute a fake). */
export interface SocketLike {
  onopen: ((event: Event) => void) | null;
  onmessage: ((event: MessageEvent) => void) | null;
  onclose: ((event: CloseEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
  send: (data: string) => void;
  close: () => void;
}

export interface BuildStreamOptions {
  /** The ws:// or wss:// URL of the task stream. */
  url: string;
  /** A usable access token, refreshed first if needed. Called before every connection attempt. */
  getToken: () => Promise<string>;
  /** Refresh the session after the server closed with 1008. Resolves true when it worked. */
  refreshAuth: () => Promise<boolean>;
  onState: (state: ConnectionState) => void;
  /** Called for every `snapshot` and `event` message (`ready` is handled internally). */
  onMessage: (message: Exclude<ServerMessage, { type: 'ready' }>) => void;
  createSocket?: (url: string) => SocketLike;
  random?: () => number;
  now?: () => number;
}

/** The server closes with this code when the auth message was missing, malformed or rejected. */
const POLICY_VIOLATION = 1008;

/**
 * A reconnecting client of the server's task stream. It authenticates with its first message,
 * reports its connection state, forwards snapshots and events, reconnects with exponential
 * backoff and jitter, and on an authentication failure (close code 1008) refreshes the session and
 * reconnects once before giving up. Framework-free so it can be tested with a fake socket.
 */
export class BuildStream {
  private readonly options: BuildStreamOptions;
  private socket: SocketLike | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private attempt = 0;
  private authRetried = false;
  private stopped = true;
  /** Incremented on every connection attempt and on stop, so stale callbacks can be ignored. */
  private generation = 0;

  constructor(options: BuildStreamOptions) {
    this.options = options;
  }

  start(): void {
    if (!this.stopped) return;
    this.stopped = false;
    this.attempt = 0;
    this.authRetried = false;
    void this.connect();
  }

  stop(): void {
    this.stopped = true;
    this.generation += 1;
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    this.detachSocket();
    this.options.onState({ kind: 'disconnected' });
  }

  private detachSocket(): void {
    const socket = this.socket;
    this.socket = null;
    if (socket === null) return;
    socket.onopen = null;
    socket.onmessage = null;
    socket.onclose = null;
    socket.onerror = null;
    socket.close();
  }

  private async connect(): Promise<void> {
    this.generation += 1;
    const generation = this.generation;
    this.options.onState({ kind: 'connecting' });
    let token: string;
    try {
      token = await this.options.getToken();
    } catch {
      if (!this.stopped && generation === this.generation) this.scheduleRetry();
      return;
    }
    if (this.stopped || generation !== this.generation) return;

    const socket = (this.options.createSocket ?? ((url) => new WebSocket(url)))(this.options.url);
    this.socket = socket;
    socket.onopen = () => {
      socket.send(JSON.stringify({ type: 'auth', token }));
    };
    socket.onmessage = (event) => {
      if (generation === this.generation) this.handleFrame(event.data);
    };
    socket.onclose = (event) => {
      if (generation === this.generation) void this.handleClose(event.code, generation);
    };
    socket.onerror = () => {
      // A close event always follows an error; the reconnect logic lives there.
    };
  }

  private handleFrame(data: unknown): void {
    const message = typeof data === 'string' ? parseServerMessage(data) : null;
    if (message === null) return;
    if (message.type === 'ready') {
      this.attempt = 0;
      this.authRetried = false;
      this.options.onState({ kind: 'connected' });
      return;
    }
    this.options.onMessage(message);
  }

  private async handleClose(code: number, generation: number): Promise<void> {
    this.socket = null;
    if (code !== POLICY_VIOLATION) {
      this.scheduleRetry();
      return;
    }
    if (this.authRetried) {
      this.options.onState({ kind: 'disconnected' });
      return;
    }
    this.authRetried = true;
    const refreshed = await this.options.refreshAuth().catch(() => false);
    if (this.stopped || generation !== this.generation) return;
    if (refreshed) {
      void this.connect();
    } else {
      this.options.onState({ kind: 'disconnected' });
    }
  }

  private scheduleRetry(): void {
    const delay = nextDelayMs(this.attempt, this.options.random);
    this.attempt += 1;
    const now = this.options.now ?? Date.now;
    this.options.onState({ kind: 'retrying', retryAt: now() + delay });
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.connect();
    }, delay);
  }
}
```

Create `frontend/src/api/queries.ts`:

```ts
import { useQuery } from '@tanstack/react-query';

import { endpoints, type BuildStatus } from './endpoints';

/** Query keys, shared by the hooks and by the code that updates the cache from the live stream. */
export const queryKeys = {
  contentSummary: ['content', 'summary'] as const,
  configCheck: ['admin', 'config-check'] as const,
  latestBuild: ['build', 'latest'] as const,
};

/** While a build runs and the live stream is down, ask the server this often. */
export const BUILD_POLL_MS = 2_000;

export function pollInterval(
  build: BuildStatus | null | undefined,
  streamConnected: boolean,
): number | false {
  return build?.state === 'running' && !streamConnected ? BUILD_POLL_MS : false;
}

export function useContentSummary() {
  return useQuery({ queryKey: queryKeys.contentSummary, queryFn: endpoints.contentSummary });
}

export function useConfigCheck() {
  return useQuery({ queryKey: queryKeys.configCheck, queryFn: endpoints.configCheck });
}

/** The latest build (null when none ran yet). Polls only while the live stream cannot be trusted. */
export function useLatestBuild(streamConnected: boolean) {
  return useQuery({
    queryKey: queryKeys.latestBuild,
    queryFn: endpoints.latestBuild,
    refetchInterval: (query) => pollInterval(query.state.data, streamConnected),
  });
}
```

Create `frontend/src/realtime/applyMessage.ts`:

```ts
import type { QueryClient } from '@tanstack/react-query';

import type { BuildStatus } from '../api/endpoints';
import { queryKeys } from '../api/queries';
import type { ServerMessage } from './messages';

/**
 * Fold one live message into the query cache.
 *
 * A snapshot replaces the latest build. An event updates it when it is about the same build,
 * otherwise (a build this browser has not seen) the latest build is fetched. A build that ended
 * also refreshes everything that depends on the content: the final status carries the report.
 */
export function applyMessage(
  queryClient: QueryClient,
  message: Exclude<ServerMessage, { type: 'ready' }>,
): void {
  if (message.type === 'snapshot') {
    queryClient.setQueryData(queryKeys.latestBuild, message.task);
    return;
  }
  const { event } = message;
  const current = queryClient.getQueryData<BuildStatus | null>(queryKeys.latestBuild);
  if (current?.task_id === event.task_id) {
    const updated: BuildStatus = {
      ...current,
      state: event.state,
      progress: event.progress ?? current.progress,
      error: event.error ?? current.error,
    };
    queryClient.setQueryData(queryKeys.latestBuild, updated);
  } else {
    void queryClient.invalidateQueries({ queryKey: queryKeys.latestBuild });
  }
  if (event.state !== 'running') {
    void queryClient.invalidateQueries({ queryKey: queryKeys.latestBuild });
    void queryClient.invalidateQueries({ queryKey: queryKeys.contentSummary });
    void queryClient.invalidateQueries({ queryKey: queryKeys.configCheck });
  }
}
```

Create `frontend/src/realtime/realtimeContext.ts`:

```ts
import { createContext, useContext } from 'react';

import type { ConnectionState } from './BuildStream';

export const RealtimeContext = createContext<ConnectionState>({ kind: 'disconnected' });

/** The state of the live connection to the server (for the badge and the polling fallback). */
export function useConnectionState(): ConnectionState {
  return useContext(RealtimeContext);
}
```

Create `frontend/src/realtime/RealtimeProvider.tsx`:

```tsx
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState, type ReactNode } from 'react';

import { ensureAccessToken, refreshSession } from '../api/client';
import { wsUrl } from '../api/http';
import { applyMessage } from './applyMessage';
import { BuildStream, type ConnectionState, type SocketLike } from './BuildStream';
import { RealtimeContext } from './realtimeContext';

interface RealtimeProviderProps {
  children: ReactNode;
  /** Test seam: replaces the browser WebSocket. Must be a stable reference. */
  createSocket?: (url: string) => SocketLike;
}

/** Keeps one connection to the server's task stream open while the user is logged in. */
export function RealtimeProvider({ children, createSocket }: RealtimeProviderProps) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<ConnectionState>({ kind: 'connecting' });

  useEffect(() => {
    const stream = new BuildStream({
      url: wsUrl('/ws/tasks'),
      getToken: ensureAccessToken,
      refreshAuth: async () => {
        try {
          await refreshSession(); // a rejected refresh token ends the session (AuthProvider)
          return true;
        } catch {
          return false;
        }
      },
      onState: setState,
      onMessage: (message) => {
        applyMessage(queryClient, message);
      },
      createSocket,
    });
    stream.start();
    return () => {
      stream.stop();
    };
  }, [queryClient, createSocket]);

  return <RealtimeContext value={state}>{children}</RealtimeContext>;
}
```

Create `frontend/src/realtime/ConnectionBadge.tsx`:

```tsx
import { Badge } from '@mantine/core';

import { useSecondsUntil } from '../hooks/useCountdown';
import type { ConnectionState } from './BuildStream';
import { useConnectionState } from './realtimeContext';

function describe(state: ConnectionState, secondsLeft: number): { color: string; label: string } {
  switch (state.kind) {
    case 'connected':
      return { color: 'green', label: 'Live' };
    case 'connecting':
      return { color: 'yellow', label: 'Connecting…' };
    case 'retrying':
      return { color: 'orange', label: `Reconnecting in ${String(secondsLeft)} s` };
    case 'disconnected':
      return { color: 'red', label: 'Offline' };
  }
}

/** The state of the live connection, always visible in the header. */
export function ConnectionBadge() {
  const state = useConnectionState();
  const secondsLeft = useSecondsUntil(state.kind === 'retrying' ? state.retryAt : null);
  const { color, label } = describe(state, secondsLeft);
  return (
    <Badge color={color} variant="dot" role="status" aria-label={`Connection: ${label}`}>
      {label}
    </Badge>
  );
}
```

- [ ] **Step 4: Run the gate**

```bash
npm run format && npm run format:check && npm run lint && npm run build && npm run coverage
```
Expected: everything passes (about 75 tests so far). The stream tests use fake timers and a fake socket; a failure there is a real logic bug: never add real waits.

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/src
git commit -m "feat: reconnecting build stream, live query updates and connection badge" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 8: The Build screen

**Files (all under `frontend/src/features/build/`):**
- Create: `format.ts`, `EnvironmentChecks.tsx`, `BuildReportTable.tsx`, `BuildProgressCard.tsx`, `BuildPage.tsx`
- Test: `format.test.ts`, `BuildPage.test.tsx`

**Interfaces:**
- Consumes: Task 7 (`useConfigCheck`, `useContentSummary`, `useLatestBuild`, `queryKeys`, `useConnectionState`, `makeBuildStatus`, `makeReport`), Task 5 (`endpoints`, `messageFor`).
- Produces: `formatCount(n)`; `<EnvironmentChecks>`; `<BuildReportTable report>`; `<BuildProgressCard task>`; `<BuildPage>` (not yet routed: Task 9 wires it). Behaviour: first-run notice when content is not built; Build button (label "Build content" / "Rebuild content" / "Start dry run"); a confirmation modal only for a real rebuild of built content; a "Dry run" switch; live progress with friendly stage labels (`import_deck`, `enrich_kanji`, `write`); a 409 or any start failure shows a toast; the report after success; the server's message after a failure.

- [ ] **Step 1: Write the tests (verified files)**

Create `frontend/src/features/build/format.test.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { formatCount } from './format';

describe('formatCount', () => {
  it('groups thousands the same way everywhere', () => {
    expect(formatCount(0)).toBe('0');
    expect(formatCount(999)).toBe('999');
    expect(formatCount(7734)).toBe('7,734');
    expect(formatCount(1234567)).toBe('1,234,567');
  });
});
```

Create `frontend/src/features/build/BuildPage.test.tsx`:

```tsx
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import type { BuildStatus } from '../../api/endpoints';
import { session } from '../../auth/session';
import { makeBuildStatus, makeReport } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { BuildPage } from './BuildPage';

const BUILD = '/api/v1/admin/content/build';

const ALL_OK = {
  ok: true,
  checks: [
    { name: 'deck_present', ok: true, detail: 'resources/deck.apkg' },
    { name: 'deck_checksum', ok: true, detail: 'matches' },
    { name: 'data_dir_writable', ok: true, detail: '/data' },
    { name: 'jamdict_available', ok: true, detail: 'jamdict-data-fix' },
  ],
};

function summary(built: boolean) {
  return {
    built,
    kana: built ? 208 : 0,
    kanji: 0,
    vocab: 0,
    unleveled_kanji: 0,
    kanji_by_level: {},
    vocab_by_level: {},
    meta: {},
  };
}

interface Scenario {
  built?: boolean;
  latest?: BuildStatus | null;
  checks?: Record<string, unknown>;
}

/** Serve the read endpoints; returns the bodies received by POST /admin/content/build. */
function serve({ built = false, latest = null, checks = ALL_OK }: Scenario = {}) {
  const posted: unknown[] = [];
  server.use(
    http.get('/api/v1/content/summary', () => HttpResponse.json(summary(built))),
    http.get('/api/v1/admin/config-check', () => HttpResponse.json(checks)),
    http.get(BUILD, () =>
      latest === null
        ? HttpResponse.json({ detail: 'no build has run yet' }, { status: 404 })
        : HttpResponse.json(latest),
    ),
    http.post(BUILD, async ({ request }) => {
      posted.push(await request.json());
      return HttpResponse.json(makeBuildStatus(), { status: 202 });
    }),
  );
  return posted;
}

describe('BuildPage', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  it('shows what the server found in the environment, problems included', async () => {
    serve({
      checks: {
        ok: false,
        checks: [
          { name: 'deck_present', ok: false, detail: 'deck not found' },
          { name: 'jamdict_available', ok: true, detail: 'jamdict-data-fix' },
        ],
      },
    });
    renderWithProviders(<BuildPage />);
    expect(await screen.findByText('deck not found')).toBeInTheDocument();
    expect(screen.getByText('Vocabulary deck')).toBeInTheDocument();
    expect(screen.getByText('Problem')).toBeInTheDocument();
    expect(screen.getByText('OK')).toBeInTheDocument();
  });

  it('welcomes a first run and starts the first build without asking', async () => {
    const posted = serve({ built: false });
    renderWithProviders(<BuildPage />);
    expect(await screen.findByText('First run')).toBeInTheDocument();
    await userEvent.click(await screen.findByRole('button', { name: 'Build content' }));
    await waitFor(() => {
      expect(posted).toEqual([{ dry_run: false }]);
    });
    expect(await screen.findByText('Reading the vocabulary deck')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Build content' })).toBeDisabled();
  });

  it('asks before replacing built content, and does nothing on Cancel', async () => {
    const posted = serve({ built: true });
    renderWithProviders(<BuildPage />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Rebuild content' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/progress is kept/i)).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(posted).toEqual([]);

    await user.click(screen.getByRole('button', { name: 'Rebuild content' }));
    await user.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Rebuild' }),
    );
    await waitFor(() => {
      expect(posted).toEqual([{ dry_run: false }]);
    });
  });

  it('starts a dry run without asking, even when content is built', async () => {
    const posted = serve({ built: true });
    renderWithProviders(<BuildPage />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('switch', { name: /dry run/i }));
    await user.click(screen.getByRole('button', { name: 'Start dry run' }));
    await waitFor(() => {
      expect(posted).toEqual([{ dry_run: true }]);
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('says so when a build is already running (409)', async () => {
    serve({ built: false });
    server.use(
      http.post(BUILD, () =>
        HttpResponse.json({ detail: 'a build is already running' }, { status: 409 }),
      ),
    );
    renderWithProviders(<BuildPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Build content' }));
    expect(await screen.findByText('a build is already running')).toBeInTheDocument();
    expect(screen.getByText('Could not start the build')).toBeInTheDocument();
  });

  it('shows the progress of a build that is already running', async () => {
    serve({
      built: true,
      latest: makeBuildStatus({ progress: { stage: 'enrich_kanji', current: 1200, total: 3088 } }),
    });
    renderWithProviders(<BuildPage />);
    expect(await screen.findByText(/Looking up kanji details/)).toHaveTextContent('1,200 of 3,088');
    expect(screen.getByRole('button', { name: 'Rebuild content' })).toBeDisabled();
  });

  it('shows the message of a failed build', async () => {
    serve({
      latest: makeBuildStatus({ state: 'failed', progress: null, error: 'the deck is missing' }),
    });
    renderWithProviders(<BuildPage />);
    expect(await screen.findByText('The build failed')).toBeInTheDocument();
    expect(screen.getByText('the deck is missing')).toBeInTheDocument();
  });

  it('shows the report of a finished build', async () => {
    serve({
      built: true,
      latest: makeBuildStatus({ state: 'succeeded', progress: null, report: makeReport() }),
    });
    renderWithProviders(<BuildPage />);
    expect(await screen.findByText('Finished')).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Items per JLPT level' });
    expect(within(table).getByText('3,053')).toBeInTheDocument(); // N1 vocabulary
    expect(screen.getByText(/7,734 vocabulary items/)).toBeInTheDocument();
    expect(screen.getByText(/Finished in 31\.4 seconds/)).toBeInTheDocument();
  });

  it('marks a dry-run report as such', async () => {
    serve({
      latest: makeBuildStatus({
        state: 'succeeded',
        dry_run: true,
        progress: null,
        report: makeReport({ dry_run: true }),
      }),
    });
    renderWithProviders(<BuildPage />);
    expect(await screen.findByText('Dry run: nothing was written.')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm test`
Expected: FAIL (modules not found: `./format`, `./BuildPage`).

- [ ] **Step 3: Implement (verified files)**

Create `frontend/src/features/build/format.ts`:

```ts
/** Whole numbers with thousands separators, the same on every machine. */
export function formatCount(value: number): string {
  return value.toLocaleString('en-US');
}
```

Create `frontend/src/features/build/EnvironmentChecks.tsx`:

```tsx
import { Alert, Badge, Group, Paper, Skeleton, Stack, Text, Title } from '@mantine/core';

import { messageFor } from '../../api/errors';
import { useConfigCheck } from '../../api/queries';

const CHECK_LABELS: Record<string, string> = {
  deck_present: 'Vocabulary deck',
  deck_checksum: 'Deck checksum',
  data_dir_writable: 'Data folder',
  jamdict_available: 'Dictionary',
};

/** What a content build needs from its environment, checked by the server. */
export function EnvironmentChecks() {
  const checks = useConfigCheck();

  if (checks.isPending) return <Skeleton height={112} />;
  if (checks.isError) {
    return (
      <Alert color="red" title="Couldn't check the environment">
        {messageFor(checks.error)}
      </Alert>
    );
  }
  return (
    <Paper withBorder p="md">
      <Title order={4} mb="xs">
        Environment
      </Title>
      <Stack gap={6}>
        {checks.data.checks.map((check) => (
          <Group key={check.name} gap="xs" wrap="nowrap" align="flex-start">
            <Badge color={check.ok ? 'green' : 'red'} variant="light" w={72}>
              {check.ok ? 'OK' : 'Problem'}
            </Badge>
            <Text size="sm" fw={500}>
              {CHECK_LABELS[check.name] ?? check.name}
            </Text>
            <Text size="sm" c="dimmed">
              {check.detail}
            </Text>
          </Group>
        ))}
      </Stack>
    </Paper>
  );
}
```

Create `frontend/src/features/build/BuildReportTable.tsx`:

```tsx
import { List, Stack, Table, Text } from '@mantine/core';

import type { BuildStatus } from '../../api/endpoints';
import { formatCount } from './format';

const LEVELS = ['N5', 'N4', 'N3', 'N2', 'N1'] as const;

/** The result of a finished build: counts per JLPT level and the totals. */
export function BuildReportTable({ report }: { report: NonNullable<BuildStatus['report']> }) {
  return (
    <Stack gap="sm">
      {report.dry_run && (
        <Text size="sm" c="dimmed">
          Dry run: nothing was written.
        </Text>
      )}
      <Table withTableBorder aria-label="Items per JLPT level">
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Level</Table.Th>
            <Table.Th ta="right">Vocabulary</Table.Th>
            <Table.Th ta="right">Kanji</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {LEVELS.map((level) => (
            <Table.Tr key={level}>
              <Table.Td>{level}</Table.Td>
              <Table.Td ta="right">{formatCount(report.vocab_by_level[level] ?? 0)}</Table.Td>
              <Table.Td ta="right">{formatCount(report.kanji_by_level[level] ?? 0)}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      <List size="sm" spacing={2}>
        <List.Item>{formatCount(report.kana_count)} kana</List.Item>
        <List.Item>{formatCount(report.vocab_count)} vocabulary items</List.Item>
        <List.Item>
          {formatCount(report.kanji_count)} kanji ({formatCount(report.unleveled_kanji_count)} not
          in the JLPT vocabulary)
        </List.Item>
        <List.Item>{formatCount(report.sentence_count)} example sentences</List.Item>
        <List.Item>Finished in {report.duration_seconds.toFixed(1)} seconds</List.Item>
      </List>
    </Stack>
  );
}
```

Create `frontend/src/features/build/BuildProgressCard.tsx`:

```tsx
import { Alert, Badge, Group, Paper, Progress, Stack, Text, Title } from '@mantine/core';

import type { BuildStatus } from '../../api/endpoints';
import { BuildReportTable } from './BuildReportTable';
import { formatCount } from './format';

const STAGE_LABELS: Record<string, string> = {
  import_deck: 'Reading the vocabulary deck',
  enrich_kanji: 'Looking up kanji details',
  write: 'Writing the content database',
};

const STATE_BADGES: Record<BuildStatus['state'], { color: string; label: string }> = {
  running: { color: 'blue', label: 'Running' },
  succeeded: { color: 'green', label: 'Finished' },
  failed: { color: 'red', label: 'Failed' },
};

/** The state of one build: live progress while it runs, then the report or the error. */
export function BuildProgressCard({ task }: { task: BuildStatus }) {
  const { progress } = task;
  const badge = STATE_BADGES[task.state];
  const percent =
    progress !== null && progress.total > 0
      ? Math.round((progress.current / progress.total) * 100)
      : 0;
  const stage = progress === null ? 'Starting' : (STAGE_LABELS[progress.stage] ?? progress.stage);

  return (
    <Paper withBorder p="md">
      <Group justify="space-between" mb="sm">
        <Title order={4}>{task.dry_run ? 'Dry run' : 'Content build'}</Title>
        <Badge color={badge.color}>{badge.label}</Badge>
      </Group>
      {task.state === 'running' && (
        <Stack gap="xs" role="status" aria-live="polite">
          <Text size="sm">
            {stage}
            {progress !== null && progress.total > 1
              ? ` (${formatCount(progress.current)} of ${formatCount(progress.total)})`
              : ''}
          </Text>
          <Progress value={percent} animated aria-label="Build progress" />
        </Stack>
      )}
      {task.state === 'failed' && (
        <Alert color="red" title="The build failed">
          {task.error ?? 'No details were reported.'}
        </Alert>
      )}
      {task.state === 'succeeded' && task.report !== null && (
        <BuildReportTable report={task.report} />
      )}
    </Paper>
  );
}
```

Create `frontend/src/features/build/BuildPage.tsx`:

```tsx
import { Alert, Button, Group, Modal, Stack, Switch, Text, Title } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { messageFor } from '../../api/errors';
import { endpoints } from '../../api/endpoints';
import { queryKeys, useContentSummary, useLatestBuild } from '../../api/queries';
import { useConnectionState } from '../../realtime/realtimeContext';
import { BuildProgressCard } from './BuildProgressCard';
import { EnvironmentChecks } from './EnvironmentChecks';

/** Start a content build (or a dry run) and follow it live. */
export function BuildPage() {
  const queryClient = useQueryClient();
  const connection = useConnectionState();
  const summary = useContentSummary();
  const latest = useLatestBuild(connection.kind === 'connected');
  const [dryRun, setDryRun] = useState(false);
  const [confirming, { open: askToConfirm, close: cancelConfirm }] = useDisclosure(false);

  const start = useMutation({
    mutationFn: (dry: boolean) => endpoints.startBuild(dry),
    onSuccess: (task) => {
      queryClient.setQueryData(queryKeys.latestBuild, task);
    },
    onError: (error) => {
      notifications.show({
        color: 'red',
        title: 'Could not start the build',
        message: messageFor(error),
      });
    },
  });

  const running = latest.data?.state === 'running' || start.isPending;
  const alreadyBuilt = summary.data?.built === true;

  const buildLabel = dryRun ? 'Start dry run' : alreadyBuilt ? 'Rebuild content' : 'Build content';

  const onBuild = () => {
    if (alreadyBuilt && !dryRun) {
      askToConfirm();
    } else {
      start.mutate(dryRun);
    }
  };

  return (
    <Stack gap="md">
      <Title order={2}>Content</Title>
      {!alreadyBuilt && summary.isSuccess && (
        <Alert color="blue" title="First run">
          The study content has not been built yet. Build it once from the vocabulary deck; it takes
          about half a minute.
        </Alert>
      )}
      <EnvironmentChecks />
      <Group>
        <Button onClick={onBuild} loading={start.isPending} disabled={running || summary.isPending}>
          {buildLabel}
        </Button>
        <Switch
          label="Dry run (check without writing)"
          checked={dryRun}
          onChange={(event) => {
            setDryRun(event.currentTarget.checked);
          }}
          disabled={running}
        />
      </Group>
      {latest.data ? <BuildProgressCard task={latest.data} /> : null}

      <Modal opened={confirming} onClose={cancelConfirm} title="Rebuild content?" centered>
        <Stack>
          <Text size="sm">
            This replaces the content database with a fresh build from the deck. Your study progress
            is kept.
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={cancelConfirm}>
              Cancel
            </Button>
            <Button
              onClick={() => {
                cancelConfirm();
                start.mutate(false);
              }}
            >
              Rebuild
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
```

- [ ] **Step 4: Run the gate**

```bash
npm run format && npm run format:check && npm run lint && npm run build && npm run coverage
```
Expected: everything passes (about 85 tests so far).

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/src
git commit -m "feat: the content Build screen with live progress" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 9: App shell, Home page and routing

**Files (all under `frontend/src/`):**
- Create: `components/ColorSchemeToggle.tsx`, `components/ErrorBoundary.tsx`, `components/AppLayout.tsx`, `features/NotFoundPage.tsx`, `features/home/HomePage.tsx`
- Modify: `App.tsx` (replace the hello page), `App.test.tsx` (replace the hello test)
- Test: `components/ColorSchemeToggle.test.tsx`, `components/ErrorBoundary.test.tsx`, `components/AppLayout.test.tsx`, `features/home/HomePage.test.tsx`, `App.test.tsx`

**Interfaces:**
- Consumes: Tasks 5 to 8.
- Produces: the finished 2B-1 application: `/login`; the authenticated area (`RequireAuth` → `RealtimeProvider` → `AppLayout`) with `/` (Home), `/build` (Build) and a not-found page; light / dark / auto theme; a route-keyed error boundary.

- [ ] **Step 1: Write the tests (verified files)**

Create `frontend/src/components/ColorSchemeToggle.test.tsx`:

```tsx
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { renderWithProviders } from '../test/render';
import { ColorSchemeToggle } from './ColorSchemeToggle';

describe('ColorSchemeToggle', () => {
  it('offers light, dark and auto, and switches between them', async () => {
    renderWithProviders(<ColorSchemeToggle />);
    const user = userEvent.setup();
    // The test provider starts on Mantine's default scheme (light); the app itself starts on auto.
    expect(screen.getByRole('radio', { name: 'Light' })).toBeChecked();
    await user.click(screen.getByText('Dark'));
    expect(screen.getByRole('radio', { name: 'Dark' })).toBeChecked();
    await user.click(screen.getByText('Auto'));
    expect(screen.getByRole('radio', { name: 'Auto' })).toBeChecked();
  });
});
```

Create `frontend/src/components/ErrorBoundary.test.tsx`:

```tsx
import { screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/render';
import { ErrorBoundary } from './ErrorBoundary';

function Broken({ fail }: { fail: boolean }) {
  if (fail) throw new Error('secret internal detail');
  return <p>All good</p>;
}

describe('ErrorBoundary', () => {
  beforeEach(() => {
    // React logs a caught render error; keep the test output quiet.
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders its children when nothing is wrong', () => {
    renderWithProviders(
      <ErrorBoundary>
        <Broken fail={false} />
      </ErrorBoundary>,
    );
    expect(screen.getByText('All good')).toBeInTheDocument();
  });

  it('shows a friendly page, never the error itself', () => {
    renderWithProviders(
      <ErrorBoundary>
        <Broken fail />
      </ErrorBoundary>,
    );
    expect(screen.getByRole('heading', { name: 'Something went wrong' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reload the page' })).toBeInTheDocument();
    expect(screen.queryByText(/secret internal detail/)).not.toBeInTheDocument();
  });

  it('logs the details to the console', () => {
    renderWithProviders(
      <ErrorBoundary>
        <Broken fail />
      </ErrorBoundary>,
    );
    expect(console.error).toHaveBeenCalledWith(
      'Rendering failed',
      expect.objectContaining({ message: 'secret internal detail' }),
      expect.any(String),
    );
  });

  it('starts over when it gets a new key (the layout keys it by route)', () => {
    const { rerender } = renderWithProviders(
      <ErrorBoundary key="a">
        <Broken fail />
      </ErrorBoundary>,
    );
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    rerender(
      <ErrorBoundary key="b">
        <Broken fail={false} />
      </ErrorBoundary>,
    );
    expect(screen.getByText('All good')).toBeInTheDocument();
  });
});
```

Create `frontend/src/components/AppLayout.test.tsx`:

```tsx
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router';
import { describe, expect, it, vi } from 'vitest';

import { AuthContext, type AuthContextValue } from '../auth/authContext';
import { RealtimeContext } from '../realtime/realtimeContext';
import { renderWithProviders } from '../test/render';
import { AppLayout } from './AppLayout';

function renderLayout(logout = vi.fn()) {
  const auth: AuthContextValue = {
    status: 'authenticated',
    sessionExpired: false,
    login: () => Promise.resolve(),
    logout,
    retry: () => {},
  };
  renderWithProviders(
    <AuthContext value={auth}>
      <RealtimeContext value={{ kind: 'connected' }}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<p>Home content</p>} />
            <Route path="build" element={<p>Build content page</p>} />
          </Route>
        </Routes>
      </RealtimeContext>
    </AuthContext>,
  );
  return logout;
}

describe('AppLayout', () => {
  it('frames the page with the wordmark, navigation and the connection state', () => {
    renderLayout();
    expect(screen.getByRole('heading', { name: /Bunshō/ })).toBeInTheDocument();
    expect(document.querySelector('span[lang="ja"]')).toHaveTextContent('文章');
    expect(screen.getByRole('link', { name: 'Home' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Build content' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Live');
    expect(screen.getByText('Home content')).toBeInTheDocument();
  });

  it('navigates between pages', async () => {
    renderLayout();
    await userEvent.click(screen.getByRole('link', { name: 'Build content' }));
    expect(screen.getByText('Build content page')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: 'Home' }));
    expect(screen.getByText('Home content')).toBeInTheDocument();
  });

  it('logs out on request', async () => {
    const logout = renderLayout();
    await userEvent.click(screen.getByRole('button', { name: 'Log out' }));
    expect(logout).toHaveBeenCalledTimes(1);
  });

  it('has a theme toggle', () => {
    renderLayout();
    expect(screen.getByRole('radio', { name: 'Dark' })).toBeInTheDocument();
  });
});
```

Create `frontend/src/features/home/HomePage.test.tsx`:

```tsx
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it } from 'vitest';

import { session } from '../../auth/session';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { HomePage } from './HomePage';

const BUILT = {
  built: true,
  kana: 208,
  kanji: 3088,
  vocab: 7734,
  unleveled_kanji: 979,
  kanji_by_level: { N5: 480, N4: 352, N3: 544, N2: 357, N1: 376 },
  vocab_by_level: { N5: 667, N4: 630, N3: 1647, N2: 1737, N1: 3053 },
  meta: {},
};

function renderHome() {
  return renderWithProviders(
    <Routes>
      <Route index element={<HomePage />} />
      <Route path="build" element={<p>Build page</p>} />
    </Routes>,
  );
}

describe('HomePage', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  it('shows the totals and the per-level table of built content', async () => {
    server.use(http.get('/api/v1/content/summary', () => HttpResponse.json(BUILT)));
    renderHome();
    expect(await screen.findByRole('heading', { name: 'Your content' })).toBeInTheDocument();
    expect(screen.getByText('208')).toBeInTheDocument();
    expect(screen.getByText('3,088')).toBeInTheDocument();
    expect(screen.getByText('7,734')).toBeInTheDocument();
    expect(screen.getByText('979 not in the JLPT vocabulary')).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Items per JLPT level' });
    const n5 = within(table).getByRole('row', { name: /N5/ });
    expect(within(n5).getByText('667')).toBeInTheDocument();
    expect(within(n5).getByText('480')).toBeInTheDocument();
  });

  it('invites a first-time user to build the content', async () => {
    server.use(
      http.get('/api/v1/content/summary', () =>
        HttpResponse.json({
          ...BUILT,
          built: false,
          kana: 0,
          kanji: 0,
          vocab: 0,
          unleveled_kanji: 0,
          kanji_by_level: {},
          vocab_by_level: {},
        }),
      ),
    );
    renderHome();
    expect(await screen.findByText('Welcome to Bunshō')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: 'Build your content' }));
    expect(screen.getByText('Build page')).toBeInTheDocument();
  });

  it('says what went wrong and lets the user try again', async () => {
    server.use(
      http.get('/api/v1/content/summary', () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    );
    renderHome();
    expect(await screen.findByText("Couldn't load the content summary")).toBeInTheDocument();
    expect(screen.getByText(/server had a problem/i)).toBeInTheDocument();

    server.use(http.get('/api/v1/content/summary', () => HttpResponse.json(BUILT)));
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('heading', { name: 'Your content' })).toBeInTheDocument();
  });
});
```

Create `frontend/src/App.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { App } from './App';
import { REFRESH_TOKEN_KEY, session } from './auth/session';
import { FakeSocket } from './test/fakeSocket';
import { server } from './test/server';

const TOKENS = { access_token: 'a2', refresh_token: 'r2', token_type: 'bearer', expires_in: 900 };
const SUMMARY = {
  built: true,
  kana: 208,
  kanji: 3088,
  vocab: 7734,
  unleveled_kanji: 979,
  kanji_by_level: { N5: 480, N4: 352, N3: 544, N2: 357, N1: 376 },
  vocab_by_level: { N5: 667, N4: 630, N3: 1647, N2: 1737, N1: 3053 },
  meta: {},
};

function rememberLogin() {
  window.localStorage.setItem(REFRESH_TOKEN_KEY, 'r1');
  server.use(
    http.post('/api/v1/auth/refresh', () => HttpResponse.json(TOKENS)),
    http.get('/api/v1/content/summary', () => HttpResponse.json(SUMMARY)),
    http.get('/api/v1/admin/config-check', () => HttpResponse.json({ ok: true, checks: [] })),
    http.get('/api/v1/admin/content/build', () =>
      HttpResponse.json({ detail: 'no build has run yet' }, { status: 404 }),
    ),
  );
}

function goTo(path: string) {
  window.history.pushState({}, '', path);
}

describe('App', () => {
  beforeEach(() => {
    session.clear();
    vi.stubGlobal('WebSocket', FakeSocket); // no real connection attempts from the live stream
    goTo('/');
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends a visitor without a login to the login page', async () => {
    render(<App />);
    expect(await screen.findByLabelText('Username')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/login');
  });

  it('opens straight on the home page for a remembered login', async () => {
    rememberLogin();
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Your content' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Bunshō/ })).toBeInTheDocument();
  });

  it('navigates to the build page and back', async () => {
    rememberLogin();
    render(<App />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('link', { name: 'Build content' }));
    expect(await screen.findByRole('heading', { name: 'Content' })).toBeInTheDocument();
    expect(window.location.pathname).toBe('/build');
    await user.click(screen.getByRole('link', { name: 'Home' }));
    expect(await screen.findByRole('heading', { name: 'Your content' })).toBeInTheDocument();
  });

  it('serves a deep link after the login is restored', async () => {
    rememberLogin();
    goTo('/build');
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Content' })).toBeInTheDocument();
  });

  it('answers an unknown address with a not-found page', async () => {
    rememberLogin();
    goTo('/nothing/here');
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument();
  });

  it('logs out and forgets the remembered login', async () => {
    rememberLogin();
    render(<App />);
    await userEvent.click(await screen.findByRole('button', { name: 'Log out' }));
    expect(await screen.findByLabelText('Username')).toBeInTheDocument();
    expect(window.localStorage.getItem(REFRESH_TOKEN_KEY)).toBeNull();
    await waitFor(() => {
      expect(window.location.pathname).toBe('/login');
    });
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm test`
Expected: FAIL (modules not found; the old `App.test.tsx` from Task 3 is replaced by this one).

- [ ] **Step 3: Implement (verified files)**

Create `frontend/src/components/ColorSchemeToggle.tsx`:

```tsx
import { SegmentedControl, useMantineColorScheme } from '@mantine/core';

/** Light, dark or follow the system. Mantine remembers the choice in localStorage. */
export function ColorSchemeToggle() {
  const { colorScheme, setColorScheme } = useMantineColorScheme();
  return (
    <SegmentedControl
      size="xs"
      aria-label="Colour theme"
      value={colorScheme}
      onChange={(value) => {
        if (value === 'light' || value === 'dark' || value === 'auto') setColorScheme(value);
      }}
      data={[
        { label: 'Light', value: 'light' },
        { label: 'Dark', value: 'dark' },
        { label: 'Auto', value: 'auto' },
      ]}
    />
  );
}
```

Create `frontend/src/components/ErrorBoundary.tsx`:

```tsx
import { Button, Center, Stack, Text, Title } from '@mantine/core';
import { Component, type ErrorInfo, type ReactNode } from 'react';

interface ErrorBoundaryState {
  failed: boolean;
}

/**
 * Catches rendering errors below it and shows a friendly page instead of a blank screen. It never
 * shows the error itself (no stack traces); the details go to the browser console. Give it a
 * `key` that changes on navigation so leaving the broken page resets it.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, ErrorBoundaryState> {
  state: ErrorBoundaryState = { failed: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Rendering failed', error, info.componentStack);
  }

  render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    return (
      <Center mih={320}>
        <Stack align="center" gap="xs">
          <Title order={3}>Something went wrong</Title>
          <Text c="dimmed">This page could not be shown. Reloading usually fixes it.</Text>
          <Button
            onClick={() => {
              window.location.reload();
            }}
          >
            Reload the page
          </Button>
        </Stack>
      </Center>
    );
  }
}
```

Create `frontend/src/features/NotFoundPage.tsx`:

```tsx
import { Button, Center, Stack, Text, Title } from '@mantine/core';
import { Link } from 'react-router';

export function NotFoundPage() {
  return (
    <Center mih={320}>
      <Stack align="center" gap="xs">
        <Title order={2}>Page not found</Title>
        <Text c="dimmed">There is nothing at this address.</Text>
        <Button component={Link} to="/">
          Back to Home
        </Button>
      </Stack>
    </Center>
  );
}
```

Create `frontend/src/components/AppLayout.tsx`:

```tsx
import { AppShell, Burger, Button, Group, NavLink, Title } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { Link, Outlet, useLocation } from 'react-router';

import { useAuth } from '../auth/authContext';
import { ConnectionBadge } from '../realtime/ConnectionBadge';
import { ColorSchemeToggle } from './ColorSchemeToggle';
import { ErrorBoundary } from './ErrorBoundary';

const NAVIGATION = [
  { to: '/', label: 'Home' },
  { to: '/build', label: 'Build content' },
] as const;

/** The frame around every logged-in page: header, navigation and the page itself. */
export function AppLayout() {
  const [opened, { toggle, close }] = useDisclosure(false);
  const { logout } = useAuth();
  const { pathname } = useLocation();

  return (
    <AppShell
      header={{ height: 56 }}
      navbar={{ width: 220, breakpoint: 'sm', collapsed: { mobile: !opened } }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger
              opened={opened}
              onClick={toggle}
              hiddenFrom="sm"
              size="sm"
              aria-label="Toggle navigation"
            />
            <Title order={3}>
              Bunshō <span lang="ja">文章</span>
            </Title>
          </Group>
          <Group gap="xs" wrap="nowrap">
            <ConnectionBadge />
            <ColorSchemeToggle />
            <Button
              variant="subtle"
              onClick={logout}
              title="Logs out this browser only; the server cannot end sessions yet"
            >
              Log out
            </Button>
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="md">
        {NAVIGATION.map((item) => (
          <NavLink
            key={item.to}
            component={Link}
            to={item.to}
            label={item.label}
            active={pathname === item.to}
            onClick={close}
          />
        ))}
      </AppShell.Navbar>
      <AppShell.Main>
        <ErrorBoundary key={pathname}>
          <Outlet />
        </ErrorBoundary>
      </AppShell.Main>
    </AppShell>
  );
}
```

Create `frontend/src/features/home/HomePage.tsx`:

```tsx
import {
  Alert,
  Button,
  Paper,
  SimpleGrid,
  Skeleton,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { Link } from 'react-router';

import { messageFor } from '../../api/errors';
import { useContentSummary } from '../../api/queries';
import { formatCount } from '../build/format';

const LEVELS = ['N5', 'N4', 'N3', 'N2', 'N1'] as const;

function Stat({ label, value, note }: { label: string; value: number; note?: string }) {
  return (
    <Paper withBorder p="md">
      <Text size="sm" c="dimmed">
        {label}
      </Text>
      <Text fz={28} fw={600}>
        {formatCount(value)}
      </Text>
      {note !== undefined && (
        <Text size="xs" c="dimmed">
          {note}
        </Text>
      )}
    </Paper>
  );
}

/** What has been built so far, or an invitation to build it. */
export function HomePage() {
  const summary = useContentSummary();

  if (summary.isPending) {
    return (
      <Stack>
        <Skeleton height={32} width={220} />
        <Skeleton height={112} />
      </Stack>
    );
  }
  if (summary.isError) {
    return (
      <Alert color="red" title="Couldn't load the content summary">
        <Text size="sm">{messageFor(summary.error)}</Text>
        <Button
          mt="sm"
          size="xs"
          onClick={() => {
            void summary.refetch();
          }}
        >
          Try again
        </Button>
      </Alert>
    );
  }

  const data = summary.data;
  if (!data.built) {
    return (
      <Alert color="blue" title="Welcome to Bunshō">
        <Text size="sm">
          There is no study content yet. Build it once from the vocabulary deck and it will be here.
        </Text>
        <Button component={Link} to="/build" mt="sm" size="xs">
          Build your content
        </Button>
      </Alert>
    );
  }

  return (
    <Stack gap="md">
      <Title order={2}>Your content</Title>
      <SimpleGrid cols={{ base: 1, sm: 3 }}>
        <Stat label="Kana" value={data.kana} />
        <Stat
          label="Kanji"
          value={data.kanji}
          note={`${formatCount(data.unleveled_kanji)} not in the JLPT vocabulary`}
        />
        <Stat label="Vocabulary" value={data.vocab} />
      </SimpleGrid>
      <Table withTableBorder aria-label="Items per JLPT level">
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Level</Table.Th>
            <Table.Th ta="right">Vocabulary</Table.Th>
            <Table.Th ta="right">Kanji</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {LEVELS.map((level) => (
            <Table.Tr key={level}>
              <Table.Td>{level}</Table.Td>
              <Table.Td ta="right">{formatCount(data.vocab_by_level[level] ?? 0)}</Table.Td>
              <Table.Td ta="right">{formatCount(data.kanji_by_level[level] ?? 0)}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Stack>
  );
}
```

Create `frontend/src/App.tsx`:

```tsx
import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router';

import { AuthProvider } from './auth/AuthProvider';
import { RequireAuth } from './auth/RequireAuth';
import { AppLayout } from './components/AppLayout';
import { BuildPage } from './features/build/BuildPage';
import { HomePage } from './features/home/HomePage';
import { LoginPage } from './features/login/LoginPage';
import { NotFoundPage } from './features/NotFoundPage';
import { createQueryClient } from './queryClient';
import { RealtimeProvider } from './realtime/RealtimeProvider';
import { theme } from './theme';

import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';

export function App() {
  const [queryClient] = useState(createQueryClient);

  return (
    <MantineProvider theme={theme} defaultColorScheme="auto">
      <Notifications position="top-right" />
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AuthProvider>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route element={<RequireAuth />}>
                <Route
                  element={
                    <RealtimeProvider>
                      <AppLayout />
                    </RealtimeProvider>
                  }
                >
                  <Route index element={<HomePage />} />
                  <Route path="build" element={<BuildPage />} />
                  <Route path="*" element={<NotFoundPage />} />
                </Route>
              </Route>
            </Routes>
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </MantineProvider>
  );
}
```

- [ ] **Step 4: Run the gate**

```bash
npm run format && npm run format:check && npm run lint && npm run build && npm run coverage
```
Expected: everything passes (about 100 tests; coverage about 98% lines / 90% branches). `vite build` prints a warning that a chunk is larger than 500 kB (Mantine, router and query together); it is only a warning: record "code-split the routes" as a follow-up in `TODO.md` (Task 10) and do not raise the limit.

- [ ] **Step 5: Try it for real**

With the backend running (`uv run bunsho` with your `.env`, port 8192) run `npm run dev` in `frontend/` and open `http://localhost:5173`. Expected: the login page; after logging in, Home (or the first-run invitation), the Build page with the environment checks, a live "Live" badge in the header, and a working build with progress. Report what you saw. (If the backend cannot be started in your environment, say so; the container smoke test in Task 10 covers the deployed path.)

- [ ] **Step 6: Commit**

```bash
cd ..
git add frontend/src
git commit -m "feat: app shell, Home page and routing" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

## Task 10: Documentation, whole-branch verification and review

**Files:**
- Modify: `README.md`, `CHANGELOG.md`, `TODO.md`, `docs/superpowers/specs/2026-09-20-bunsho-2b1-frontend-skeleton-design.md` (implementation notes)

- [ ] **Step 1: Update the README**

Replace the paragraph that starts `**Frontend development.** Allow the Vite dev server with` (in the "Studying (review API)" section) with:

````markdown
**Web UI.** The Docker image contains the built web UI and serves it at `http://<host>:8192/` (log in with the credentials from your env file). Outside Docker the API serves the UI only when `paths.frontend_dir` (`BUNSHO_PATHS__FRONTEND_DIR`) points at a built `frontend/dist`; unset, it serves the API only. Unknown paths under `/api` stay JSON 404s.

**Developing the UI.** Requires Node 24 or newer. Start the backend (`uv run bunsho`), then in `frontend/`: `npm ci`, `npm run dev`, and open `http://localhost:5173`. The dev server proxies `/api` (WebSocket included) to `http://127.0.0.1:8192`, so no CORS setup is needed (set `VITE_API_TARGET` if the backend runs elsewhere). Other commands: `npm run lint`, `npm run format:check`, `npm test`, `npm run coverage`, `npm run build`. After changing the API, refresh the frontend's types: `uv run python scripts/export_openapi.py` (rewrites `frontend/openapi.json`; a unit test fails while it is stale), then `npm run gen:api`, and commit both files. The `BUNSHO_SERVER__CORS_ORIGINS` setting remains available for setups that do not use the proxy.
````
Also add to the README's "Development" section a short list of the frontend gate commands if that section lists the Python ones (match its style).

- [ ] **Step 2: CHANGELOG, TODO and spec notes**

`CHANGELOG.md`, under `## [Unreleased]` → `### Added`:

```markdown
- Web UI (`frontend/`, React with Mantine): log in (the refresh token is remembered in the browser,
  the access token only in memory), an app shell with a light, dark or system theme, a Home page
  showing what has been built, and a Build screen that runs a content build or dry run with live
  progress over the WebSocket (with reconnect and a polling fallback). The Docker image builds
  the UI in a Node stage and the service serves it (`paths.frontend_dir`), with cache and security
  headers and a fallback to `index.html` for client-side routes.
- The API's OpenAPI document is committed as `frontend/openapi.json`; a unit test fails when it is
  stale, and the frontend's TypeScript types are generated from it.
- CI: a `frontend` job (Prettier, ESLint, type-check and build, vitest with coverage, and a check
  that the generated API types are current); Dependabot updates the npm dependencies; the
  container smoke test checks that the UI is served.
```
`TODO.md`: tick the Plan 2 items now done: "Image: a Node stage…", "CI: a `frontend` job…", "Dependabot: add the `npm` entry…", "Extend the smoke test: `index.html` is served…" (edit the last one to say the review round trip was done in Plan 2A and the `index.html` check in 2B-1), "CORS: open it for the Vite dev origin" (replace with: the dev server uses a proxy, no CORS needed); update the status paragraph at the top ("Plan 2B-1 (frontend skeleton and delivery) is implemented on `feat/plan-2b1-frontend-skeleton`; Plan 2B-2 (dashboard, review, stats, settings) is next."); add these open items under a new "Plan 2B-2 and later" heading: "Dashboard, flip-and-grade review with keyboard shortcuts and furigana, statistics and settings screens (Plan 2B-2)", "Code-split the routes: the production JS chunk is over 500 kB", "Move to TypeScript 7 once `typescript-eslint` and `openapi-typescript` support it (TypeScript is pinned to 6.0.3; see the Plan 2B-1 plan)", "Content-Security-Policy header for the served UI (Mantine injects inline styles: needs nonces or hashes)", "Browser end-to-end test of the deployed UI", "Refresh-token logout/revocation on the server (the UI's Log out only clears this browser)", "The JSON 500 from unhandled errors is produced outside CORS middleware (only matters for cross-origin setups)".
Append to the spec `docs/superpowers/specs/2026-09-20-bunsho-2b1-frontend-skeleton-design.md` an "Implementation notes" section: root `lang="en"`; TypeScript 6.0.3 pin and the `overrides` entry with the reason; React Router declarative mode; task order (real-time before the shell); `SPAStaticFiles` answers 405 for non-GET methods on unknown non-API paths.

- [ ] **Step 3: Whole-branch verification**

```bash
unset VIRTUAL_ENV
uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run bandit -c pyproject.toml -r src -q
uv run pytest --cov=src/bunsho -q
cd frontend && npm ci && npm run format:check && npm run lint && npm run build && npm run coverage && cd ..
uv run python scripts/smoke_test.py
```
Expected: everything green; Python coverage at or above 90%; frontend coverage at or above 80%; the smoke test ends `[smoke] PASS` (it now also checks that the UI is served). Also confirm `git status` is clean and `git diff --exit-code -- frontend/src/api/schema.d.ts frontend/openapi.json` after re-running `uv run python scripts/export_openapi.py && (cd frontend && npm run gen:api)`.

- [ ] **Step 4: Whole-branch review (Sonnet)**

Dispatch one whole-branch review with `superpowers:requesting-code-review` on a **Sonnet** model (James: not Opus), against `main`, given the spec, this plan, "Version exceptions" and "Refinements to the spec". Ask it to check specifically: the token handling (nothing sensitive in URLs, logs, query keys or storage other than the refresh token); the single-flight refresh and its failure modes; the WebSocket reconnect logic and the 1008 path; the static-serving fallback rules (an unknown `/api` GET must stay JSON, no path traversal, headers); the Dockerfile stage (cache mounts, no dev files in the runtime image, the runtime user can read `/app/frontend`); CI job correctness (the drift check runs in the right directory); accessibility basics (labels, `aria-live` regions, focus); test quality (no real timers or network); and consistency between README, CHANGELOG, TODO and the code. Fix Critical and Important findings in one fix wave and re-review only that wave; record Minor findings in `TODO.md`.

- [ ] **Step 5: Push and prepare the PR**

```bash
git push
gh pr ready   # only when CI is green on ubuntu, windows and macOS, including the new frontend job
```
Update the draft PR description (end with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`): what was built, the resolved dependency versions and the TypeScript 6.0.3 exception with its reason, test counts and coverage (Python and frontend), the smoke-test result, and what Plan 2B-2 builds on. James reviews and merges; do not merge.
