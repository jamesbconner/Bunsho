# CSP and Security Headers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the baseline security headers and a Content-Security-Policy on every HTTP response: a strict, nonce-based policy for the served UI shell, a default-deny policy for the API and static assets, and a dedicated looser policy for `/docs` and `/redoc`.

**Architecture:** A pure `api/csp.py` holds the policy strings and the nonce generator. `SPAStaticFiles` keeps `index.html` in memory, swaps a placeholder for a fresh nonce on every shell response and leaves the nonce on the ASGI scope. A new outermost `SecurityHeadersMiddleware` adds the baseline headers and picks the CSP (shell with nonce, docs, or default-deny) when the response starts. The frontend reads the nonce from a `<meta>` tag and hands it to `MantineProvider`. A `server.csp_report_only` setting flips the header name to `Content-Security-Policy-Report-Only`. A stale UI build (no placeholder) is reported by config validation.

**Tech Stack:** Python 3.13, FastAPI/Starlette (pure ASGI middleware), pytest + `TestClient`; React, TypeScript, Mantine 9, Vite, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-26-bunsho-csp-security-headers-design.md`

## Global Constraints

- Branch `feat/csp-security-headers`, created from an up-to-date `main` (the spec is already on `main`; this plan is on `docs/csp-plan`). Never merge; James reviews and merges. Open the PR yourself when done.
- Commits: conventional commits, stage explicit paths only, `git commit -m "<subject>" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"` (the trailer is its own paragraph). Never stage `.gitignore`, `.github/`, `.python-version`, `.superpowers/`, `.env.example` (it is untracked and stays that way).
- **No version bump.** Everything goes into the existing `## [1.4.0] - 2026-09-25` CHANGELOG section (1.4.0 is untagged; James asked for this). Do not touch the date or `pyproject.toml`.
- Header values, exactly (spec, "Policies"):
  - Baseline on every HTTP response: `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`.
  - Shell CSP: `default-src 'none'; script-src 'self'; style-src 'self' 'nonce-<N>'; img-src 'self'; font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`.
  - Default CSP (API, `/openapi.json`, assets, everything else): `default-src 'none'; frame-ancestors 'none'`.
  - Docs CSP (`/docs`, `/redoc`, `/docs/oauth2-redirect`), settled against the real pages on 2026-09-26: `default-src 'none'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; img-src 'self' data: https://fastapi.tiangolo.com; font-src https://fonts.gstatic.com; worker-src blob:; connect-src 'self'; frame-ancestors 'none'`.
  - The nonce is `base64.b64encode(secrets.token_bytes(16)).decode()` (never `token_urlsafe`: `-` and `_` are not valid in a CSP nonce).
  - The nonce placeholder is the literal `__CSP_NONCE__`, in `<meta name="csp-nonce" content="__CSP_NONCE__" />`.
  - The setting is `server.csp_report_only`, env `BUNSHO_SERVER__CSP_REPORT_ONLY`, default `false`. Exactly one CSP header is ever sent (never both names).
  - No HSTS from the app. No `unsafe-inline`/`unsafe-eval` in the shell policy.
- Python: type annotations on everything public, Google-style docstrings, `ruff check .`, `ruff format --check .`, `mypy src/`, `bandit -c pyproject.toml -r src/ -l`, `pytest --cov` >= 90. Frontend: strict TypeScript, `npm run format:check`, `npm run lint`, `npm run build`, `npm run coverage`.
- Tests: no pytest-asyncio; drive async code with `asyncio.run(...)`. HTTP tests use `TestClient`. The existing fixtures `service_config`, `client` (no UI) live in `tests/base.py` / `tests/unit/api/conftest.py`.
- Windows quirks: `unset VIRTUAL_ENV` before every `uv` command; quote the `Bunshō` path; write files with the Write/Edit tools, not shell heredocs (Python edits can leave CRLF; `ruff format` fixes it; TS: `npm run format` in `frontend/`). A formatter hook may drop an import that is not used yet: add imports together with their first use.
- Subagents: this project's hook demands `graphify query "<question>"` before reading or grepping source files. Put that instruction in every subagent prompt.
- Never run the tests of a file you are still editing in the background, and do not loop tests while another agent edits files.

## Review Focus

The failure modes the spec implies but a per-task happy path would miss, most likely first. Each has a pinning test in the task named in brackets.

1. **A stale or reused nonce:** two shell requests must get different nonces, and for each the nonce in the header must equal the one in the body. A `HEAD` and a deep link must behave the same. [Task 5]
2. **The wrong policy on a near miss:** a missing asset (`/assets/missing.js`), an unknown API path (`/api/nothing`, `/api`) and a directory-like path must never get the shell policy or the shell body; they keep their 404 and the default-deny policy. `/docs/` (trailing slash) and `/docsx` must not get the loose docs policy. [Task 4, Task 5]
3. **A stale UI build:** a `frontend_dir` whose `index.html` has no placeholder must fail with the "run `npm run build`" message, not produce a blank page at run time; an empty folder or no `index.html` keeps working as before. [Task 3, Task 5]
4. **Headers missing on the unhappy paths:** 401, 404, 405, the JSON 500 and a CORS preflight must all carry the baseline headers and exactly one CSP header; an inner app that already set a header keeps its value. [Task 4]
5. **The docs pages break silently after a FastAPI upgrade:** every origin the real `/docs` and `/redoc` HTML references must be covered by the docs policy, and the docs URLs must match the constants. [Task 4]
6. **Development still works:** under `npm run dev` the meta tag still holds the literal placeholder, so no nonce is used and Mantine must not receive one. [Task 6]

---

## File Structure

| File | Responsibility |
|---|---|
| `src/bunsho/api/csp.py` (create) | Policy strings, docs paths, header names, nonce generator, scope key. Pure: no I/O, no framework imports |
| `src/bunsho/frontend_shell.py` (create) | The nonce placeholder, `read_shell`, `shell_problem`, `StaleShellError` (neutral: imported by config and by the API layer) |
| `src/bunsho/config/service.py` (modify) | `ServerSettings.csp_report_only`, parsing and validation |
| `src/bunsho/config/settings.py` (modify) | `frontend_dir` validation reports a stale shell |
| `src/bunsho/api/security_headers.py` (create) | `SecurityHeadersMiddleware`, `BASELINE_HEADERS` |
| `src/bunsho/api/static.py` (modify) | Render the shell with a nonce; drop the security-header dict, keep caching |
| `src/bunsho/api/app.py` (modify) | Add the middleware last (outermost) |
| `frontend/index.html` (modify) | The `csp-nonce` meta tag |
| `frontend/src/csp.ts` (create) | `readCspNonce()` |
| `frontend/src/App.tsx` (modify) | Pass the nonce to `MantineProvider` |
| `scripts/smoke_test.py` (modify) | Shell body is no longer byte-identical per request; assert the headers |
| `README.md`, `CHANGELOG.md`, `TODO.md`, the spec (modify) | Documentation and the settled docs policy |

---

### Task 1: `api/csp.py`: policies, nonce, header names

**Files:**
- Create: `src/bunsho/api/csp.py`
- Test: `tests/unit/api/test_csp.py`

**Interfaces:**
- Consumes: nothing.
- Produces (later tasks rely on these exact names):
  - `CSP_HEADER: str = "Content-Security-Policy"`, `CSP_REPORT_ONLY_HEADER: str = "Content-Security-Policy-Report-Only"`
  - `NONCE_SCOPE_KEY: str = "bunsho.csp_nonce"`
  - `DEFAULT_POLICY: str`, `DOCS_POLICY: str`, `DOCS_PATHS: frozenset[str]`
  - `shell_policy(nonce: str) -> str` (raises `ValueError` for anything that is not base64)
  - `header_name(report_only: bool) -> str`
  - `generate_nonce() -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/api/test_csp.py`:

```python
import base64

import pytest

from bunsho.api.csp import (
    CSP_HEADER,
    CSP_REPORT_ONLY_HEADER,
    DEFAULT_POLICY,
    DOCS_PATHS,
    DOCS_POLICY,
    NONCE_SCOPE_KEY,
    generate_nonce,
    header_name,
    shell_policy,
)

NONCE = "dGVzdC1ub25jZS0xMjM0NQ=="


def test_the_shell_policy_is_exact() -> None:
    assert shell_policy(NONCE) == (
        "default-src 'none'; script-src 'self'; "
        f"style-src 'self' 'nonce-{NONCE}'; "
        "img-src 'self'; font-src 'self'; connect-src 'self'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    )


def test_the_shell_policy_never_allows_inline_or_eval() -> None:
    policy = shell_policy(NONCE)
    assert "unsafe-inline" not in policy
    assert "unsafe-eval" not in policy


def test_the_default_policy_is_exact() -> None:
    assert DEFAULT_POLICY == "default-src 'none'; frame-ancestors 'none'"


def test_the_docs_policy_is_exact() -> None:
    assert DOCS_POLICY == (
        "default-src 'none'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
        "img-src 'self' data: https://fastapi.tiangolo.com; "
        "font-src https://fonts.gstatic.com; "
        "worker-src blob:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'"
    )


def test_the_docs_paths_are_the_three_fastapi_pages() -> None:
    assert DOCS_PATHS == frozenset({"/docs", "/redoc", "/docs/oauth2-redirect"})


@pytest.mark.parametrize("bad", ["", "a b", "x'; script-src *", "abc\n", "a-b_c", "=abc"])
def test_a_nonce_that_is_not_base64_is_refused(bad: str) -> None:
    with pytest.raises(ValueError, match="nonce"):
        shell_policy(bad)


def test_header_names() -> None:
    assert header_name(False) == CSP_HEADER == "Content-Security-Policy"
    assert header_name(True) == CSP_REPORT_ONLY_HEADER == "Content-Security-Policy-Report-Only"


def test_the_scope_key_is_namespaced() -> None:
    assert NONCE_SCOPE_KEY == "bunsho.csp_nonce"


def test_generated_nonces_are_16_random_bytes_of_valid_base64() -> None:
    nonce = generate_nonce()
    assert len(base64.b64decode(nonce, validate=True)) == 16
    assert shell_policy(nonce)  # accepted by the policy builder
    assert len({generate_nonce() for _ in range(50)}) == 50
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd "D:/Documents/Code/Bunshō" && unset VIRTUAL_ENV && uv run pytest tests/unit/api/test_csp.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'bunsho.api.csp'`.

- [ ] **Step 3: Write the implementation**

Create `src/bunsho/api/csp.py`:

```python
"""Content-Security-Policy strings, the docs paths and the per-request nonce.

A pure module (no I/O, no framework imports) so the policies are read and tested in one place.
"""

from __future__ import annotations

import base64
import re
import secrets

CSP_HEADER = "Content-Security-Policy"
CSP_REPORT_ONLY_HEADER = "Content-Security-Policy-Report-Only"

NONCE_SCOPE_KEY = "bunsho.csp_nonce"
"""Where the static layer leaves the nonce on the ASGI scope for the security-headers middleware."""

DEFAULT_POLICY = "default-src 'none'; frame-ancestors 'none'"
"""For everything that is not the app shell or a docs page: JSON and hashed assets have no active
content, and this also stops a file such as an SVG from running script if opened as a page."""

DOCS_PATHS = frozenset({"/docs", "/redoc", "/docs/oauth2-redirect"})
"""FastAPI's default documentation URLs; a test fails if the app's real URLs differ."""

DOCS_POLICY = "; ".join(
    [
        "default-src 'none'",
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com",
        "img-src 'self' data: https://fastapi.tiangolo.com",
        "font-src https://fonts.gstatic.com",
        "worker-src blob:",
        "connect-src 'self'",
        "frame-ancestors 'none'",
    ]
)
"""Swagger UI and Redoc load scripts, styles, fonts and a favicon from CDNs and run an inline
bootstrap script, so they cannot work under the shell policy. Confined to ``DOCS_PATHS``."""

_NONCE = re.compile(r"[A-Za-z0-9+/]+={0,2}")


def generate_nonce() -> str:
    """Return a fresh nonce: 16 random bytes, base64 encoded (what the CSP grammar requires).

    Returns:
        A new random nonce value.
    """
    return base64.b64encode(secrets.token_bytes(16)).decode("ascii")


def shell_policy(nonce: str) -> str:
    """Build the strict policy for the app shell with ``nonce`` allowed for styles.

    Args:
        nonce: A base64 nonce, normally from ``generate_nonce``.

    Returns:
        The ``Content-Security-Policy`` header value.

    Raises:
        ValueError: ``nonce`` is not base64 (a value with quotes or semicolons could otherwise
            inject further directives).
    """
    if _NONCE.fullmatch(nonce) is None:
        raise ValueError(f"nonce must be base64, got {nonce!r}")
    return "; ".join(
        [
            "default-src 'none'",
            "script-src 'self'",
            f"style-src 'self' 'nonce-{nonce}'",
            "img-src 'self'",
            "font-src 'self'",
            "connect-src 'self'",
            "base-uri 'none'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
    )


def header_name(report_only: bool) -> str:
    """Return the CSP header name: enforcing, or report-only when ``report_only`` is set."""
    return CSP_REPORT_ONLY_HEADER if report_only else CSP_HEADER
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/api/test_csp.py -q`
Expected: all pass.

- [ ] **Step 5: Lint and type-check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src/`
Expected: clean (run `uv run ruff format .` first if it reports formatting).

- [ ] **Step 6: Commit**

```bash
git add src/bunsho/api/csp.py tests/unit/api/test_csp.py
git commit -m "feat(api): CSP policies, docs paths and nonce generator" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: the `server.csp_report_only` setting

**Files:**
- Modify: `src/bunsho/config/service.py` (`ServerSettings`, `validate_service_config`, `load_service_config`)
- Test: `tests/unit/config/test_service_config.py`

**Interfaces:**
- Consumes: `ConfigNormalizer.get_bool(section, key, fallback)` (raises `ConfigError` on a bad value).
- Produces: `ServerSettings.csp_report_only: bool = False` (a keyword with a default, so every existing `ServerSettings(...)` call, including `tests/base.py`, keeps working).

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/config/test_service_config.py` (the `_valid` helper is defined at the top of that file):

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/config/test_service_config.py -q`
Expected: FAIL (`AttributeError: 'ServerSettings' object has no attribute 'csp_report_only'`, and the bad value is not reported).

- [ ] **Step 3: Implement**

In `src/bunsho/config/service.py`:

1. Add the field to `ServerSettings` (after `trusted_proxies`):

```python
    trusted_proxies: tuple[str, ...] = ()
    csp_report_only: bool = False
```

2. Add a helper next to `_int`:

```python
def _bool(cfg: ConfigNormalizer, section: str, key: str, fallback: bool, errors: list[str]) -> bool:
    try:
        return cfg.get_bool(section, key, fallback)
    except ConfigError as exc:
        errors.append(str(exc))
        return fallback
```

3. In `validate_service_config`, after the `trusted_proxies` loop and before the `[auth] username` check, add:

```python
    _bool(cfg, "server", "csp_report_only", False, errors)
```

4. In `load_service_config`, add to the `ServerSettings(...)` call:

```python
            trusted_proxies=_trusted_proxies(cfg),
            csp_report_only=cfg.get_bool("server", "csp_report_only", False),
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/config -q`
Expected: all pass.

- [ ] **Step 5: Lint and type-check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src/`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/bunsho/config/service.py tests/unit/config/test_service_config.py
git commit -m "feat(config): server.csp_report_only setting" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: `frontend_shell` and the stale-build check in config validation

**Files:**
- Create: `src/bunsho/frontend_shell.py`
- Modify: `src/bunsho/config/settings.py` (the `frontend_dir` block of `validate_config`, currently lines ~90-95)
- Test: `tests/unit/test_frontend_shell.py` (create), `tests/unit/config/test_settings.py` (append)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `CSP_NONCE_PLACEHOLDER: str = "__CSP_NONCE__"`, `INDEX_FILE: str = "index.html"`
  - `class StaleShellError(ValueError)`
  - `read_shell(frontend_dir: Path) -> str | None`: the text of `index.html`, `None` when the folder has no `index.html`; raises `StaleShellError` when the file lacks the placeholder.
  - `shell_problem(frontend_dir: Path) -> str | None`: the message for config validation, or `None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_frontend_shell.py`:

```python
from pathlib import Path

import pytest

from bunsho.frontend_shell import (
    CSP_NONCE_PLACEHOLDER,
    StaleShellError,
    read_shell,
    shell_problem,
)

CURRENT = f'<html><head><meta name="csp-nonce" content="{CSP_NONCE_PLACEHOLDER}" /></head></html>'


def _dist(tmp_path: Path, html: str | bytes | None) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir()
    if isinstance(html, bytes):
        (dist / "index.html").write_bytes(html)
    elif html is not None:
        (dist / "index.html").write_text(html, encoding="utf-8")
    return dist


def test_the_placeholder_is_the_documented_literal() -> None:
    assert CSP_NONCE_PLACEHOLDER == "__CSP_NONCE__"


def test_read_shell_returns_a_current_build(tmp_path: Path) -> None:
    assert read_shell(_dist(tmp_path, CURRENT)) == CURRENT


def test_read_shell_returns_none_without_an_index(tmp_path: Path) -> None:
    assert read_shell(_dist(tmp_path, None)) is None


def test_read_shell_rejects_a_build_without_the_placeholder(tmp_path: Path) -> None:
    with pytest.raises(StaleShellError, match="npm run build"):
        read_shell(_dist(tmp_path, "<html><body>old</body></html>"))


def test_a_stale_shell_error_is_a_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        read_shell(_dist(tmp_path, "<html></html>"))


def test_shell_problem_is_none_for_a_current_build(tmp_path: Path) -> None:
    assert shell_problem(_dist(tmp_path, CURRENT)) is None


def test_shell_problem_is_none_without_an_index(tmp_path: Path) -> None:
    assert shell_problem(_dist(tmp_path, None)) is None


def test_shell_problem_names_the_file_and_the_fix_for_a_stale_build(tmp_path: Path) -> None:
    problem = shell_problem(_dist(tmp_path, "<html></html>"))
    assert problem is not None
    assert "index.html" in problem
    assert CSP_NONCE_PLACEHOLDER in problem
    assert "npm run build" in problem


def test_shell_problem_reports_an_unreadable_index_instead_of_raising(tmp_path: Path) -> None:
    problem = shell_problem(_dist(tmp_path, b"\xff\xfe\x00 not utf-8"))
    assert problem is not None
    assert "index.html" in problem
```

Append to `tests/unit/config/test_settings.py`:

```python
def test_a_frontend_build_without_the_nonce_placeholder_is_reported(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>old build</body></html>", encoding="utf-8")
    errors = validate_config(ConfigNormalizer({"paths": {"frontend_dir": str(dist)}}))
    assert any("frontend_dir" in e and "npm run build" in e for e in errors)


def test_a_current_frontend_build_is_accepted(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text('<meta content="__CSP_NONCE__">', encoding="utf-8")
    errors = validate_config(ConfigNormalizer({"paths": {"frontend_dir": str(dist)}}))
    assert not any("frontend_dir" in e for e in errors)


def test_a_frontend_folder_without_an_index_is_not_reported(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()  # the existing behaviour: only "is a directory" is checked
    errors = validate_config(ConfigNormalizer({"paths": {"frontend_dir": str(dist)}}))
    assert not any("frontend_dir" in e for e in errors)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_frontend_shell.py tests/unit/config/test_settings.py -q`
Expected: collection error for `bunsho.frontend_shell`; the new settings test for a stale build fails.

- [ ] **Step 3: Write the implementation**

Create `src/bunsho/frontend_shell.py`:

```python
"""The built web UI's ``index.html`` and the nonce placeholder it must contain.

A neutral module: both the config validation and the API's static layer import it, so the
config layer never has to import from the API layer.
"""

from __future__ import annotations

from pathlib import Path

CSP_NONCE_PLACEHOLDER = "__CSP_NONCE__"
"""Written into ``frontend/index.html``; the server swaps it for a fresh nonce on every request."""

INDEX_FILE = "index.html"


class StaleShellError(ValueError):
    """``index.html`` has no nonce placeholder: it comes from an older build of the UI."""


def read_shell(frontend_dir: Path) -> str | None:
    """Return the text of ``frontend_dir/index.html``.

    Args:
        frontend_dir: The folder with the built UI.

    Returns:
        The file's text, or ``None`` when the folder has no ``index.html``.

    Raises:
        StaleShellError: The file has no ``CSP_NONCE_PLACEHOLDER``.
        OSError: The file cannot be read.
        UnicodeDecodeError: The file is not UTF-8.
    """
    index = frontend_dir / INDEX_FILE
    if not index.is_file():
        return None
    text = index.read_text(encoding="utf-8")
    if CSP_NONCE_PLACEHOLDER not in text:
        raise StaleShellError(
            f"{index} does not contain the {CSP_NONCE_PLACEHOLDER} placeholder, so it comes from "
            "an older build of the UI; rebuild it with 'npm run build' in frontend/"
        )
    return text


def shell_problem(frontend_dir: Path) -> str | None:
    """Describe what is wrong with the built shell for config validation.

    Args:
        frontend_dir: The folder with the built UI.

    Returns:
        A message, or ``None`` when the shell is fine or there is no ``index.html`` to check.
    """
    try:
        read_shell(frontend_dir)
    except StaleShellError as exc:
        return str(exc)
    except (OSError, UnicodeDecodeError) as exc:
        return f"{frontend_dir / INDEX_FILE} cannot be read ({type(exc).__name__})"
    return None
```

In `src/bunsho/config/settings.py`, add `from bunsho.frontend_shell import shell_problem` to the imports and replace the `frontend_dir` block of `validate_config`:

```python
    frontend = cfg.get_string("paths", "frontend_dir")
    if frontend and not Path(frontend).is_dir():
        errors.append(
            f"[paths] frontend_dir={frontend!r} is not a directory; build the UI with "
            "'npm run build' in frontend/, or unset it to serve the API only"
        )
    elif frontend and (problem := shell_problem(Path(frontend))):
        errors.append(f"[paths] frontend_dir={frontend!r}: {problem}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_frontend_shell.py tests/unit/config -q`
Expected: all pass (the existing empty-`dist` test keeps passing: no `index.html` is not reported).

- [ ] **Step 5: Lint and type-check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src/`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/bunsho/frontend_shell.py src/bunsho/config/settings.py tests/unit/test_frontend_shell.py tests/unit/config/test_settings.py
git commit -m "feat(config): report a UI build that has no CSP nonce placeholder" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: `SecurityHeadersMiddleware` and wiring

**Files:**
- Create: `src/bunsho/api/security_headers.py`
- Modify: `src/bunsho/api/app.py` (import, and one `add_middleware` call)
- Test: `tests/unit/api/test_security_headers_middleware.py` (ASGI level), `tests/unit/api/test_security_headers.py` (app level)

**Interfaces:**
- Consumes: from Task 1, `DEFAULT_POLICY`, `DOCS_PATHS`, `DOCS_POLICY`, `NONCE_SCOPE_KEY`, `header_name`, `shell_policy`; from Task 2, `ServerSettings.csp_report_only`.
- Produces: `BASELINE_HEADERS: dict[str, str]`; `SecurityHeadersMiddleware(app: ASGIApp, *, report_only: bool = False)`.

- [ ] **Step 1: Write the failing ASGI-level tests**

Create `tests/unit/api/test_security_headers_middleware.py`:

```python
import asyncio

import pytest
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bunsho.api.csp import DEFAULT_POLICY, DOCS_POLICY, NONCE_SCOPE_KEY, shell_policy
from bunsho.api.security_headers import BASELINE_HEADERS, SecurityHeadersMiddleware

BASELINE = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
}


def _scope(path: str = "/api/v1/health", kind: str = "http") -> Scope:
    return {"type": kind, "path": path, "method": "GET", "headers": []}


def _responding(headers: list[tuple[str, str]] | None = None, *, nonce: str | None = None) -> ASGIApp:
    """An app that answers 200 with ``headers``; optionally leaves a nonce on the scope first."""

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        if nonce is not None:
            scope[NONCE_SCOPE_KEY] = nonce
        raw = [(k.encode(), v.encode()) for k, v in headers or []]
        await send({"type": "http.response.start", "status": 200, "headers": raw})
        await send({"type": "http.response.body", "body": b""})

    return app


def _headers(app: ASGIApp, scope: Scope, *, report_only: bool = False) -> dict[str, str]:
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request"}

    async def send(message: Message) -> None:
        sent.append(message)

    asyncio.run(SecurityHeadersMiddleware(app, report_only=report_only)(scope, receive, send))
    start = next(m for m in sent if m["type"] == "http.response.start")
    return {k.decode().lower(): v.decode() for k, v in start["headers"]}


def test_the_baseline_headers_are_a_documented_constant() -> None:
    assert {k.lower(): v for k, v in BASELINE_HEADERS.items()} == BASELINE


def test_a_plain_response_gets_the_baseline_and_the_default_policy() -> None:
    headers = _headers(_responding(), _scope())
    for name, value in BASELINE.items():
        assert headers[name] == value
    assert headers["content-security-policy"] == DEFAULT_POLICY


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/docs/oauth2-redirect"])
def test_the_docs_pages_get_the_docs_policy(path: str) -> None:
    assert _headers(_responding(), _scope(path))["content-security-policy"] == DOCS_POLICY


@pytest.mark.parametrize("path", ["/docs/", "/docsx", "/redoc/x", "/api/docs", "/", "/docs/other"])
def test_near_misses_do_not_get_the_loose_docs_policy(path: str) -> None:
    assert _headers(_responding(), _scope(path))["content-security-policy"] == DEFAULT_POLICY


def test_a_nonce_left_on_the_scope_selects_the_shell_policy() -> None:
    headers = _headers(_responding(nonce="YWJjZA=="), _scope("/build"))
    assert headers["content-security-policy"] == shell_policy("YWJjZA==")


def test_the_nonce_is_read_when_the_response_starts_not_when_the_request_arrives() -> None:
    # The inner app sets the nonce while handling the request; the middleware must still see it.
    headers = _headers(_responding(nonce="ZWZnaA=="), _scope("/"))
    assert "'nonce-ZWZnaA=='" in headers["content-security-policy"]


def test_the_shell_policy_wins_over_the_docs_path_rule() -> None:
    headers = _headers(_responding(nonce="YWJjZA=="), _scope("/docs"))
    assert headers["content-security-policy"] == shell_policy("YWJjZA==")


def test_report_only_sends_the_report_only_header_and_never_both() -> None:
    headers = _headers(_responding(), _scope(), report_only=True)
    assert headers["content-security-policy-report-only"] == DEFAULT_POLICY
    assert "content-security-policy" not in headers


def test_enforcing_mode_never_sends_the_report_only_header() -> None:
    assert "content-security-policy-report-only" not in _headers(_responding(), _scope())


def test_headers_the_inner_app_already_set_are_kept() -> None:
    inner = _responding(
        [("X-Frame-Options", "SAMEORIGIN"), ("Content-Security-Policy", "default-src 'self'")]
    )
    headers = _headers(inner, _scope())
    assert headers["x-frame-options"] == "SAMEORIGIN"
    assert headers["content-security-policy"] == "default-src 'self'"
    assert headers["x-content-type-options"] == "nosniff"  # the gaps are still filled


def test_a_response_start_without_a_headers_key_still_gets_them() -> None:
    async def bare(_scope: Scope, _receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 204})
        await send({"type": "http.response.body", "body": b""})

    headers = _headers(bare, _scope())
    assert headers["x-frame-options"] == "DENY"
    assert headers["content-security-policy"] == DEFAULT_POLICY


def test_body_messages_are_passed_through_untouched() -> None:
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request"}

    async def send(message: Message) -> None:
        sent.append(message)

    asyncio.run(SecurityHeadersMiddleware(_responding())(_scope(), receive, send))
    assert sent[1] == {"type": "http.response.body", "body": b""}


@pytest.mark.parametrize("kind", ["websocket", "lifespan"])
def test_other_scopes_pass_through_without_touching_messages(kind: str) -> None:
    sent: list[Message] = []

    async def app(_scope: Scope, _receive: Receive, send: Send) -> None:
        await send({"type": "websocket.accept", "headers": []})

    async def receive() -> Message:
        return {"type": "websocket.connect"}

    async def send(message: Message) -> None:
        sent.append(message)

    asyncio.run(SecurityHeadersMiddleware(app)(_scope(kind=kind), receive, send))
    assert sent == [{"type": "websocket.accept", "headers": []}]
```

- [ ] **Step 2: Write the failing app-level tests**

Create `tests/unit/api/test_security_headers.py`:

```python
import dataclasses
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from bunsho.api.app import create_app
from bunsho.api.csp import DEFAULT_POLICY, DOCS_PATHS, DOCS_POLICY
from bunsho.config.service import ServiceConfig
from tests.base import make_service_config

ORIGIN = "http://localhost:5173"
BASELINE = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
}


def _boom() -> None:
    raise RuntimeError("secret")


def _assert_secured(response: Response, policy: str = DEFAULT_POLICY) -> None:
    for name, value in BASELINE.items():
        assert response.headers[name] == value
    assert response.headers["content-security-policy"] == policy
    assert "content-security-policy-report-only" not in response.headers


@pytest.mark.parametrize(
    "path", ["/api/v1/health", "/openapi.json", "/api/v1/does-not-exist", "/nothing/at/all"]
)
def test_api_and_schema_responses_carry_the_headers_and_default_policy(
    client: TestClient, path: str
) -> None:
    _assert_secured(client.get(path))


def test_an_unauthorized_response_is_secured(client: TestClient) -> None:
    response = client.get("/api/v1/reviews/next")
    assert response.status_code == 401
    _assert_secured(response)


def test_a_method_not_allowed_response_is_secured(client: TestClient) -> None:
    response = client.post("/api/v1/health", json={})
    assert response.status_code == 405
    _assert_secured(response)


@pytest.mark.parametrize("path", sorted(DOCS_PATHS))
def test_the_docs_pages_carry_the_docs_policy(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    _assert_secured(response, DOCS_POLICY)


def test_the_docs_paths_match_the_apps_real_urls(service_config: ServiceConfig) -> None:
    app = create_app(service_config)
    assert {app.docs_url, app.redoc_url, app.swagger_ui_oauth2_redirect_url} == DOCS_PATHS


def test_every_origin_the_docs_pages_load_from_is_allowed_by_the_docs_policy(
    client: TestClient,
) -> None:
    for path in ("/docs", "/redoc"):
        response = client.get(path)
        origins = set(re.findall(r"https?://[^/\"' )>?]+", response.text))
        assert origins, f"{path} references no external origin: the pattern needs a look"
        for origin in origins:
            assert origin in response.headers["content-security-policy"], (
                f"{path} loads from {origin}, which the docs policy does not allow; a FastAPI "
                "upgrade probably changed the page: update DOCS_POLICY and the spec"
            )


@pytest.fixture
def failing_client(service_config: ServiceConfig) -> Iterator[TestClient]:
    app = create_app(service_config)
    app.add_api_route("/boom", _boom)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_the_json_500_is_secured(failing_client: TestClient) -> None:
    response = failing_client.get("/boom")
    assert response.status_code == 500
    _assert_secured(response)


def test_a_cors_preflight_is_secured(tmp_path: Path) -> None:
    config = make_service_config(tmp_path, cors_origins=(ORIGIN,))
    preflight = {"Origin": ORIGIN, "Access-Control-Request-Method": "GET"}
    with TestClient(create_app(config)) as client:
        response = client.options("/api/v1/health", headers=preflight)
    assert response.status_code == 200
    _assert_secured(response)


def test_report_only_mode_sends_only_the_report_only_header(service_config: ServiceConfig) -> None:
    server = dataclasses.replace(service_config.server, csp_report_only=True)
    config = dataclasses.replace(service_config, server=server)
    with TestClient(create_app(config)) as client:
        response = client.get("/api/v1/health")
    assert response.headers["content-security-policy-report-only"] == DEFAULT_POLICY
    assert "content-security-policy" not in response.headers
    for name, value in BASELINE.items():
        assert response.headers[name] == value
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/api/test_security_headers_middleware.py tests/unit/api/test_security_headers.py -q`
Expected: collection error for `bunsho.api.security_headers`.

- [ ] **Step 4: Write the implementation**

Create `src/bunsho/api/security_headers.py`:

```python
"""Security headers on every HTTP response, and the Content-Security-Policy for each kind."""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bunsho.api.csp import (
    DEFAULT_POLICY,
    DOCS_PATHS,
    DOCS_POLICY,
    NONCE_SCOPE_KEY,
    header_name,
    shell_policy,
)

BASELINE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


class SecurityHeadersMiddleware:
    """Add the baseline headers and a CSP to every HTTP response.

    Add it last in ``create_app`` so it is the outermost user middleware: it then covers static
    files, API responses, the docs pages, CORS preflights and the JSON 500. It only fills gaps: a
    header the inner app already set keeps its value. WebSocket and lifespan scopes are not
    touched.

    Which CSP a response gets: the strict shell policy when the static layer left a nonce on the
    scope while serving the app shell, the docs policy on the docs paths, else default-deny.
    """

    def __init__(self, app: ASGIApp, *, report_only: bool = False) -> None:
        """Wrap ``app``.

        Args:
            app: The ASGI application to wrap.
            report_only: Send ``Content-Security-Policy-Report-Only`` instead of the enforcing
                header (never both).
        """
        self._app = app
        self._csp_header = header_name(report_only)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Run the wrapped app, adding the headers when the response starts."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        async def add_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                headers = MutableHeaders(scope=message)
                for name, value in BASELINE_HEADERS.items():
                    headers.setdefault(name, value)
                headers.setdefault(self._csp_header, self._policy_for(scope))
            await send(message)

        await self._app(scope, receive, add_headers)

    @staticmethod
    def _policy_for(scope: Scope) -> str:
        """Pick the CSP for this request; read at response start, when the nonce is known."""
        nonce = scope.get(NONCE_SCOPE_KEY)
        if nonce:
            return shell_policy(nonce)
        if scope.get("path") in DOCS_PATHS:
            return DOCS_POLICY
        return DEFAULT_POLICY
```

In `src/bunsho/api/app.py`, add the import next to the other `bunsho.api` imports:

```python
from bunsho.api.security_headers import SecurityHeadersMiddleware
```

and add the middleware as the **last** `add_middleware` call (after the CORS block, before `add_exception_handler`):

```python
    # Added last so it is the outermost user middleware and covers every response, CORS
    # preflights and the JSON 500 included.
    app.add_middleware(SecurityHeadersMiddleware, report_only=config.server.csp_report_only)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/api/test_security_headers_middleware.py tests/unit/api/test_security_headers.py -q`
Expected: all pass.

- [ ] **Step 6: Run the whole API test folder (regressions: static, CORS, error handlers, websockets)**

Run: `uv run pytest tests/unit/api -q`
Expected: all pass. `test_static.py` still passes here because `SPAStaticFiles` still sets its own headers (Task 5 removes them); the middleware only fills gaps.

- [ ] **Step 7: Lint and type-check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src/`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add src/bunsho/api/security_headers.py src/bunsho/api/app.py tests/unit/api/test_security_headers_middleware.py tests/unit/api/test_security_headers.py
git commit -m "feat(api): security headers and a CSP on every response" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: render the app shell with a per-request nonce

**Files:**
- Modify: `src/bunsho/api/static.py`
- Modify: `tests/unit/api/test_static.py`

**Interfaces:**
- Consumes: from Task 1, `NONCE_SCOPE_KEY`, `generate_nonce`, `DEFAULT_POLICY`, `shell_policy`; from Task 3, `CSP_NONCE_PLACEHOLDER`, `read_shell`, `StaleShellError`; from Task 4, the middleware (already wired in `create_app`).
- Produces: `SPAStaticFiles(directory=..., html=True)` unchanged for callers; it now raises `StaleShellError` (a `ValueError`) at construction for a stale `index.html`, renders the shell per request, and no longer sets any security header itself.

- [ ] **Step 1: Rewrite the tests**

Replace the top of `tests/unit/api/test_static.py` (imports, constants, fixtures) and the first three tests, and add the new ones below. The tests from `test_other_files_are_served_but_not_cached` onward stay as they are except where shown.

Imports and constants:

```python
import dataclasses
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from bunsho.api.app import create_app
from bunsho.api.csp import DEFAULT_POLICY, shell_policy
from bunsho.api.static import SPAStaticFiles
from bunsho.config.service import ServiceConfig
from bunsho.frontend_shell import CSP_NONCE_PLACEHOLDER, StaleShellError

INDEX_HTML = (
    '<!doctype html><html><head><meta name="csp-nonce" content="__CSP_NONCE__" /></head>'
    '<body><div id="root"></div></body></html>'
)
SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
}
NONCE_IN_POLICY = re.compile(r"'nonce-([A-Za-z0-9+/=]+)'")
NONCE_IN_BODY = re.compile(r'name="csp-nonce" content="([^"]*)"')


def shell_nonce(response: Response) -> str:
    """The nonce in the CSP header; asserts it is the same one the page body carries."""
    header = NONCE_IN_POLICY.search(response.headers["content-security-policy"])
    body = NONCE_IN_BODY.search(response.text)
    assert header is not None, "the shell's CSP carries no nonce"
    assert body is not None, "the shell body carries no csp-nonce meta tag"
    assert header.group(1) == body.group(1)
    return header.group(1)
```

The `dist` and `ui_client` fixtures are unchanged. Replace `test_the_root_serves_the_app_shell_without_caching` and `test_client_side_routes_fall_back_to_the_shell` with:

```python
def test_the_root_serves_the_shell_with_a_nonce_and_no_caching(ui_client: TestClient) -> None:
    response = ui_client.get("/")
    assert response.status_code == 200
    nonce = shell_nonce(response)
    assert response.text == INDEX_HTML.replace(CSP_NONCE_PLACEHOLDER, nonce)
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["content-security-policy"] == shell_policy(nonce)
    for name, value in SECURITY_HEADERS.items():
        assert response.headers[name] == value


@pytest.mark.parametrize("path", ["/build", "/some/nested/route", "/login", "/index.html"])
def test_client_side_routes_and_index_get_the_shell_with_a_nonce(
    ui_client: TestClient, path: str
) -> None:
    response = ui_client.get(path)
    assert response.status_code == 200
    nonce = shell_nonce(response)
    assert response.text == INDEX_HTML.replace(CSP_NONCE_PLACEHOLDER, nonce)
    assert response.headers["cache-control"] == "no-cache"


def test_every_shell_response_gets_a_fresh_nonce(ui_client: TestClient) -> None:
    nonces = [shell_nonce(ui_client.get(path)) for path in ["/", "/", "/build", "/build", "/login"]]
    assert len(set(nonces)) == len(nonces)


def test_the_placeholder_never_reaches_the_client(ui_client: TestClient) -> None:
    for path in ["/", "/build", "/index.html"]:
        assert CSP_NONCE_PLACEHOLDER not in ui_client.get(path).text


def test_head_on_the_shell_is_secured_and_has_a_nonce(ui_client: TestClient) -> None:
    response = ui_client.head("/")
    assert response.status_code == 200
    assert NONCE_IN_POLICY.search(response.headers["content-security-policy"])
```

Update the asset tests:

```python
def test_hashed_assets_are_cached_forever_and_get_no_nonce(ui_client: TestClient) -> None:
    response = ui_client.get("/assets/app-abc123.js")
    assert response.status_code == 200
    assert response.text == "console.log(1);"
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == DEFAULT_POLICY


def test_other_files_are_served_but_not_cached_and_get_no_nonce(ui_client: TestClient) -> None:
    response = ui_client.get("/favicon.svg")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["content-security-policy"] == DEFAULT_POLICY
```

Add the near-miss and startup tests at the end of the file:

```python
@pytest.mark.parametrize("path", ["/assets/missing.js", "/nope.png", "/api/nothing", "/api"])
def test_a_404_never_gets_the_shell_body_or_policy(ui_client: TestClient, path: str) -> None:
    response = ui_client.get(path)
    assert response.status_code == 404
    assert "nonce" not in response.headers["content-security-policy"]
    assert CSP_NONCE_PLACEHOLDER not in response.text
    assert response.headers["content-security-policy"] == DEFAULT_POLICY


def test_a_stale_build_is_refused_when_the_files_are_constructed(tmp_path: Path) -> None:
    stale = tmp_path / "stale"
    stale.mkdir()
    (stale / "index.html").write_text("<html><body>old</body></html>", encoding="utf-8")
    with pytest.raises(StaleShellError, match="npm run build"):
        SPAStaticFiles(directory=stale, html=True)


def test_create_app_refuses_a_stale_build(service_config: ServiceConfig, tmp_path: Path) -> None:
    stale = tmp_path / "stale"
    stale.mkdir()
    (stale / "index.html").write_text("<html><body>old</body></html>", encoding="utf-8")
    app_config = dataclasses.replace(service_config.app, frontend_dir=stale)
    with pytest.raises(ValueError, match="npm run build"):
        create_app(dataclasses.replace(service_config, app=app_config))


def test_a_folder_without_an_index_keeps_its_old_behaviour(
    service_config: ServiceConfig, tmp_path: Path
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    app_config = dataclasses.replace(service_config.app, frontend_dir=empty)
    config = dataclasses.replace(service_config, app=app_config)
    with TestClient(create_app(config)) as client:
        assert client.get("/favicon.svg").status_code == 200
        assert client.get("/").status_code == 404
        assert client.get("/build").status_code == 404
```

Keep `test_missing_files_are_a_404_not_the_shell`, `test_unknown_api_paths_keep_their_json_404`, `test_api_routes_docs_and_the_schema_still_win`, `test_head_works_and_other_methods_are_refused`, `test_a_path_traversal_cannot_leave_the_frontend_folder` and `test_without_a_frontend_folder_the_root_is_a_plain_json_404` unchanged.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/api/test_static.py -q`
Expected: failures (`shell_nonce` finds no nonce in the header; `StaleShellError` not raised; imports of `SPAStaticFiles` behaviour).

- [ ] **Step 3: Write the implementation**

Replace `src/bunsho/api/static.py` with:

```python
"""Serving the built frontend: hashed assets, the app shell with a per-request CSP nonce, and the
deep-link fallback."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from starlette.exceptions import HTTPException
from starlette.responses import HTMLResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from bunsho.api.csp import NONCE_SCOPE_KEY, generate_nonce
from bunsho.frontend_shell import CSP_NONCE_PLACEHOLDER, INDEX_FILE, read_shell

INDEX = INDEX_FILE
_IMMUTABLE = "public, max-age=31536000, immutable"
_SHELL_PATHS = frozenset({"", ".", INDEX})
"""How Starlette names the root and the index file (the root arrives as ``.``)."""


def _posix(path: str) -> str:
    """The mount-relative path with forward slashes (Starlette hands over OS separators)."""
    return path.replace("\\", "/")


def _is_client_route(path: str) -> bool:
    """Whether the single-page app should answer this path: not an API path, no file extension."""
    if path == "api" or path.startswith("api/"):
        return False
    return "." not in path.rsplit("/", 1)[-1]


def _set_cache_control(response: Response, path: str) -> None:
    """Cache hashed assets forever and never cache anything else."""
    response.headers["Cache-Control"] = _IMMUTABLE if path.startswith("assets/") else "no-cache"


class SPAStaticFiles(StaticFiles):
    """``StaticFiles`` for a single-page app.

    The app shell (the root, ``index.html`` and any unknown path without a file extension, so a
    deep link such as ``/build`` survives a reload) is rendered per request: the nonce
    placeholder in ``index.html`` is replaced by a fresh CSP nonce, which is also left on the ASGI
    scope for ``SecurityHeadersMiddleware``. Unknown API paths and missing files stay 404.
    """

    def __init__(
        self, *, directory: str | os.PathLike[str], html: bool = True, **kwargs: Any
    ) -> None:
        """Serve the build in ``directory``.

        Args:
            directory: The folder with the built UI.
            html: Serve ``index.html`` for directories, as ``StaticFiles`` does.
            **kwargs: Passed to ``StaticFiles``.

        Raises:
            StaleShellError: ``index.html`` has no ``CSP_NONCE_PLACEHOLDER`` (an older build).
        """
        super().__init__(directory=directory, html=html, **kwargs)
        self._shell = read_shell(Path(directory))

    @staticmethod
    def _shell_response(shell: str, scope: Scope) -> Response:
        """Render ``shell`` with a new nonce and record the nonce for the middleware."""
        nonce = generate_nonce()
        scope[NONCE_SCOPE_KEY] = nonce
        response = HTMLResponse(shell.replace(CSP_NONCE_PLACEHOLDER, nonce))
        response.headers["Cache-Control"] = "no-cache"
        return response

    async def get_response(self, path: str, scope: Scope) -> Response:
        """Serve ``path`` from the build folder, falling back to the app shell for client routes.

        Args:
            path: The path relative to the mount (``.`` for the root).
            scope: The ASGI scope.

        Returns:
            The file response with cache headers, or the shell rendered with a fresh nonce.

        Raises:
            HTTPException: 404 for unknown API paths and for missing files.
        """
        served = _posix(path)  # on Windows Starlette passes "api\nothing", not "api/nothing"
        shell = self._shell
        if shell is not None and served in _SHELL_PATHS:
            return self._shell_response(shell, scope)
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or not _is_client_route(served):
                raise
            if shell is not None:
                return self._shell_response(shell, scope)
            response = await super().get_response(INDEX, scope)
            served = INDEX
        _set_cache_control(response, served)
        return response
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/api/test_static.py -q`
Expected: all pass. If the root test fails because `/` does not reach the shell branch, print `path` in `get_response` once to see how this Starlette version names the root and add that value to `_SHELL_PATHS` (do not special-case it elsewhere).

- [ ] **Step 5: Run the whole API folder and the app-level header tests**

Run: `uv run pytest tests/unit/api tests/unit/test_main.py -q`
Expected: all pass, including `test_security_headers*.py` from Task 4 (the nonce in the header equalling the nonce in the body proves the scope key survives the whole middleware stack).

- [ ] **Step 6: Lint, type-check, bandit**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run bandit -c pyproject.toml -r src/ -l -q`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/bunsho/api/static.py tests/unit/api/test_static.py
git commit -m "feat(static): render the app shell with a per-request CSP nonce" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: the frontend reads the nonce and gives it to Mantine

**Files:**
- Modify: `frontend/index.html`
- Create: `frontend/src/csp.ts`, `frontend/src/csp.test.ts`
- Modify: `frontend/src/App.tsx`, `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: the literal placeholder `__CSP_NONCE__` the server replaces.
- Produces: `readCspNonce(): string | undefined`; `CSP_NONCE_PLACEHOLDER` (TS constant, same literal).

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/csp.test.ts`:

```ts
import { afterEach, describe, expect, it } from 'vitest';

import { CSP_NONCE_PLACEHOLDER, readCspNonce } from './csp';

function setMeta(content: string | null) {
  const meta = document.createElement('meta');
  meta.setAttribute('name', 'csp-nonce');
  if (content !== null) meta.setAttribute('content', content);
  document.head.appendChild(meta);
}

describe('readCspNonce', () => {
  afterEach(() => {
    document.head.querySelectorAll('meta[name="csp-nonce"]').forEach((node) => {
      node.remove();
    });
  });

  it('uses the same placeholder the server replaces', () => {
    expect(CSP_NONCE_PLACEHOLDER).toBe('__CSP_NONCE__');
  });

  it('returns the nonce the server put in the page', () => {
    setMeta('abc123+/==');
    expect(readCspNonce()).toBe('abc123+/==');
  });

  it('returns undefined without the tag', () => {
    expect(readCspNonce()).toBeUndefined();
  });

  it('returns undefined for a tag without content', () => {
    setMeta(null);
    expect(readCspNonce()).toBeUndefined();
  });

  it('returns undefined for an empty or blank value', () => {
    setMeta('   ');
    expect(readCspNonce()).toBeUndefined();
  });

  it('returns undefined while the placeholder is still there (npm run dev)', () => {
    setMeta(CSP_NONCE_PLACEHOLDER);
    expect(readCspNonce()).toBeUndefined();
  });
});
```

Add to `frontend/src/App.test.tsx`, inside the top-level `describe('App', ...)` (it already has the `beforeEach`/`afterEach` that reset the session and stub `WebSocket`); add a helper above the `describe`:

```tsx
function setNonceMeta(content: string) {
  const meta = document.createElement('meta');
  meta.setAttribute('name', 'csp-nonce');
  meta.setAttribute('content', content);
  document.head.appendChild(meta);
}
```

and these tests inside it:

```tsx
  describe('CSP nonce', () => {
    afterEach(() => {
      document.head.querySelectorAll('meta[name="csp-nonce"]').forEach((node) => {
        node.remove();
      });
    });

    it("puts the page's nonce on Mantine's runtime style elements", async () => {
      setNonceMeta('test-nonce+123==');
      render(<App />);
      await screen.findByLabelText('Username');
      const styles = Array.from(document.querySelectorAll('style[data-mantine-styles]'));
      expect(styles.length).toBeGreaterThan(0);
      for (const style of styles) {
        expect(style.getAttribute('nonce')).toBe('test-nonce+123==');
      }
    });

    it('adds no nonce when the page has none (development)', async () => {
      render(<App />);
      await screen.findByLabelText('Username');
      const styles = Array.from(document.querySelectorAll('style[data-mantine-styles]'));
      expect(styles.length).toBeGreaterThan(0);
      for (const style of styles) {
        expect(style.hasAttribute('nonce')).toBe(false);
      }
    });
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd "D:/Documents/Code/Bunshō/frontend" && npx vitest run src/csp.test.ts src/App.test.tsx`
Expected: `csp.test.ts` fails to import `./csp`; the App nonce test fails (no `nonce` attribute).

- [ ] **Step 3: Write the implementation**

`frontend/index.html`: add the meta tag after the viewport tag:

```html
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="csp-nonce" content="__CSP_NONCE__" />
```

Create `frontend/src/csp.ts`:

```ts
/** The literal the server replaces with a fresh nonce on every page load (see frontend/index.html). */
export const CSP_NONCE_PLACEHOLDER = '__CSP_NONCE__';

/**
 * The Content-Security-Policy nonce the server put in the page, for Mantine's runtime `<style>`
 * elements. Undefined when there is none: no tag, no content, or the placeholder still in place
 * (the Vite dev server serves the file as is, and needs no CSP).
 */
export function readCspNonce(): string | undefined {
  const content = document.querySelector('meta[name="csp-nonce"]')?.getAttribute('content')?.trim();
  if (content === undefined || content === '' || content === CSP_NONCE_PLACEHOLDER) return undefined;
  return content;
}
```

`frontend/src/App.tsx`: import it and read it once with `useState` (as `queryClient` is), then pass it to the provider:

```tsx
import { readCspNonce } from './csp';
```

```tsx
export function App() {
  const [queryClient] = useState(createQueryClient);
  const [cspNonce] = useState(readCspNonce);

  return (
    <MantineProvider
      theme={theme}
      defaultColorScheme="auto"
      getStyleNonce={cspNonce === undefined ? undefined : () => cspNonce}
    >
```

(`getStyleNonce` is `() => string` in Mantine 9; `undefined` leaves it off.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx vitest run src/csp.test.ts src/App.test.tsx`
Expected: all pass. If a Mantine `<style>` is rendered in a place the test query does not see, print `document.head.innerHTML` once and adjust the selector; do not weaken the "every style element" assertion.

- [ ] **Step 5: Format, lint, type-check, coverage**

Run: `npm run format && npm run format:check && npm run lint && npx tsc --noEmit -p . && npm run coverage`
Expected: clean; coverage thresholds hold.

- [ ] **Step 6: Commit**

```bash
cd "D:/Documents/Code/Bunshō"
git add frontend/index.html frontend/src/csp.ts frontend/src/csp.test.ts frontend/src/App.tsx frontend/src/App.test.tsx
git commit -m "feat(ui): give Mantine the page's CSP nonce" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: docs, smoke test, spec update, full verification

**Files:**
- Modify: `scripts/smoke_test.py`, `README.md`, `CHANGELOG.md`, `TODO.md`, `docs/superpowers/specs/2026-09-26-bunsho-csp-security-headers-design.md`

**Interfaces:**
- Consumes: everything above.
- Produces: a green full verification and a PR-ready branch.

- [ ] **Step 1: Update the smoke test**

`scripts/smoke_test.py::expect_frontend_served` compares `/build` byte for byte with `/`, which a per-request nonce breaks, and it has no header assertions. Above `expect_frontend_served` add:

```python
NONCE_META = re.compile(rb'(name="csp-nonce" content=")([^"]*)(")')


def shell_nonce(body: bytes) -> bytes:
    """The nonce in the shell's csp-nonce meta tag."""
    match = NONCE_META.search(body)
    expect(match is not None, "the app shell has no csp-nonce meta tag")
    assert match is not None  # for mypy: expect() raised otherwise
    return match.group(2)


def without_nonce(body: bytes) -> bytes:
    """The shell with its nonce blanked, so two responses can be compared."""
    return NONCE_META.sub(rb"\1\3", body)
```

Replace the start of `expect_frontend_served` up to and including the deep-link check with:

```python
    status, headers, body = http_get("/")
    expect(status == 200, f"GET / returned {status}, not 200")
    expect("text/html" in headers.get("content-type", ""), "GET / is not HTML")
    expect(b'<div id="root">' in body, "GET / did not return the app shell")
    expect(headers.get("cache-control") == "no-cache", "the app shell must not be cached")
    nonce = shell_nonce(body)
    expect(nonce not in (b"", b"__CSP_NONCE__"), "the shell still holds the nonce placeholder")
    csp = headers.get("content-security-policy", "")
    expect(f"'nonce-{nonce.decode()}'" in csp, "the shell CSP does not carry the body's nonce")
    expect("script-src 'self'" in csp and "unsafe-inline" not in csp, "the shell CSP is not strict")
    expect(headers.get("x-frame-options") == "DENY", "the shell lacks X-Frame-Options")
    expect(headers.get("x-content-type-options") == "nosniff", "the shell lacks nosniff")
    expect(headers.get("referrer-policy") == "no-referrer", "the shell lacks Referrer-Policy")
    status, _, deep_link = http_get("/build")
    expect(
        status == 200 and without_nonce(deep_link) == without_nonce(body),
        "a client-side route did not return the shell",
    )
    expect(shell_nonce(deep_link) != nonce, "the nonce must change on every request")
```

and, after the existing `an API 404 must be JSON` check, add:

```python
    expect(
        headers.get("content-security-policy") == "default-src 'none'; frame-ancestors 'none'",
        "an API response must carry the default-deny CSP",
    )
    status, headers, _ = http_get("/docs")
    expect(status == 200, f"/docs returned {status}, not 200")
    expect("cdn.jsdelivr.net" in headers.get("content-security-policy", ""), "/docs needs its CSP")
```

(The existing `status, headers, _ = http_get("/api/v1/does-not-exist")` line is the one whose `headers` the first new `expect` reads: place the new code right after its two existing `expect`s.)

- [ ] **Step 2: Update the README**

In `README.md` settings paragraph, after `` `server.trusted_proxies` (…default, means proxy headers are ignored), `` add ` ` `` `server.csp_report_only` (`true` sends the Content-Security-Policy as `Content-Security-Policy-Report-Only`: the browser reports violations in its console and blocks nothing; default `false`), `` before `` `auth.access_ttl_minutes` ``. The anchor text is `default, means proxy headers are ignored), \`auth.access_ttl_minutes\`,`.

After the bullet ending `in front. Never expose the port to the internet.` add:

```markdown
- Every response carries `X-Content-Type-Options`, `Referrer-Policy` and `X-Frame-Options` headers and a
  Content-Security-Policy. The UI's policy allows only the service's own scripts and styles (styles by a
  per-request nonce); the API is default-deny; `/docs` and `/redoc` get a looser policy so they can load
  Swagger UI and Redoc from `cdn.jsdelivr.net`. If a browser or extension misbehaves under the policy,
  set `BUNSHO_SERVER__CSP_REPORT_ONLY=true` to see the violations in the browser console without
  blocking anything. The service does not send `Strict-Transport-Security`; if a reverse proxy
  terminates TLS, have the proxy send it.
```

`.env.example` is untracked in this repository and is not edited; the PR body says so.

- [ ] **Step 3: CHANGELOG**

View the top of `CHANGELOG.md` first. In the existing `## [1.4.0] - 2026-09-25` section only (do not add a new version or an Unreleased entry):

- append to `### Added`: `- \`server.csp_report_only\` (\`BUNSHO_SERVER__CSP_REPORT_ONLY\`, default false) sends the Content-Security-Policy as \`Content-Security-Policy-Report-Only\`, so a browser reports violations in its console without blocking anything.`
- append to `### Security`:
  - `- Every response now carries \`X-Content-Type-Options\`, \`Referrer-Policy\` and \`X-Frame-Options\`, not only the static files: the API, \`/openapi.json\` and the docs pages too.`
  - `- The web UI is served with a Content-Security-Policy: only the service's own scripts, and styles only with a per-request nonce (no \`unsafe-inline\`). The API and static assets are default-deny. \`/docs\` and \`/redoc\` have their own looser policy so Swagger UI and Redoc still load from \`cdn.jsdelivr.net\`.`
  - `- The service refuses to start with a \`frontend_dir\` built before this version (no nonce placeholder in \`index.html\`) and says to rebuild the UI with \`npm run build\`.`

- [ ] **Step 4: TODO.md**

Remove the two open items under `### Security & Auth` (the Content-Security-Policy line and the "Security headers … set on static responses only" line). If the section is then empty, keep the heading and write `- (nothing open)` under it. Add above `### Decisions`:

```markdown
### CSP and security headers (1.4.0)

- [x] Baseline security headers on every response, and a CSP per response class: a strict nonce-based
      policy for the UI shell (`SPAStaticFiles` renders `index.html` per request; Mantine gets the nonce
      via `getStyleNonce`), default-deny for the API and assets, a looser one for `/docs` and `/redoc`
- [x] `server.csp_report_only` switch; a UI build without the nonce placeholder is reported by config
      validation
```

- [ ] **Step 5: Update the spec to match what was built**

In `docs/superpowers/specs/2026-09-26-bunsho-csp-security-headers-design.md`:

1. Replace the `DOCS` line in the "Policies" code block with the settled policy (Global Constraints of this plan, "Docs CSP"), and replace the paragraph beginning "The DOCS list is the starting point." with: `The DOCS list was settled on 2026-09-26 against the HTML FastAPI serves today: Swagger UI loads its script and stylesheet from cdn.jsdelivr.net, the favicon from fastapi.tiangolo.com and runs one inline script; Redoc loads its bundle from cdn.jsdelivr.net, its fonts stylesheet from fonts.googleapis.com (font files from fonts.gstatic.com) and uses blob: workers. A test pins every origin the two pages reference against the policy, so a FastAPI upgrade that changes them is noticed.`
2. In "Setting" and "Housekeeping" replace the `.env.example` mentions with: `.env.example is untracked in this repository, so it is not edited; the PR notes the new optional key for James to add by hand.`
3. Change the status line to `Status: implemented in PR <number> (fill in when the PR is opened).` — write the real number after Step 9.

- [ ] **Step 6: Full backend verification (mirrors CI)**

Run:

```bash
cd "D:/Documents/Code/Bunshō" && unset VIRTUAL_ENV
uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run bandit -c pyproject.toml -r src/ -l -q
uv run pytest --cov --cov-report=term-missing -q
```
Expected: clean; all tests pass; coverage >= 90 with the new modules (`csp.py`, `security_headers.py`, `frontend_shell.py`, `static.py`) at or near 100%. Warnings: 3-4 unclosed-sqlite `ResourceWarning`s also appear on a clean `main`; they are not from this work.

- [ ] **Step 7: Flake check for the new HTTP tests**

Run (about 4 minutes):

```bash
fails=0; for i in $(seq 1 40); do uv run pytest tests/unit/api/test_static.py tests/unit/api/test_security_headers.py tests/unit/api/test_security_headers_middleware.py tests/unit/api/test_csp.py -q -p no:cacheprovider -x >/dev/null 2>&1 || { fails=$((fails+1)); echo "run $i FAILED"; }; done; echo "failures=$fails"
```
Expected: `failures=0`.

- [ ] **Step 8: Full frontend verification and a real build**

Run:

```bash
cd "D:/Documents/Code/Bunshō/frontend"
npm run format:check && npm run lint && npx tsc --noEmit -p . && npm run gen:api && git diff --exit-code -- src/api/schema.d.ts && npm run build && npm run coverage
grep -c "__CSP_NONCE__" dist/index.html
```
Expected: everything clean, `git diff --exit-code` prints nothing, and the `grep -c` prints `1` (the placeholder survived the build).

- [ ] **Step 9: Real-server check with the built UI**

Run the service against the fresh build and look at the headers for real (this is what the unit tests cannot show). In a scratch folder outside the repo write a `.env` with `BUNSHO_AUTH__USERNAME`, an argon2 `BUNSHO_AUTH__PASSWORD_HASH` and a 32+ character `BUNSHO_AUTH__JWT_SECRET` (see `.env.example`'s generation commands), `BUNSHO_PATHS__FRONTEND_DIR=<repo>/frontend/dist` and `BUNSHO_PATHS__DATA_DIR=<scratch>/data`. Start `uv run bunsho`, then:

```bash
curl -sI http://127.0.0.1:8192/            # 200, CSP with a nonce, X-Frame-Options, nosniff, Referrer-Policy
curl -s  http://127.0.0.1:8192/ | grep csp-nonce   # the same nonce as in the header, and different on the next call
curl -sI http://127.0.0.1:8192/api/v1/health       # default-deny CSP
curl -sI http://127.0.0.1:8192/docs                # docs CSP
```
Then stop the server. Also start it once with `BUNSHO_SERVER__CSP_REPORT_ONLY=true` and confirm `curl -sI /` shows `Content-Security-Policy-Report-Only` and no `Content-Security-Policy`. If Docker is available, additionally run `uv run python scripts/smoke_test.py` (CI runs it; it takes several minutes and builds the image). If either cannot be run, say so in the PR body.

- [ ] **Step 10: Commit the documentation and smoke test**

```bash
cd "D:/Documents/Code/Bunshō"
git add scripts/smoke_test.py README.md CHANGELOG.md TODO.md docs/superpowers/specs/2026-09-26-bunsho-csp-security-headers-design.md
git commit -m "docs: CSP and security headers in the README, changelog and smoke test" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

- [ ] **Step 11: Push, open the PR, fill in the spec's PR number**

```bash
git push -u origin feat/csp-security-headers
gh pr create --base main --head feat/csp-security-headers --title "feat(security): CSP and security headers on every response" --body-file <a file with the body below>
```
Then replace `<number>` in the spec's status line, commit `docs(spec): record the PR number` and push.

PR body must contain: a Summary (what the three policies are and why `/docs` is the one exception; the nonce flow; the report-only switch; stale-build check; goes into 1.4.0, no bump); Tests (list); Verification actually run (with results and the flake loop count); **Not verified** (browser rendering; Redoc/Swagger live; `.env.example` untracked so not edited); and this **manual browser checklist for James**:

1. Build the UI (`npm run build` in `frontend/`) and start the service with it. Open the app in a real browser with the console open. Log in, then visit Home, Review (all three modes), Stats and Settings (every tab). Confirm the console shows **no CSP violations**. Also try the dark scheme, a narrow window below the mobile breakpoint, trigger a notification (save settings) and look at the stats charts.
2. Open `/docs` and `/redoc`: both render; "Try it out" works in `/docs`.
3. Set `BUNSHO_SERVER__CSP_REPORT_ONLY=true`, restart, reload: the response header is `Content-Security-Policy-Report-Only`, nothing is blocked. Then unset it.
4. Any violation found: report it, and the policy (and spec) get a follow-up with the reason.
5. Optionally add `# BUNSHO_SERVER__CSP_REPORT_ONLY=false` to your local `.env.example` (it is untracked).

Do not merge; no tag or release.
