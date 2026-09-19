# Bunshō Plan 1A: Foundation and Content Pipeline

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a tested library that turns the pinned JLPT vocabulary `.apkg` deck plus the jamdict-data-fix database into a rebuildable `content.db` (kana, derived-level kanji, vocab, sentences).

**Architecture:** Hexagonal modular monolith. Pure parsing and derivation logic sits behind small Protocols (`DeckImporter`, `KanjiInfoSource`, `KanaProvider`, `ContentWriting`). A `ContentBuildOrchestrator` coordinates them, supports `dry_run` and progress callbacks, and writes `content.db` atomically. A `Context` plus factory functions wire concrete services from config.

**Tech Stack:** Python 3.13, uv, hatchling, pydantic v2, python-dotenv, jamdict + jamdict-data-fix, stdlib sqlite3, pytest, ruff, mypy, bandit.

**Spec:** `docs/superpowers/specs/2026-09-19-bunsho-foundation-and-review-engine-design.md`

**Plan series:** 1A (this plan) → 1B (progress.db + Alembic, JWT auth, FastAPI app, health/config-check/admin build + WebSocket, Docker, CI, skills cleanup) → 2 (FSRS review engine + React UI). 1B and 2 are written after 1A lands.

## Global Constraints

- Python `>=3.13`; build backend `hatchling`; dependency management with `uv`; `.venv` managed by uv.
- Display name is **Bunshō**; ASCII slug for package, distribution and identifiers is **`bunsho`** (never `bunshou`).
- **No CLI** (no click/rich). No `print` for operational output; use `logging` with `key=value` style messages.
- Google-style docstrings on all public functions, classes and methods; modern type syntax (`list[str]`); mypy strict.
- ruff (lint + format), mypy, bandit must pass; pytest coverage `>= 90%`.
- Any operation that writes data supports `dry_run` (orchestrator level here).
- Never hard-code secrets; config from file < `.env` < real environment variables (env wins), keys case-insensitive.
- Never use port 8000 (default API port later is 8192).
- New behavior needs tests; shared fixtures live in `tests/base.py`.
- The deck is pinned: `resources/JLPT_N5_to_N1_Japanese_Vocabulary.apkg`, sha256 `fe5cf438a8f0f6690af00b2c2a9c61da9390feb5bd6d663ea8e6b225b17c3b4a`, GPL-3.0.
- Commit messages use conventional commits; append the session's `Co-Authored-By` trailer. Stage explicit paths, never `git add -A`.
- Deck facts the code relies on: 7,734 notes; exactly one `jlpt_N1`..`jlpt_N5` tag per note; fields `Expression`, `English definition`, `Reading`, `Grammar`, `Additional definitions`, `Example JP`, `Example EN`; only `<mark>` HTML; furigana as `漢字[かんじ]` with a space (or string start) before each base; 959 notes have an empty `Example JP`. `(expression, raw Reading)` is unique across all notes, but `(expression, plain reading)` is NOT: exactly one homograph pair exists (two N3 notes for 度, Reading `ど` and `度[ど]`), which the importer disambiguates as `vocab:度:ど` and `vocab:度:ど#2` (controller ruling R12, added after Task 11 hit it on the real deck).
- jamdict facts the code relies on (verified against `jamdict 0.1a11.post2`, `jamdict-data-fix 1.5.1a2`): `Jamdict(db_file=p, kd2_file=p, jmnedict_file=p, auto_config=False)`; `get_char(literal)` returns `Character | None`; `character.meanings(english_only=True)`; readings via `character.rm_groups[*].readings[*]` with `r_type` `ja_on` / `ja_kun`; `stroke_count`, `grade`, `freq`, `jlpt` (old 1-4 scale, ignored); `radicals` items with `rad_type == "classical"`; a missing DB file does **not** raise, so availability must be checked with `is_available()` and `has_kd2()`; roughly 10 ms per lookup.

## Scope note

The spec said kanji outside the deck would be stored as "unleveled". Plan 1A stores **only kanji that appear in deck vocabulary**, each with a derived level (YAGNI). Expected real-deck results: 2,109 kanji (N5 480, N4 352, N3 544, N2 357, N1 376), 6,775 sentences, 208 kana.

## File Structure

```
pyproject.toml, README.md, .gitignore                     (Task 1)
resources/LICENSE, resources/README.md                    (Task 1)
src/bunsho/__init__.py                                    (Task 1)
src/bunsho/config/{__init__,normalizer,loader,settings}.py (Task 2)
src/bunsho/text.py, src/bunsho/models/{__init__,content}.py (Task 3)
src/bunsho/services/furigana.py                           (Task 4)
src/bunsho/services/kana_source.py                        (Task 5)
src/bunsho/services/anki_importer.py                      (Task 6)
src/bunsho/services/{protocols,kanji_levels}.py           (Task 7)
src/bunsho/services/jamdict_service.py                    (Task 8)
src/bunsho/services/content_repository.py                 (Task 9)
src/bunsho/orchestration/{__init__,content_build}.py      (Task 10)
src/bunsho/{logging_setup,context,factories}.py           (Task 11)
tests/{__init__,base,conftest,apkg_builder}.py, tests/unit/**, tests/integration/**
```

---

### Task 1: Scaffold, rename to `bunsho`, tooling, deck provenance

**Files:**
- Modify: `pyproject.toml`, `README.md`
- Create: `.gitignore`, `src/bunsho/__init__.py`, `resources/LICENSE`, `resources/README.md`, `tests/__init__.py`, `tests/test_package.py`
- Delete: `src/bunshou/`

**Interfaces:**
- Produces: `bunsho.__version__: str`, `bunsho.APP_NAME == "Bunshō"`, `bunsho.APP_SLUG == "bunsho"`.

- [ ] **Step 1: Write the failing test**

Create `tests/__init__.py` (empty) and `tests/test_package.py`:

```python
from importlib import metadata

import bunsho


def test_names_and_version() -> None:
    assert bunsho.APP_NAME == "Bunshō"
    assert bunsho.APP_SLUG == "bunsho"
    assert bunsho.__version__ == metadata.version("bunsho")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_package.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'bunsho'` or metadata not found).

- [ ] **Step 3: Rename the package and rewrite `pyproject.toml`**

```bash
mv src/bunshou src/bunsho
```

`src/bunsho/__init__.py`:

```python
"""Bunshō (文章): a Japanese language learning tool."""

__version__ = "0.1.0"
APP_NAME = "Bunshō"
APP_SLUG = "bunsho"
```

Replace `pyproject.toml` entirely:

```toml
[project]
name = "bunsho"
version = "0.1.0"
description = "Bunshō (文章): a Japanese learning tool with kana, JLPT kanji and vocabulary, and spaced-repetition flashcards."
readme = "README.md"
authors = [{ name = "James", email = "jamesbconner@users.noreply.github.com" }]
requires-python = ">=3.13"
dependencies = []

[project.optional-dependencies]
dev = []

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/bunsho"]

[tool.ruff]
line-length = 100
target-version = "py313"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "D", "S", "C4", "PT"]

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["D", "S101", "S105", "S106"]

[tool.mypy]
python_version = "3.13"
strict = true
files = ["src"]
plugins = ["pydantic.mypy"]

[[tool.mypy.overrides]]
module = ["jamdict", "jamdict.*", "jamdict_data", "jamdict_data.*"]
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-ra --strict-markers"
markers = ["integration: needs the real deck and the jamdict-data-fix database"]

[tool.coverage.run]
source = ["src/bunsho"]
branch = true

[tool.coverage.report]
fail_under = 90
show_missing = true
exclude_lines = ["pragma: no cover", "if TYPE_CHECKING:", "\\.\\.\\."]

[tool.bandit]
exclude_dirs = ["tests"]
```

Add dependencies (uv resolves current versions):

```bash
uv add pydantic python-dotenv jamdict jamdict-data-fix
uv add --optional dev pytest pytest-cov ruff mypy bandit pre-commit twine
uv sync --extra dev
```

- [ ] **Step 4: Write README, .gitignore and deck provenance**

`README.md`:

```markdown
# Bunshō (文章)

A Japanese language learning tool: hiragana, katakana, JLPT N5-N1 kanji and vocabulary, and
spaced-repetition flashcards. Runs as a containerized FastAPI + React web app on a home server.

Status: early development. See `docs/superpowers/specs/` for the design.
```

`.gitignore`:

```
.venv/
__pycache__/
*.pyc
.env
data/
node_modules/
dist/
.coverage
coverage.xml
.mypy_cache/
.ruff_cache/
.pytest_cache/
.claude/settings.local.json
.claude/scheduled_tasks.lock
```

```bash
curl -fsSL https://raw.githubusercontent.com/coolmule0/JLPT-N5-N1-Japanese-Vocabulary-Anki/refs/heads/main/LICENSE -o resources/LICENSE
head -3 resources/LICENSE
```
Expected first line: `GNU GENERAL PUBLIC LICENSE`.

`resources/README.md`:

```markdown
# Resources

## JLPT_N5_to_N1_Japanese_Vocabulary.apkg

- Source: https://github.com/coolmule0/JLPT-N5-N1-Japanese-Vocabulary-Anki (AnkiWeb shared deck 1550984460)
- License: GNU GPL v3 (see `LICENSE` in this folder)
- Obtained: 2026-09-19
- sha256: `fe5cf438a8f0f6690af00b2c2a9c61da9390feb5bd6d663ea8e6b225b17c3b4a`
- Contents: 7,734 vocabulary notes tagged `jlpt_N1`..`jlpt_N5`.

Bunshō verifies this checksum before importing. A `content.db` built from this deck is a
derived work; if it is ever distributed it must be offered under GPL-3.0.
```

- [ ] **Step 5: Run tests and quality gates**

Run: `uv run pytest tests/test_package.py -v && uv run ruff check . && uv run ruff format --check . && uv run mypy src/`
Expected: PASS everywhere. If `ruff format --check` fails, run `uv run ruff format .` and re-check.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock README.md .gitignore src tests resources docs
git commit -m "chore: scaffold bunsho package, tooling and pinned deck provenance"
```

---

### Task 2: Configuration (normalizer, loader, validated AppConfig)

**Files:**
- Create: `src/bunsho/config/__init__.py`, `normalizer.py`, `loader.py`, `settings.py`
- Test: `tests/unit/config/test_normalizer.py`, `tests/unit/config/test_loader.py`, `tests/unit/config/test_settings.py`

**Interfaces:**
- Produces:
  - `ConfigError(ValueError)`
  - `ConfigNormalizer(raw: Mapping[str, Mapping[str, Any]] | None = None)` with `has_option(section, key) -> bool`, `get_string(section, key, fallback: str = "") -> str`, `get_int(section, key, fallback: int = 0) -> int`, `get_float(section, key, fallback: float = 0.0) -> float`, `get_bool(section, key, fallback: bool = False) -> bool`, `merge_env(environ: Mapping[str, str]) -> ConfigNormalizer`
  - `load_config(*, config_file: Path | None = None, env_file: Path | None = None, environ: Mapping[str, str] | None = None) -> ConfigNormalizer`
  - `AppConfig` frozen dataclass: `data_dir: Path`, `resources_dir: Path`, `deck_filename: str`, `deck_sha256: str`, `jamdict_db: Path | None`, `log_level: str`; properties `content_db_path`, `progress_db_path`, `deck_path`
  - `validate_config(cfg: ConfigNormalizer) -> list[str]`, `load_app_config(cfg: ConfigNormalizer) -> AppConfig`, constants `DEFAULT_DECK_FILENAME`, `DEFAULT_DECK_SHA256`
- Env override convention: `BUNSHO_<SECTION>__<KEY>` (e.g. `BUNSHO_PATHS__DATA_DIR`).

- [ ] **Step 1: Write the failing tests**

`tests/unit/config/test_normalizer.py` (create empty `__init__.py` files under `tests/unit` and `tests/unit/config`):

```python
import pytest

from bunsho.config.normalizer import ConfigError, ConfigNormalizer


def test_sections_and_keys_are_case_insensitive() -> None:
    cfg = ConfigNormalizer({"Database": {"Host": "h"}, "DATABASE": {"PORT": "5"}})
    assert cfg.get_string("database", "host") == "h"
    assert cfg.get_int("Database", "port") == 5


def test_fallbacks_when_missing() -> None:
    cfg = ConfigNormalizer()
    assert cfg.get_string("a", "b", "x") == "x"
    assert cfg.get_int("a", "b", 7) == 7
    assert cfg.get_float("a", "b", 1.5) == 1.5
    assert cfg.get_bool("a", "b", True) is True
    assert not cfg.has_option("a", "b")


@pytest.mark.parametrize("raw", ["true", "YES", "1", "on"])
def test_get_bool_truthy(raw: str) -> None:
    assert ConfigNormalizer({"s": {"k": raw}}).get_bool("s", "k") is True


@pytest.mark.parametrize("raw", ["false", "No", "0", "off"])
def test_get_bool_falsy(raw: str) -> None:
    assert ConfigNormalizer({"s": {"k": raw}}).get_bool("s", "k", True) is False


def test_get_bool_accepts_real_bool_and_rejects_garbage() -> None:
    assert ConfigNormalizer({"s": {"k": True}}).get_bool("s", "k") is True
    with pytest.raises(ConfigError, match="not a valid boolean"):
        ConfigNormalizer({"s": {"k": "maybe"}}).get_bool("s", "k")


def test_invalid_numbers_raise_config_error() -> None:
    cfg = ConfigNormalizer({"s": {"i": "x", "f": "y"}})
    with pytest.raises(ConfigError, match="not a valid integer"):
        cfg.get_int("s", "i")
    with pytest.raises(ConfigError, match="not a valid float"):
        cfg.get_float("s", "f")


def test_merge_env_overrides_and_ignores_unrelated() -> None:
    cfg = ConfigNormalizer({"paths": {"data_dir": "file"}})
    merged = cfg.merge_env(
        {"BUNSHO_PATHS__DATA_DIR": "env", "OTHER": "x", "BUNSHO_BAD": "y", "BUNSHO___K": "z"}
    )
    assert merged.get_string("paths", "data_dir") == "env"
    assert cfg.get_string("paths", "data_dir") == "file"  # original untouched
    assert not merged.has_option("bad", "")
```

`tests/unit/config/test_loader.py`:

```python
from pathlib import Path

from bunsho.config.loader import load_config


def test_precedence_file_then_dotenv_then_environ(tmp_path: Path) -> None:
    toml = tmp_path / "config.toml"
    toml.write_text('[Paths]\nData_Dir = "from-toml"\nResources_Dir = "toml-res"\n')
    dotenv = tmp_path / ".env"
    dotenv.write_text("BUNSHO_PATHS__DATA_DIR=from-dotenv\nBUNSHO_LOGGING__LEVEL=debug\n")
    cfg = load_config(
        config_file=toml,
        env_file=dotenv,
        environ={"BUNSHO_LOGGING__LEVEL": "warning"},
    )
    assert cfg.get_string("paths", "data_dir") == "from-dotenv"
    assert cfg.get_string("paths", "resources_dir") == "toml-res"
    assert cfg.get_string("logging", "level") == "warning"


def test_defaults_to_process_environment(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUNSHO_PATHS__DATA_DIR", "from-os")
    assert load_config().get_string("paths", "data_dir") == "from-os"
```

`tests/unit/config/test_settings.py`:

```python
from pathlib import Path

import pytest

from bunsho.config.normalizer import ConfigError, ConfigNormalizer
from bunsho.config.settings import (
    DEFAULT_DECK_FILENAME,
    DEFAULT_DECK_SHA256,
    load_app_config,
    validate_config,
)


def test_defaults_are_valid() -> None:
    config = load_app_config(ConfigNormalizer())
    assert config.deck_filename == DEFAULT_DECK_FILENAME
    assert config.deck_sha256 == DEFAULT_DECK_SHA256
    assert config.jamdict_db is None
    assert config.log_level == "INFO"
    assert config.content_db_path == Path("data") / "content.db"
    assert config.progress_db_path == Path("data") / "progress.db"
    assert config.deck_path == Path("resources") / DEFAULT_DECK_FILENAME


def test_all_validation_errors_are_reported_together(tmp_path: Path) -> None:
    cfg = ConfigNormalizer(
        {
            "logging": {"level": "loud"},
            "paths": {
                "deck_sha256": "abc",
                "deck_filename": "../evil.apkg",
                "jamdict_db": str(tmp_path / "missing.db"),
            },
        }
    )
    errors = validate_config(cfg)
    assert len(errors) == 4
    with pytest.raises(ConfigError) as info:
        load_app_config(cfg)
    assert str(info.value).count("\n  - ") == 4


@pytest.mark.parametrize("name", ["", ".", "..", "a/b.apkg", "a\\b.apkg"])
def test_deck_filename_must_be_bare(name: str) -> None:
    assert validate_config(ConfigNormalizer({"paths": {"deck_filename": name}}))


def test_existing_jamdict_db_is_accepted(tmp_path: Path) -> None:
    db = tmp_path / "jamdict.db"
    db.write_bytes(b"")
    config = load_app_config(ConfigNormalizer({"paths": {"jamdict_db": str(db)}}))
    assert config.jamdict_db == db
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/config -v`
Expected: FAIL (`ModuleNotFoundError: bunsho.config`).

- [ ] **Step 3: Implement**

`src/bunsho/config/normalizer.py`:

```python
"""Case-insensitive configuration wrapper with typed accessors."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

ENV_PREFIX = "BUNSHO_"
_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})


class ConfigError(ValueError):
    """Raised when configuration is missing, malformed or invalid."""


class ConfigNormalizer:
    """Holds ``{section: {key: value}}`` with lowercase section and key names."""

    def __init__(self, raw: Mapping[str, Mapping[str, Any]] | None = None) -> None:
        """Normalize ``raw`` so lookups are case-insensitive.

        Args:
            raw: Nested mapping such as parsed TOML. Names may use any case.
        """
        self._data: dict[str, dict[str, Any]] = {}
        for section, values in (raw or {}).items():
            bucket = self._data.setdefault(section.lower(), {})
            for key, value in values.items():
                bucket[key.lower()] = value

    def has_option(self, section: str, key: str) -> bool:
        """Return whether ``[section] key`` is present."""
        return key.lower() in self._data.get(section.lower(), {})

    def _lookup(self, section: str, key: str) -> Any | None:
        return self._data.get(section.lower(), {}).get(key.lower())

    def get_string(self, section: str, key: str, fallback: str = "") -> str:
        """Return the value as a string, or ``fallback`` when absent."""
        value = self._lookup(section, key)
        return fallback if value is None else str(value)

    def get_int(self, section: str, key: str, fallback: int = 0) -> int:
        """Return the value as an int.

        Raises:
            ConfigError: If the value cannot be parsed as an integer.
        """
        value = self._lookup(section, key)
        if value is None:
            return fallback
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"[{section}] {key}={value!r} is not a valid integer") from exc

    def get_float(self, section: str, key: str, fallback: float = 0.0) -> float:
        """Return the value as a float.

        Raises:
            ConfigError: If the value cannot be parsed as a float.
        """
        value = self._lookup(section, key)
        if value is None:
            return fallback
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"[{section}] {key}={value!r} is not a valid float") from exc

    def get_bool(self, section: str, key: str, fallback: bool = False) -> bool:
        """Return the value as a bool (true/false, yes/no, on/off, 1/0).

        Raises:
            ConfigError: If the value is not a recognized boolean spelling.
        """
        value = self._lookup(section, key)
        if value is None:
            return fallback
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
        raise ConfigError(f"[{section}] {key}={value!r} is not a valid boolean")

    def merge_env(self, environ: Mapping[str, str]) -> ConfigNormalizer:
        """Return a copy with ``BUNSHO_<SECTION>__<KEY>`` variables applied on top.

        Args:
            environ: Environment-style mapping. Unrelated or malformed names are ignored.

        Returns:
            A new normalizer; ``self`` is not modified.
        """
        merged = ConfigNormalizer(self._data)
        for name, value in environ.items():
            upper = name.upper()
            if not upper.startswith(ENV_PREFIX):
                continue
            section, sep, key = upper[len(ENV_PREFIX) :].partition("__")
            if not sep or not section or not key:
                continue
            merged._data.setdefault(section.lower(), {})[key.lower()] = value
        return merged
```

`src/bunsho/config/loader.py`:

```python
"""Load layered configuration: TOML file < ``.env`` file < real environment."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from bunsho.config.normalizer import ConfigNormalizer


def load_config(
    *,
    config_file: Path | None = None,
    env_file: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> ConfigNormalizer:
    """Build a normalized configuration from all sources.

    Args:
        config_file: Optional TOML file with the lowest precedence.
        env_file: Optional ``.env`` file; overrides the TOML file.
        environ: Environment mapping (defaults to ``os.environ``); highest precedence.

    Returns:
        The merged configuration. ``os.environ`` is never mutated.
    """
    file_values: dict[str, Any] = {}
    if config_file is not None:
        with config_file.open("rb") as handle:
            file_values = tomllib.load(handle)
    merged_env: dict[str, str] = {}
    if env_file is not None:
        merged_env.update({k: v for k, v in dotenv_values(env_file).items() if v is not None})
    merged_env.update(os.environ if environ is None else environ)
    return ConfigNormalizer(file_values).merge_env(merged_env)
```

`src/bunsho/config/settings.py`:

```python
"""Typed application configuration and validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from bunsho.config.normalizer import ConfigError, ConfigNormalizer

DEFAULT_DECK_FILENAME = "JLPT_N5_to_N1_Japanese_Vocabulary.apkg"
DEFAULT_DECK_SHA256 = "fe5cf438a8f0f6690af00b2c2a9c61da9390feb5bd6d663ea8e6b225b17c3b4a"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Validated runtime configuration."""

    data_dir: Path
    resources_dir: Path
    deck_filename: str
    deck_sha256: str
    jamdict_db: Path | None
    log_level: str

    @property
    def content_db_path(self) -> Path:
        """Location of the rebuildable ``content.db``."""
        return self.data_dir / "content.db"

    @property
    def progress_db_path(self) -> Path:
        """Location of the irreplaceable ``progress.db``."""
        return self.data_dir / "progress.db"

    @property
    def deck_path(self) -> Path:
        """Location of the pinned vocabulary deck."""
        return self.resources_dir / self.deck_filename

    @classmethod
    def from_normalizer(cls, cfg: ConfigNormalizer) -> AppConfig:
        """Build from an already-validated normalizer (see ``validate_config``)."""
        jamdict = cfg.get_string("paths", "jamdict_db")
        return cls(
            data_dir=Path(cfg.get_string("paths", "data_dir", "data")),
            resources_dir=Path(cfg.get_string("paths", "resources_dir", "resources")),
            deck_filename=cfg.get_string("paths", "deck_filename", DEFAULT_DECK_FILENAME),
            deck_sha256=cfg.get_string("paths", "deck_sha256", DEFAULT_DECK_SHA256).lower(),
            jamdict_db=Path(jamdict) if jamdict else None,
            log_level=cfg.get_string("logging", "level", "INFO").upper(),
        )


def validate_config(cfg: ConfigNormalizer) -> list[str]:
    """Check configuration and return every problem found (empty list means valid)."""
    errors: list[str] = []
    level = cfg.get_string("logging", "level", "INFO").upper()
    if level not in _LOG_LEVELS:
        errors.append(f"[logging] level={level!r} must be one of {sorted(_LOG_LEVELS)}")
    sha = cfg.get_string("paths", "deck_sha256", DEFAULT_DECK_SHA256).lower()
    if not _SHA256.fullmatch(sha):
        errors.append("[paths] deck_sha256 must be 64 lowercase hex characters")
    name = cfg.get_string("paths", "deck_filename", DEFAULT_DECK_FILENAME)
    if not name or name in {".", ".."} or Path(name).name != name:
        errors.append("[paths] deck_filename must be a bare file name without directories")
    jamdict = cfg.get_string("paths", "jamdict_db")
    if jamdict and not Path(jamdict).is_file():
        errors.append(
            f"[paths] jamdict_db={jamdict!r} does not exist; "
            "unset it to use the database from the jamdict-data-fix package"
        )
    return errors


def load_app_config(cfg: ConfigNormalizer) -> AppConfig:
    """Validate ``cfg`` and build an ``AppConfig``.

    Raises:
        ConfigError: Listing every validation failure at once.
    """
    errors = validate_config(cfg)
    if errors:
        raise ConfigError("Invalid configuration:\n  - " + "\n  - ".join(errors))
    return AppConfig.from_normalizer(cfg)
```

`src/bunsho/config/__init__.py`:

```python
"""Configuration loading, normalization and validation."""

from bunsho.config.loader import load_config
from bunsho.config.normalizer import ConfigError, ConfigNormalizer
from bunsho.config.settings import AppConfig, load_app_config, validate_config

__all__ = [
    "AppConfig",
    "ConfigError",
    "ConfigNormalizer",
    "load_app_config",
    "load_config",
    "validate_config",
]
```

- [ ] **Step 4: Run tests and gates**

Run: `uv run pytest tests/unit/config -v && uv run ruff check . && uv run ruff format --check . && uv run mypy src/`
Expected: all PASS. (Format with `uv run ruff format .` if needed.)

- [ ] **Step 5: Commit**

```bash
git add src/bunsho/config tests/unit
git commit -m "feat(config): case-insensitive layered config with validated AppConfig"
```

---

### Task 3: Domain models, text helpers, shared test base

**Files:**
- Create: `src/bunsho/text.py`, `src/bunsho/models/__init__.py`, `src/bunsho/models/content.py`, `tests/base.py`, `tests/conftest.py`
- Test: `tests/unit/test_text.py`, `tests/unit/models/test_content.py`

**Interfaces:**
- Produces (`bunsho.text`): `is_kanji(char: str) -> bool`, `extract_kanji(text: str) -> list[str]`
- Produces (`bunsho.models.content`):
  - `JlptLevel(IntEnum)` N1=1..N5=5 (higher number = easier), `.label -> str`, `JlptLevel.from_tag(tag: str) -> JlptLevel | None`, `JlptLevel.study_order() -> tuple[JlptLevel, ...]` (N5..N1)
  - `KanaScript(StrEnum)` `HIRAGANA="hira"`, `KATAKANA="kata"`; `KanaKind(StrEnum)` `BASIC`, `DAKUTEN`, `YOUON`
  - Frozen models: `RubySegment(base: str, reading: str | None = None, highlighted: bool = False)`, `Sentence(segments: tuple[RubySegment, ...], english: str)`, `Kana(id, script, char, romaji, kind, group)`, `KanjiDetails(meanings, on_readings, kun_readings, stroke_count, grade, frequency, radical)` (all defaulted), `Kanji(KanjiDetails + id, char, level)`, `Vocab(id, expression, reading, reading_segments, meaning, additional_definitions="", part_of_speech=(), tags=(), level, sentence=None)` with property `usually_kana`
  - `ImportedDeck(vocab: list[Vocab], sha256: str)` frozen dataclass
  - `kana_id(script, char) -> "kana:hira:あ"`, `kanji_id(char) -> "kanji:漢"`, `vocab_id(expression, reading) -> "vocab:{expression}:{reading}"`
- Produces (`tests/base.py`): `make_vocab(expression, reading, level, *, tags, sentence)`, `make_kanji_details(**overrides)`, `FakeKanjiSource(details)`, fixtures `app_config`, `quiet_logger`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_text.py`:

```python
import pytest

from bunsho.text import extract_kanji, is_kanji


@pytest.mark.parametrize(
    ("char", "expected"),
    [("日", True), ("あ", False), ("A", False), ("々", False), ("", False), ("日本", False)],
)
def test_is_kanji(char: str, expected: bool) -> None:
    assert is_kanji(char) is expected


def test_extract_kanji_keeps_order_and_repeats() -> None:
    assert extract_kanji("日本の日曜日") == ["日", "本", "日", "曜", "日"]
    assert extract_kanji("ユニフォーム") == []
```

`tests/unit/models/test_content.py` (add empty `tests/unit/models/__init__.py`):

```python
import pytest
from pydantic import ValidationError

from bunsho.models.content import (
    JlptLevel,
    KanaScript,
    RubySegment,
    Sentence,
    kana_id,
    kanji_id,
    vocab_id,
)
from tests.base import make_vocab


@pytest.mark.parametrize(
    ("tag", "level"),
    [
        ("jlpt_N5", JlptLevel.N5),
        ("jlpt_N1", JlptLevel.N1),
        ("jlpt_N6", None),
        ("usually_kana", None),
        ("jlpt_n3", None),
    ],
)
def test_level_from_tag(tag: str, level: JlptLevel | None) -> None:
    assert JlptLevel.from_tag(tag) is level


def test_level_order_and_label() -> None:
    assert JlptLevel.study_order() == (
        JlptLevel.N5,
        JlptLevel.N4,
        JlptLevel.N3,
        JlptLevel.N2,
        JlptLevel.N1,
    )
    assert JlptLevel.N5 > JlptLevel.N1  # higher number = easier
    assert JlptLevel.N3.label == "N3"


def test_stable_ids() -> None:
    assert kana_id(KanaScript.HIRAGANA, "あ") == "kana:hira:あ"
    assert kanji_id("漢") == "kanji:漢"
    assert vocab_id("体", "からだ") == "vocab:体:からだ"


def test_vocab_usually_kana_and_json_round_trip() -> None:
    assert make_vocab(tags=("usually_kana",)).usually_kana is True
    assert make_vocab().usually_kana is False
    sentence = Sentence(
        segments=(RubySegment(base="猫", reading="ねこ", highlighted=True),), english="cat"
    )
    vocab = make_vocab(sentence=sentence)
    assert type(vocab).model_validate_json(vocab.model_dump_json()) == vocab


def test_models_are_frozen() -> None:
    vocab = make_vocab()
    with pytest.raises(ValidationError):
        vocab.expression = "x"  # type: ignore[misc]
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_text.py tests/unit/models -v`
Expected: FAIL (modules missing).

- [ ] **Step 3: Implement**

`src/bunsho/text.py`:

```python
"""Small Japanese text helpers."""

from __future__ import annotations


def is_kanji(char: str) -> bool:
    """Return whether ``char`` is a single CJK ideograph (iteration mark ``々`` excluded)."""
    return len(char) == 1 and ("一" <= char <= "鿿" or "㐀" <= char <= "䶿")


def extract_kanji(text: str) -> list[str]:
    """Return every kanji in ``text`` in order, keeping repeats."""
    return [char for char in text if is_kanji(char)]
```

`src/bunsho/models/content.py`:

```python
"""Domain models for study content (kana, kanji, vocabulary, sentences)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum, StrEnum

from pydantic import BaseModel, ConfigDict

_LEVEL_TAG = re.compile(r"jlpt_N([1-5])")


class JlptLevel(IntEnum):
    """JLPT level. As on the exam, a higher number is easier (N5 is the easiest)."""

    N1 = 1
    N2 = 2
    N3 = 3
    N4 = 4
    N5 = 5

    @property
    def label(self) -> str:
        """Human-readable name such as ``N3``."""
        return f"N{self.value}"

    @classmethod
    def from_tag(cls, tag: str) -> JlptLevel | None:
        """Parse an Anki tag such as ``jlpt_N3``; return ``None`` for other tags."""
        match = _LEVEL_TAG.fullmatch(tag)
        return cls(int(match.group(1))) if match else None

    @classmethod
    def study_order(cls) -> tuple[JlptLevel, ...]:
        """Levels from easiest to hardest: N5, N4, N3, N2, N1."""
        return (cls.N5, cls.N4, cls.N3, cls.N2, cls.N1)


class KanaScript(StrEnum):
    """Kana writing system."""

    HIRAGANA = "hira"
    KATAKANA = "kata"


class KanaKind(StrEnum):
    """Kana category."""

    BASIC = "basic"
    DAKUTEN = "dakuten"
    YOUON = "youon"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class RubySegment(_Frozen):
    """A run of text, optionally with a furigana reading."""

    base: str
    reading: str | None = None
    highlighted: bool = False


class Sentence(_Frozen):
    """A Japanese example sentence with its English translation."""

    segments: tuple[RubySegment, ...]
    english: str


class Kana(_Frozen):
    """A single kana character (or yōon combination)."""

    id: str
    script: KanaScript
    char: str
    romaji: str
    kind: KanaKind
    group: str


class KanjiDetails(_Frozen):
    """Dictionary facts about a kanji (from KANJIDIC2 via jamdict)."""

    meanings: tuple[str, ...] = ()
    on_readings: tuple[str, ...] = ()
    kun_readings: tuple[str, ...] = ()
    stroke_count: int | None = None
    grade: int | None = None
    frequency: int | None = None
    radical: int | None = None


class Kanji(KanjiDetails):
    """A kanji with its derived JLPT level."""

    id: str
    char: str
    level: JlptLevel


class Vocab(_Frozen):
    """A vocabulary item imported from the JLPT deck."""

    id: str
    expression: str
    reading: str
    reading_segments: tuple[RubySegment, ...]
    meaning: str
    additional_definitions: str = ""
    part_of_speech: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    level: JlptLevel
    sentence: Sentence | None = None

    @property
    def usually_kana(self) -> bool:
        """Whether the deck marks this word as usually written in kana."""
        return "usually_kana" in self.tags


@dataclass(frozen=True, slots=True)
class ImportedDeck:
    """Result of importing a vocabulary deck."""

    vocab: list[Vocab]
    sha256: str


def kana_id(script: KanaScript, char: str) -> str:
    """Stable ID for a kana, e.g. ``kana:hira:あ``."""
    return f"kana:{script.value}:{char}"


def kanji_id(char: str) -> str:
    """Stable ID for a kanji, e.g. ``kanji:漢``."""
    return f"kanji:{char}"


def vocab_id(expression: str, reading: str) -> str:
    """Stable ID for a vocab item; ``reading`` is the plain kana reading."""
    return f"vocab:{expression}:{reading}"
```

`src/bunsho/models/__init__.py`:

```python
"""Domain models."""

from bunsho.models.content import (
    ImportedDeck,
    JlptLevel,
    Kana,
    KanaKind,
    KanaScript,
    Kanji,
    KanjiDetails,
    RubySegment,
    Sentence,
    Vocab,
    kana_id,
    kanji_id,
    vocab_id,
)

__all__ = [
    "ImportedDeck",
    "JlptLevel",
    "Kana",
    "KanaKind",
    "KanaScript",
    "Kanji",
    "KanjiDetails",
    "RubySegment",
    "Sentence",
    "Vocab",
    "kana_id",
    "kanji_id",
    "vocab_id",
]
```

`tests/base.py` (shared builders and fixtures; new test files import from here):

```python
"""Shared test builders and fixtures for Bunshō."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from bunsho.config.settings import DEFAULT_DECK_FILENAME, DEFAULT_DECK_SHA256, AppConfig
from bunsho.models.content import (
    JlptLevel,
    KanjiDetails,
    RubySegment,
    Sentence,
    Vocab,
    vocab_id,
)


def make_vocab(
    expression: str = "日本",
    reading: str = "にほん",
    level: JlptLevel = JlptLevel.N5,
    *,
    tags: tuple[str, ...] = (),
    sentence: Sentence | None = None,
) -> Vocab:
    """Build a ``Vocab`` with sensible defaults for tests."""
    return Vocab(
        id=vocab_id(expression, reading),
        expression=expression,
        reading=reading,
        reading_segments=(RubySegment(base=expression, reading=reading),),
        meaning="test meaning",
        part_of_speech=("noun",),
        tags=tags,
        level=level,
        sentence=sentence,
    )


def make_kanji_details(**overrides: object) -> KanjiDetails:
    """Build ``KanjiDetails`` with defaults, overriding any field by keyword."""
    values: dict[str, object] = {
        "meanings": ("day",),
        "on_readings": ("ニチ",),
        "kun_readings": ("ひ",),
        "stroke_count": 4,
        "grade": 1,
        "frequency": 1,
        "radical": 72,
    }
    values.update(overrides)
    return KanjiDetails.model_validate(values)


class FakeKanjiSource:
    """In-memory kanji source for unit tests (duck-types ``KanjiInfoSource``)."""

    def __init__(self, details: dict[str, KanjiDetails] | None = None) -> None:
        self.details = details or {}
        self.calls: list[str] = []

    def get_kanji(self, char: str) -> KanjiDetails | None:
        """Return canned details, recording each lookup."""
        self.calls.append(char)
        return self.details.get(char)


@pytest.fixture
def app_config(tmp_path: Path) -> AppConfig:
    """An ``AppConfig`` rooted in a temporary directory."""
    return AppConfig(
        data_dir=tmp_path / "data",
        resources_dir=tmp_path / "resources",
        deck_filename=DEFAULT_DECK_FILENAME,
        deck_sha256=DEFAULT_DECK_SHA256,
        jamdict_db=None,
        log_level="INFO",
    )


@pytest.fixture
def quiet_logger() -> logging.Logger:
    """A logger that stays out of test output."""
    logger = logging.getLogger("bunsho.tests")
    logger.setLevel(logging.CRITICAL)
    return logger
```

`tests/conftest.py`:

```python
"""Make shared fixtures from ``tests.base`` available to every test module."""

from tests.base import app_config, quiet_logger

__all__ = ["app_config", "quiet_logger"]
```

- [ ] **Step 4: Run tests and gates**

Run: `uv run pytest tests/unit -v && uv run ruff check . && uv run ruff format --check . && uv run mypy src/`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bunsho/text.py src/bunsho/models tests
git commit -m "feat(models): content domain models, stable IDs and shared test base"
```

---

### Task 4: Furigana parser

**Files:**
- Create: `src/bunsho/services/__init__.py` (empty docstring module), `src/bunsho/services/furigana.py`
- Test: `tests/unit/services/test_furigana.py` (add empty `tests/unit/services/__init__.py`)

**Interfaces:**
- Consumes: `RubySegment` (Task 3).
- Produces: `parse_furigana(text: str) -> tuple[RubySegment, ...]`, `plain_reading(segments: Sequence[RubySegment]) -> str`, `plain_text(segments: Sequence[RubySegment]) -> str`.

Format rules (verified against the deck): a ruby base is the run of non-space characters immediately before `[reading]`; the base starts at the string start, after one whitespace character (which is a delimiter and is dropped), or directly after a previous `]`. `<mark>...</mark>` toggles `highlighted`; any other tag is stripped.

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from bunsho.models.content import RubySegment
from bunsho.services.furigana import parse_furigana, plain_reading, plain_text

SENTENCE = "我々[われわれ]は 別[わか]れて<mark>別々[べつべつ]</mark>の 道[みち]を 行[い]った。"


def test_word_with_okurigana() -> None:
    assert parse_furigana("体[からだ]つき") == (
        RubySegment(base="体", reading="からだ"),
        RubySegment(base="つき"),
    )


def test_kana_only_word_is_one_plain_segment() -> None:
    assert parse_furigana("ユニフォーム") == (RubySegment(base="ユニフォーム"),)


def test_sentence_with_highlight() -> None:
    assert parse_furigana(SENTENCE) == (
        RubySegment(base="我々", reading="われわれ"),
        RubySegment(base="は"),
        RubySegment(base="別", reading="わか"),
        RubySegment(base="れて"),
        RubySegment(base="別々", reading="べつべつ", highlighted=True),
        RubySegment(base="の"),
        RubySegment(base="道", reading="みち"),
        RubySegment(base="を"),
        RubySegment(base="行", reading="い"),
        RubySegment(base="った。"),
    )


def test_plain_projections() -> None:
    segments = parse_furigana(SENTENCE)
    assert plain_reading(segments) == "われわれはわかれてべつべつのみちをいった。"
    assert plain_text(segments) == "我々は別れて別々の道を行った。"


def test_adjacent_rubies_without_space() -> None:
    assert parse_furigana("漢[かん]字[じ]") == (
        RubySegment(base="漢", reading="かん"),
        RubySegment(base="字", reading="じ"),
    )


def test_other_tags_are_stripped_and_do_not_highlight() -> None:
    assert parse_furigana("<b>猫[ねこ]</b>") == (RubySegment(base="猫", reading="ねこ"),)


@pytest.mark.parametrize("text", ["", "<mark></mark>"])
def test_empty_input(text: str) -> None:
    assert parse_furigana(text) == ()


def test_unbalanced_bracket_is_kept_literally() -> None:
    assert parse_furigana("a[b") == (RubySegment(base="a[b"),)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/services/test_furigana.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

`src/bunsho/services/__init__.py`:

```python
"""Services: parsing, dictionary access, storage."""
```

`src/bunsho/services/furigana.py`:

```python
"""Parser for Anki-style furigana markup, e.g. ``漢字[かんじ]``."""

from __future__ import annotations

import re
from collections.abc import Sequence

from bunsho.models.content import RubySegment

_TAG = re.compile(r"(<[^>]*>)")
_RUBY = re.compile(r"(?:^|\s|(?<=\]))([^\s\[\]]+)\[([^\]]+)\]")


def parse_furigana(text: str) -> tuple[RubySegment, ...]:
    """Split furigana markup into ruby segments.

    ``<mark>`` regions produce ``highlighted`` segments; all other HTML tags are dropped.

    Args:
        text: Markup such as ``体[からだ]つき``.

    Returns:
        Segments in reading order; empty for empty input.

    Examples:
        >>> parse_furigana("体[からだ]つき")[0].reading
        'からだ'
    """
    segments: list[RubySegment] = []
    highlighted = False
    for part in _TAG.split(text):
        if part == "<mark>":
            highlighted = True
        elif part == "</mark>":
            highlighted = False
        elif not part or _TAG.fullmatch(part):
            continue
        else:
            segments.extend(_parse_chunk(part, highlighted))
    return tuple(segments)


def _parse_chunk(chunk: str, highlighted: bool) -> list[RubySegment]:
    segments: list[RubySegment] = []
    cursor = 0
    for match in _RUBY.finditer(chunk):
        if match.start() > cursor:
            segments.append(RubySegment(base=chunk[cursor : match.start()], highlighted=highlighted))
        segments.append(
            RubySegment(base=match.group(1), reading=match.group(2), highlighted=highlighted)
        )
        cursor = match.end()
    if cursor < len(chunk):
        segments.append(RubySegment(base=chunk[cursor:], highlighted=highlighted))
    return segments


def plain_reading(segments: Sequence[RubySegment]) -> str:
    """Return the all-kana reading (rubies replaced by their readings)."""
    return "".join(segment.reading or segment.base for segment in segments)


def plain_text(segments: Sequence[RubySegment]) -> str:
    """Return the text as written, without furigana."""
    return "".join(segment.base for segment in segments)
```

- [ ] **Step 4: Run tests and gates**

Run: `uv run pytest tests/unit/services/test_furigana.py -v && uv run ruff check . && uv run ruff format --check . && uv run mypy src/`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bunsho/services tests/unit/services
git commit -m "feat(services): furigana markup parser"
```

---

### Task 5: Kana source

**Files:**
- Create: `src/bunsho/services/kana_source.py`
- Test: `tests/unit/services/test_kana_source.py`

**Interfaces:**
- Consumes: `Kana`, `KanaKind`, `KanaScript`, `kana_id` (Task 3).
- Produces: `KanaSource().all_kana() -> list[Kana]` returning 208 entries (104 hiragana, then 104 katakana), each script ordered basic → dakuten → yōon. Romaji is Hepburn (`ぢ`=`ji`, `づ`=`zu`).

- [ ] **Step 1: Write the failing tests**

```python
from collections import Counter

from bunsho.models.content import KanaKind, KanaScript
from bunsho.services.kana_source import KanaSource


def test_counts_per_script_and_kind() -> None:
    kana = KanaSource().all_kana()
    counts = Counter((k.script, k.kind) for k in kana)
    for script in (KanaScript.HIRAGANA, KanaScript.KATAKANA):
        assert counts[(script, KanaKind.BASIC)] == 46
        assert counts[(script, KanaKind.DAKUTEN)] == 25
        assert counts[(script, KanaKind.YOUON)] == 33
    assert len(kana) == 208


def test_ids_are_unique_and_stable_format() -> None:
    kana = KanaSource().all_kana()
    assert len({k.id for k in kana}) == len(kana)
    assert kana[0].id == "kana:hira:あ"


def test_katakana_mirrors_hiragana() -> None:
    by_id = {k.id: k for k in KanaSource().all_kana()}
    assert by_id["kana:kata:ア"].romaji == "a"
    assert by_id["kana:kata:ン"].romaji == "n"
    assert by_id["kana:kata:シャ"].romaji == "sha"
    assert by_id["kana:hira:しゃ"].kind is KanaKind.YOUON
    assert by_id["kana:hira:が"].kind is KanaKind.DAKUTEN
    assert by_id["kana:hira:を"].romaji == "wo"


def test_order_is_basic_then_dakuten_then_youon() -> None:
    kinds = [k.kind for k in KanaSource().all_kana()[:104]]
    assert kinds == [KanaKind.BASIC] * 46 + [KanaKind.DAKUTEN] * 25 + [KanaKind.YOUON] * 33
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/services/test_kana_source.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

```python
"""Static hiragana and katakana tables."""

from __future__ import annotations

from collections.abc import Callable

from bunsho.models.content import Kana, KanaKind, KanaScript, kana_id

_Row = tuple[str, str]

_BASIC: tuple[tuple[str, tuple[_Row, ...]], ...] = (
    ("vowels", (("あ", "a"), ("い", "i"), ("う", "u"), ("え", "e"), ("お", "o"))),
    ("k", (("か", "ka"), ("き", "ki"), ("く", "ku"), ("け", "ke"), ("こ", "ko"))),
    ("s", (("さ", "sa"), ("し", "shi"), ("す", "su"), ("せ", "se"), ("そ", "so"))),
    ("t", (("た", "ta"), ("ち", "chi"), ("つ", "tsu"), ("て", "te"), ("と", "to"))),
    ("n", (("な", "na"), ("に", "ni"), ("ぬ", "nu"), ("ね", "ne"), ("の", "no"))),
    ("h", (("は", "ha"), ("ひ", "hi"), ("ふ", "fu"), ("へ", "he"), ("ほ", "ho"))),
    ("m", (("ま", "ma"), ("み", "mi"), ("む", "mu"), ("め", "me"), ("も", "mo"))),
    ("y", (("や", "ya"), ("ゆ", "yu"), ("よ", "yo"))),
    ("r", (("ら", "ra"), ("り", "ri"), ("る", "ru"), ("れ", "re"), ("ろ", "ro"))),
    ("w", (("わ", "wa"), ("を", "wo"))),
    ("n-final", (("ん", "n"),)),
)

_DAKUTEN: tuple[tuple[str, tuple[_Row, ...]], ...] = (
    ("g", (("が", "ga"), ("ぎ", "gi"), ("ぐ", "gu"), ("げ", "ge"), ("ご", "go"))),
    ("z", (("ざ", "za"), ("じ", "ji"), ("ず", "zu"), ("ぜ", "ze"), ("ぞ", "zo"))),
    ("d", (("だ", "da"), ("ぢ", "ji"), ("づ", "zu"), ("で", "de"), ("ど", "do"))),
    ("b", (("ば", "ba"), ("び", "bi"), ("ぶ", "bu"), ("べ", "be"), ("ぼ", "bo"))),
    ("p", (("ぱ", "pa"), ("ぴ", "pi"), ("ぷ", "pu"), ("ぺ", "pe"), ("ぽ", "po"))),
)

_SMALL_Y = ("ゃ", "ゅ", "ょ")
_YOUON: tuple[tuple[str, tuple[str, str, str]], ...] = (
    ("き", ("kya", "kyu", "kyo")),
    ("し", ("sha", "shu", "sho")),
    ("ち", ("cha", "chu", "cho")),
    ("に", ("nya", "nyu", "nyo")),
    ("ひ", ("hya", "hyu", "hyo")),
    ("み", ("mya", "myu", "myo")),
    ("り", ("rya", "ryu", "ryo")),
    ("ぎ", ("gya", "gyu", "gyo")),
    ("じ", ("ja", "ju", "jo")),
    ("び", ("bya", "byu", "byo")),
    ("ぴ", ("pya", "pyu", "pyo")),
)

_Entry = tuple[str, str, str, KanaKind]


def _hiragana_entries() -> list[_Entry]:
    entries: list[_Entry] = []
    for kind, table in ((KanaKind.BASIC, _BASIC), (KanaKind.DAKUTEN, _DAKUTEN)):
        for group, rows in table:
            entries.extend((char, romaji, group, kind) for char, romaji in rows)
    for base, romaji_forms in _YOUON:
        for small, romaji in zip(_SMALL_Y, romaji_forms, strict=True):
            entries.append((base + small, romaji, "youon", KanaKind.YOUON))
    return entries


def _to_katakana(text: str) -> str:
    """Shift hiragana code points (U+3041..U+3096) to katakana (+0x60)."""
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in text)


def _identity(text: str) -> str:
    return text


class KanaSource:
    """Provides the full hiragana and katakana study set."""

    def all_kana(self) -> list[Kana]:
        """Return 104 hiragana followed by 104 katakana."""
        entries = _hiragana_entries()
        converters: tuple[tuple[KanaScript, Callable[[str], str]], ...] = (
            (KanaScript.HIRAGANA, _identity),
            (KanaScript.KATAKANA, _to_katakana),
        )
        return [
            Kana(
                id=kana_id(script, glyph),
                script=script,
                char=glyph,
                romaji=romaji,
                kind=kind,
                group=group,
            )
            for script, convert in converters
            for char, romaji, group, kind in entries
            for glyph in (convert(char),)
        ]
```

- [ ] **Step 4: Run tests and gates**

Run: `uv run pytest tests/unit/services/test_kana_source.py -v && uv run ruff check . && uv run ruff format --check . && uv run mypy src/`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bunsho/services/kana_source.py tests/unit/services/test_kana_source.py
git commit -m "feat(services): hiragana and katakana source"
```

---

### Task 6: Anki deck importer

**Files:**
- Create: `src/bunsho/services/anki_importer.py`, `tests/apkg_builder.py`
- Test: `tests/unit/services/test_anki_importer.py`

**Interfaces:**
- Consumes: `parse_furigana`, `plain_reading` (Task 4); `Vocab`, `Sentence`, `JlptLevel`, `ImportedDeck`, `vocab_id` (Task 3).
- Produces:
  - Exceptions: `DeckImportError(Exception)`, `DeckIntegrityError`, `DeckFormatError`, `DuplicateContentIdError` (all subclass `DeckImportError`)
  - `sha256_of(path: Path) -> str`
  - `AnkiDeckImporter(expected_sha256: str, logger: logging.Logger | None = None)` with `import_vocab(deck_path: Path) -> ImportedDeck`
- Test helper: `build_apkg(path: Path, notes: Sequence[SyntheticNote], *, member: str = "collection.anki21", fields: Sequence[str] = DECK_FIELDS) -> str` (returns the file's sha256).

- [ ] **Step 1: Write the test helper and failing tests**

`tests/apkg_builder.py`:

```python
"""Build tiny synthetic ``.apkg`` files for importer tests."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

DECK_FIELDS = (
    "Expression",
    "English definition",
    "Reading",
    "Grammar",
    "Additional definitions",
    "Example JP",
    "Example EN",
)


@dataclass(frozen=True)
class SyntheticNote:
    """One note: field values in ``DECK_FIELDS`` order plus tags."""

    fields: tuple[str, ...]
    tags: tuple[str, ...]


def note(
    expression: str,
    reading: str,
    level_tag: str = "jlpt_N5",
    *,
    meaning: str = "meaning",
    grammar: str = "noun",
    example_jp: str = "",
    example_en: str = "",
    extra_tags: tuple[str, ...] = (),
) -> SyntheticNote:
    """Convenience constructor for a note with the deck's field layout."""
    return SyntheticNote(
        fields=(expression, meaning, reading, grammar, "", example_jp, example_en),
        tags=(level_tag, *extra_tags),
    )


def build_apkg(
    path: Path,
    notes: Sequence[SyntheticNote],
    *,
    member: str = "collection.anki21",
    fields: Sequence[str] = DECK_FIELDS,
    model_count: int = 1,
) -> str:
    """Write a minimal ``.apkg`` and return its sha256 hex digest."""
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE col (models TEXT, decks TEXT)")
    models = {
        str(i): {"name": f"model{i}", "flds": [{"name": n, "ord": o} for o, n in enumerate(fields)]}
        for i in range(model_count)
    }
    con.execute("INSERT INTO col VALUES (?, ?)", (json.dumps(models), "{}"))
    con.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, flds TEXT, tags TEXT)")
    for index, item in enumerate(notes, start=1):
        con.execute(
            "INSERT INTO notes VALUES (?, ?, ?)",
            (index, "\x1f".join(item.fields), f" {' '.join(item.tags)} "),
        )
    data = con.serialize()
    con.close()
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(member, data)
    return hashlib.sha256(path.read_bytes()).hexdigest()
```

`tests/unit/services/test_anki_importer.py`:

```python
import logging
import zipfile
from pathlib import Path

import pytest

from bunsho.models.content import JlptLevel
from bunsho.services.anki_importer import (
    AnkiDeckImporter,
    DeckFormatError,
    DeckImportError,
    DeckIntegrityError,
    DuplicateContentIdError,
    sha256_of,
)
from tests.apkg_builder import DECK_FIELDS, build_apkg, note

SENTENCE_JP = "我々[われわれ]は 別[わか]れて<mark>別々[べつべつ]</mark>の 道[みち]を 行[い]った。"


def _importer(sha: str) -> AnkiDeckImporter:
    return AnkiDeckImporter(sha, logging.getLogger("bunsho.tests"))


def test_imports_fields_levels_tags_and_sentence(tmp_path: Path) -> None:
    deck = tmp_path / "deck.apkg"
    sha = build_apkg(
        deck,
        [
            note(
                "別々", "別々[べつべつ]", "jlpt_N2", meaning="separate", grammar="no adjective, noun",
                example_jp=SENTENCE_JP, example_en="We went our own ways.",
                extra_tags=("usually_kana", "polite/丁寧語"),
            ),
            note("体", "体[からだ]つき", "jlpt_N4"),
        ],
    )
    imported = _importer(sha).import_vocab(deck)
    assert imported.sha256 == sha
    first, second = imported.vocab
    assert first.id == "vocab:別々:べつべつ"
    assert first.level is JlptLevel.N2
    assert first.meaning == "separate"
    assert first.part_of_speech == ("no adjective", "noun")
    assert first.tags == ("usually_kana", "polite/丁寧語")
    assert first.usually_kana
    assert first.sentence is not None
    assert first.sentence.english == "We went our own ways."
    assert any(s.highlighted and s.base == "別々" for s in first.sentence.segments)
    assert second.reading == "からだつき"
    assert second.sentence is None


def test_wrong_checksum_is_rejected(tmp_path: Path) -> None:
    deck = tmp_path / "deck.apkg"
    build_apkg(deck, [note("日", "にち")])
    with pytest.raises(DeckIntegrityError, match="sha256"):
        _importer("0" * 64).import_vocab(deck)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(DeckImportError, match="not found"):
        _importer("0" * 64).import_vocab(tmp_path / "nope.apkg")


def test_falls_back_to_legacy_collection_member(tmp_path: Path) -> None:
    deck = tmp_path / "deck.apkg"
    sha = build_apkg(deck, [note("日", "にち")], member="collection.anki2")
    assert len(_importer(sha).import_vocab(deck).vocab) == 1


def test_unsupported_collection_format(tmp_path: Path) -> None:
    deck = tmp_path / "deck.apkg"
    with zipfile.ZipFile(deck, "w") as archive:
        archive.writestr("collection.anki21b", b"zstd")
    with pytest.raises(DeckFormatError, match="older Anki"):
        _importer(sha256_of(deck)).import_vocab(deck)


def test_missing_required_field(tmp_path: Path) -> None:
    deck = tmp_path / "deck.apkg"
    sha = build_apkg(deck, [], fields=[f for f in DECK_FIELDS if f != "Reading"])
    with pytest.raises(DeckFormatError, match="Reading"):
        _importer(sha).import_vocab(deck)


def test_multiple_models_rejected(tmp_path: Path) -> None:
    deck = tmp_path / "deck.apkg"
    sha = build_apkg(deck, [note("日", "にち")], model_count=2)
    with pytest.raises(DeckFormatError, match="one note type"):
        _importer(sha).import_vocab(deck)


@pytest.mark.parametrize("tag_set", [(), ("jlpt_N5", "jlpt_N4")])
def test_exactly_one_level_tag_required(tmp_path: Path, tag_set: tuple[str, ...]) -> None:
    deck = tmp_path / "deck.apkg"
    item = note("日", "にち")
    item = type(item)(fields=item.fields, tags=tag_set)
    sha = build_apkg(deck, [item])
    with pytest.raises(DeckFormatError, match="JLPT tag"):
        _importer(sha).import_vocab(deck)


def test_duplicate_expression_and_reading_is_rejected(tmp_path: Path) -> None:
    deck = tmp_path / "deck.apkg"
    sha = build_apkg(deck, [note("日", "にち"), note("日", "にち", "jlpt_N4")])
    with pytest.raises(DuplicateContentIdError, match="vocab:日:にち"):
        _importer(sha).import_vocab(deck)


def test_same_expression_different_reading_is_allowed(tmp_path: Path) -> None:
    deck = tmp_path / "deck.apkg"
    sha = build_apkg(deck, [note("日", "ひ"), note("日", "にち")])
    assert len(_importer(sha).import_vocab(deck).vocab) == 2
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/services/test_anki_importer.py -v`
Expected: FAIL (`ModuleNotFoundError: bunsho.services.anki_importer`).

- [ ] **Step 3: Implement**

`src/bunsho/services/anki_importer.py`:

```python
"""Importer for the community JLPT vocabulary Anki deck (``.apkg``)."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import zipfile
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

from bunsho.models.content import ImportedDeck, JlptLevel, Sentence, Vocab, vocab_id
from bunsho.services.furigana import parse_furigana, plain_reading

REQUIRED_FIELDS = ("Expression", "English definition", "Reading")
_COLLECTION_MEMBERS = ("collection.anki21", "collection.anki2")
_FIELD_SEPARATOR = "\x1f"


class DeckImportError(Exception):
    """Base class for deck import failures."""


class DeckIntegrityError(DeckImportError):
    """The deck file does not match the pinned checksum."""


class DeckFormatError(DeckImportError):
    """The deck structure is not what the importer expects."""


class DuplicateContentIdError(DeckImportError):
    """Two notes map to the same stable content ID."""


def sha256_of(path: Path) -> str:
    """Return the hex SHA-256 digest of a file, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class AnkiDeckImporter:
    """Reads vocabulary notes from a checksum-pinned ``.apkg`` file."""

    def __init__(self, expected_sha256: str, logger: logging.Logger | None = None) -> None:
        """Create an importer.

        Args:
            expected_sha256: Lowercase hex digest the deck must match.
            logger: Logger for structured progress messages.
        """
        self._expected_sha256 = expected_sha256
        self._logger = logger or logging.getLogger(__name__)

    def import_vocab(self, deck_path: Path) -> ImportedDeck:
        """Import every note as a ``Vocab`` in deck order.

        Args:
            deck_path: Path to the ``.apkg`` file.

        Returns:
            The vocabulary plus the verified checksum.

        Raises:
            DeckImportError: The file is missing.
            DeckIntegrityError: The checksum differs from the pinned value.
            DeckFormatError: The archive or its notes are malformed.
            DuplicateContentIdError: Two notes share ``expression`` and reading.
        """
        if not deck_path.is_file():
            raise DeckImportError(f"deck file not found: {deck_path}")
        digest = sha256_of(deck_path)
        if digest != self._expected_sha256:
            raise DeckIntegrityError(
                f"deck sha256 mismatch for {deck_path.name}: expected {self._expected_sha256}, "
                f"got {digest}. If you replaced the deck on purpose, update paths.deck_sha256."
            )
        with zipfile.ZipFile(deck_path) as archive:
            collection = _read_collection(archive)
        vocab: list[Vocab] = []
        seen: dict[str, str] = {}
        for fields, tags in _iter_notes(collection):
            item = _to_vocab(fields, tags)
            if item.id in seen:
                raise DuplicateContentIdError(f"duplicate content id {item.id}")
            seen[item.id] = item.expression
            vocab.append(item)
        self._logger.info(
            "deck_import path=%s notes=%d sha256=%s", deck_path.name, len(vocab), digest
        )
        return ImportedDeck(vocab=vocab, sha256=digest)


def _read_collection(archive: zipfile.ZipFile) -> bytes:
    names = set(archive.namelist())
    for member in _COLLECTION_MEMBERS:
        if member in names:
            return archive.read(member)
    raise DeckFormatError(
        "no readable collection found (looked for "
        f"{', '.join(_COLLECTION_MEMBERS)}); re-export the deck with "
        "'Support older Anki versions' enabled"
    )


def _iter_notes(collection: bytes) -> Iterator[tuple[dict[str, str], list[str]]]:
    with closing(sqlite3.connect(":memory:")) as con:
        con.deserialize(collection)
        row = con.execute("SELECT models FROM col").fetchone()
        models = json.loads(row[0])
        if len(models) != 1:
            raise DeckFormatError(f"expected one note type, found {len(models)}")
        model = next(iter(models.values()))
        names = [f["name"] for f in sorted(model["flds"], key=lambda f: f["ord"])]
        missing = [name for name in REQUIRED_FIELDS if name not in names]
        if missing:
            raise DeckFormatError(f"deck is missing required field(s): {', '.join(missing)}")
        for flds, tags in con.execute("SELECT flds, tags FROM notes ORDER BY id"):
            values = flds.split(_FIELD_SEPARATOR)
            if len(values) != len(names):
                raise DeckFormatError(
                    f"note has {len(values)} fields, expected {len(names)}: {flds[:40]!r}"
                )
            yield dict(zip(names, values, strict=True)), tags.split()


def _to_vocab(fields: dict[str, str], tags: list[str]) -> Vocab:
    expression = fields["Expression"].strip()
    levels = [level for tag in tags if (level := JlptLevel.from_tag(tag)) is not None]
    if len(levels) != 1:
        raise DeckFormatError(
            f"note {expression!r} has {len(levels)} JLPT tag(s); expected exactly 1"
        )
    segments = parse_furigana(fields["Reading"].strip())
    reading = plain_reading(segments)
    example_jp = fields.get("Example JP", "").strip()
    sentence = (
        Sentence(segments=parse_furigana(example_jp), english=fields.get("Example EN", "").strip())
        if example_jp
        else None
    )
    return Vocab(
        id=vocab_id(expression, reading),
        expression=expression,
        reading=reading,
        reading_segments=segments,
        meaning=fields["English definition"].strip(),
        additional_definitions=fields.get("Additional definitions", "").strip(),
        part_of_speech=tuple(
            part.strip() for part in fields.get("Grammar", "").split(",") if part.strip()
        ),
        tags=tuple(tag for tag in tags if JlptLevel.from_tag(tag) is None),
        level=levels[0],
        sentence=sentence,
    )
```

- [ ] **Step 4: Run tests and gates**

Run: `uv run pytest tests/unit/services/test_anki_importer.py -v && uv run ruff check . && uv run ruff format --check . && uv run mypy src/`
Expected: PASS. (`test_missing_required_field` builds an empty deck, so no notes are iterated; the field check runs before the loop.)

- [ ] **Step 5: Commit**

```bash
git add src/bunsho/services/anki_importer.py tests/apkg_builder.py tests/unit/services/test_anki_importer.py
git commit -m "feat(services): checksum-pinned Anki deck importer"
```

---

### Task 7: Service protocols and kanji level derivation

**Files:**
- Create: `src/bunsho/services/protocols.py`, `src/bunsho/services/kanji_levels.py`
- Test: `tests/unit/services/test_kanji_levels.py`

**Interfaces:**
- Consumes: `Vocab`, `JlptLevel`, `Kana`, `Kanji`, `KanjiDetails`, `ImportedDeck` (Task 3); `extract_kanji` (Task 3).
- Produces:
  - `DeckImporter` Protocol: `import_vocab(self, deck_path: Path) -> ImportedDeck`
  - `KanaProvider` Protocol: `all_kana(self) -> list[Kana]`
  - `KanjiInfoSource` Protocol: `get_kanji(self, char: str) -> KanjiDetails | None`
  - `ContentWriting` Protocol: `write(self, target: Path, *, kana: Sequence[Kana], kanji: Sequence[Kanji], vocab: Sequence[Vocab], meta: Mapping[str, str]) -> None`
  - `derive_kanji_levels(vocab: Iterable[Vocab]) -> dict[str, JlptLevel]` — each kanji found in a word's `expression` gets the **easiest** level (highest number) of any word containing it; result is independent of input order.

- [ ] **Step 1: Write the failing tests**

```python
from bunsho.models.content import JlptLevel
from bunsho.services.kanji_levels import derive_kanji_levels
from tests.base import make_vocab


def test_kanji_gets_easiest_level_of_any_word() -> None:
    vocab = [
        make_vocab("日曜日", "にちようび", JlptLevel.N4),
        make_vocab("日本", "にほん", JlptLevel.N5),
    ]
    levels = derive_kanji_levels(vocab)
    assert levels == {"日": JlptLevel.N5, "曜": JlptLevel.N4, "本": JlptLevel.N5}


def test_result_is_order_independent() -> None:
    vocab = [make_vocab("日本", "にほん", JlptLevel.N5), make_vocab("日曜日", "にちようび", JlptLevel.N4)]
    assert derive_kanji_levels(vocab) == derive_kanji_levels(list(reversed(vocab)))


def test_kana_only_words_contribute_nothing() -> None:
    assert derive_kanji_levels([make_vocab("ユニフォーム", "ゆにふぉーむ")]) == {}


def test_hard_word_alone_keeps_its_level() -> None:
    assert derive_kanji_levels([make_vocab("憂鬱", "ゆううつ", JlptLevel.N1)]) == {
        "憂": JlptLevel.N1,
        "鬱": JlptLevel.N1,
    }
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/services/test_kanji_levels.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

`src/bunsho/services/kanji_levels.py`:

```python
"""Derive JLPT levels for kanji from the vocabulary that uses them."""

from __future__ import annotations

from collections.abc import Iterable

from bunsho.models.content import JlptLevel, Vocab
from bunsho.text import extract_kanji


def derive_kanji_levels(vocab: Iterable[Vocab]) -> dict[str, JlptLevel]:
    """Assign each kanji the easiest level of any word whose expression contains it.

    The JLPT publishes no official kanji lists, so a kanji is treated as "learned" at the
    first (easiest) level where it shows up in vocabulary. N5 is the easiest level and has
    the highest numeric value.

    Args:
        vocab: Vocabulary items with levels.

    Returns:
        Mapping of kanji character to derived level.
    """
    levels: dict[str, JlptLevel] = {}
    for item in vocab:
        for char in extract_kanji(item.expression):
            current = levels.get(char)
            if current is None or item.level > current:
                levels[char] = item.level
    return levels
```

`src/bunsho/services/protocols.py`:

```python
"""Ports (interfaces) the content pipeline depends on."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from bunsho.models.content import ImportedDeck, Kana, Kanji, KanjiDetails, Vocab


class DeckImporter(Protocol):
    """Reads vocabulary from a deck file."""

    def import_vocab(self, deck_path: Path) -> ImportedDeck:
        """Import all vocabulary from ``deck_path``."""
        ...


class KanaProvider(Protocol):
    """Supplies the kana study set."""

    def all_kana(self) -> list[Kana]:
        """Return every kana to study."""
        ...


class KanjiInfoSource(Protocol):
    """Looks up dictionary facts about a kanji."""

    def get_kanji(self, char: str) -> KanjiDetails | None:
        """Return details for ``char`` or ``None`` when unknown."""
        ...


class ContentWriting(Protocol):
    """Persists a complete content build."""

    def write(
        self,
        target: Path,
        *,
        kana: Sequence[Kana],
        kanji: Sequence[Kanji],
        vocab: Sequence[Vocab],
        meta: Mapping[str, str],
    ) -> None:
        """Write all content to ``target``."""
        ...
```

- [ ] **Step 4: Run tests and gates**

Run: `uv run pytest tests/unit/services/test_kanji_levels.py -v && uv run ruff check . && uv run ruff format --check . && uv run mypy src/`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bunsho/services/protocols.py src/bunsho/services/kanji_levels.py tests/unit/services/test_kanji_levels.py
git commit -m "feat(services): service protocols and derived kanji levels"
```

---

### Task 8: Jamdict service

**Files:**
- Create: `src/bunsho/services/jamdict_service.py`
- Test: `tests/unit/services/test_jamdict_service.py`, `tests/integration/__init__.py`, `tests/integration/test_jamdict_real.py`

**Interfaces:**
- Consumes: `KanjiDetails` (Task 3); satisfies the `KanjiInfoSource` Protocol (Task 7).
- Produces:
  - `JamdictUnavailableError(RuntimeError)`
  - `JamdictService(db_file: Path | None = None, *, jam: Any | None = None)`; `db_file=None` uses the database bundled with `jamdict-data-fix`; `jam` is a test seam. Construction raises `JamdictUnavailableError` if the database is missing or lacks KANJIDIC2 data.
  - `JamdictService.get_kanji(char: str) -> KanjiDetails | None`. Readings keep KANJIDIC2 notation (`く.う`, `-び`). The old 1-4 `jlpt` field is deliberately ignored.

- [ ] **Step 1: Write the failing tests**

`tests/unit/services/test_jamdict_service.py`:

```python
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from bunsho.services.jamdict_service import JamdictService, JamdictUnavailableError


def _reading(kind: str, value: str) -> SimpleNamespace:
    return SimpleNamespace(r_type=kind, value=value)


def _character(**overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "literal": "日",
        "stroke_count": 4,
        "grade": 1,
        "freq": 1,
        "jlpt": 4,
        "rm_groups": [
            SimpleNamespace(
                readings=[
                    _reading("pinyin", "ri4"),
                    _reading("ja_on", "ニチ"),
                    _reading("ja_on", "ジツ"),
                    _reading("ja_kun", "ひ"),
                    _reading("ja_kun", "-び"),
                ]
            )
        ],
        "radicals": [SimpleNamespace(rad_type="classical", value="72")],
        "meanings": lambda english_only=False: ["day", "sun"] if english_only else ["day", "jour"],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _FakeJam:
    def __init__(self, chars: dict[str, Any], *, available: bool = True, kd2: bool = True) -> None:
        self._chars, self._available, self._kd2 = chars, available, kd2

    def is_available(self) -> bool:
        return self._available

    def has_kd2(self) -> bool:
        return self._kd2

    def get_char(self, literal: str) -> Any:
        return self._chars.get(literal)


def test_maps_character_to_details() -> None:
    service = JamdictService(jam=_FakeJam({"日": _character()}))
    details = service.get_kanji("日")
    assert details is not None
    assert details.meanings == ("day", "sun")  # English only
    assert details.on_readings == ("ニチ", "ジツ")
    assert details.kun_readings == ("ひ", "-び")
    assert details.stroke_count == 4
    assert details.grade == 1
    assert details.frequency == 1
    assert details.radical == 72


def test_unknown_character_returns_none() -> None:
    assert JamdictService(jam=_FakeJam({})).get_kanji("あ") is None


def test_optional_fields_may_be_missing() -> None:
    character = _character(grade=None, freq=None, radicals=[], stroke_count=0)
    details = JamdictService(jam=_FakeJam({"日": character})).get_kanji("日")
    assert details is not None
    assert (details.grade, details.frequency, details.radical, details.stroke_count) == (
        None,
        None,
        None,
        None,
    )


@pytest.mark.parametrize(("available", "kd2"), [(False, True), (True, False)])
def test_unavailable_database_is_an_error(available: bool, kd2: bool) -> None:
    with pytest.raises(JamdictUnavailableError, match="KANJIDIC2"):
        JamdictService(jam=_FakeJam({}, available=available, kd2=kd2))


def test_missing_db_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(JamdictUnavailableError, match="not found"):
        JamdictService(tmp_path / "missing.db")
```

`tests/integration/test_jamdict_real.py` (create empty `tests/integration/__init__.py`):

```python
import pytest

from bunsho.services.jamdict_service import JamdictService, JamdictUnavailableError


@pytest.fixture(scope="module")
def service() -> JamdictService:
    try:
        return JamdictService()
    except JamdictUnavailableError as exc:
        pytest.skip(f"jamdict-data-fix database unavailable: {exc}")


@pytest.mark.integration
def test_real_lookup_of_nichi(service: JamdictService) -> None:
    details = service.get_kanji("日")
    assert details is not None
    assert details.stroke_count == 4
    assert "day" in details.meanings
    assert {"ニチ", "ジツ"} <= set(details.on_readings)
    assert "ひ" in details.kun_readings
    assert details.radical == 72


@pytest.mark.integration
def test_real_lookup_of_non_kanji_is_none(service: JamdictService) -> None:
    assert service.get_kanji("あ") is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/services/test_jamdict_service.py tests/integration/test_jamdict_real.py -v`
Expected: FAIL (`ModuleNotFoundError: bunsho.services.jamdict_service`).

- [ ] **Step 3: Implement**

```python
"""Kanji lookups backed by jamdict (KANJIDIC2 in the jamdict-data-fix database)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jamdict import Jamdict

from bunsho.models.content import KanjiDetails


class JamdictUnavailableError(RuntimeError):
    """The jamdict database is missing or has no KANJIDIC2 data."""


class JamdictService:
    """Read-only access to kanji facts. Not thread-safe; use from one thread at a time."""

    def __init__(self, db_file: Path | None = None, *, jam: Any | None = None) -> None:
        """Open the database.

        Args:
            db_file: Explicit database path; ``None`` uses the ``jamdict-data-fix`` package.
            jam: A pre-built ``Jamdict``-like object (test seam).

        Raises:
            JamdictUnavailableError: The file is missing or lacks KANJIDIC2 data. jamdict
                itself fails silently in these cases, so availability is checked explicitly.
        """
        if jam is None:
            if db_file is None:
                jam = Jamdict()
            else:
                if not db_file.is_file():
                    raise JamdictUnavailableError(f"jamdict database not found: {db_file}")
                path = str(db_file)
                jam = Jamdict(db_file=path, kd2_file=path, jmnedict_file=path, auto_config=False)
        if not (jam.is_available() and jam.has_kd2()):
            raise JamdictUnavailableError(
                "jamdict database is not available or has no KANJIDIC2 data; "
                "install jamdict-data-fix or set paths.jamdict_db"
            )
        self._jam = jam

    def get_kanji(self, char: str) -> KanjiDetails | None:
        """Look up one kanji.

        Args:
            char: A single character.

        Returns:
            Details, or ``None`` when the dictionary has no such kanji.
        """
        character = self._jam.get_char(char)
        if character is None:
            return None
        readings = [r for group in character.rm_groups for r in group.readings]
        radical = next(
            (int(r.value) for r in character.radicals if r.rad_type == "classical"), None
        )
        return KanjiDetails(
            meanings=tuple(character.meanings(english_only=True)),
            on_readings=tuple(r.value for r in readings if r.r_type == "ja_on"),
            kun_readings=tuple(r.value for r in readings if r.r_type == "ja_kun"),
            stroke_count=character.stroke_count or None,
            grade=character.grade,
            frequency=character.freq,
            radical=radical,
        )
```

- [ ] **Step 4: Run tests and gates**

Run: `uv run pytest tests/unit/services/test_jamdict_service.py tests/integration/test_jamdict_real.py -v && uv run ruff check . && uv run ruff format --check . && uv run mypy src/`
Expected: PASS (the two integration tests run against the real 325 MB database bundled with `jamdict-data-fix`).

- [ ] **Step 5: Commit**

```bash
git add src/bunsho/services/jamdict_service.py tests/unit/services/test_jamdict_service.py tests/integration
git commit -m "feat(services): jamdict kanji lookup with explicit availability check"
```

---

### Task 9: Content database writer and repository

**Files:**
- Create: `src/bunsho/services/content_repository.py`
- Test: `tests/unit/services/test_content_repository.py`

**Interfaces:**
- Consumes: `Kana`, `Kanji`, `Vocab`, `JlptLevel`, `KanaScript` (Task 3).
- Produces:
  - `ContentWriter().write(target: Path, *, kana, kanji, vocab, meta) -> None` (satisfies `ContentWriting`). Builds `<target>.tmp` then `os.replace`s it over `target`, so readers never see a half-written file and a failed build leaves any existing `content.db` untouched.
  - `ContentCounts(kana: int, kanji: int, vocab: int)` frozen dataclass
  - `ContentRepository(path: Path)` (raises `FileNotFoundError` if missing) with `counts()`, `meta() -> dict[str, str]`, `list_kana(script: KanaScript | None = None)`, `list_kanji(level: JlptLevel | None = None)`, `list_vocab(level: JlptLevel | None = None)`, `get_kanji(item_id: str) -> Kanji | None`, `get_vocab(item_id: str) -> Vocab | None`. Lists return rows in insertion order. Each read opens a short-lived read-only connection.
- Storage layout: tables `meta`, `kana`, `kanji`, `vocab`; each item row holds `id`, an indexed filter column (`script` or `level`) and the model as JSON in `data`.

- [ ] **Step 1: Write the failing tests**

```python
import sqlite3
from pathlib import Path

import pytest

from bunsho.models.content import (
    JlptLevel,
    Kanji,
    KanaScript,
    kanji_id,
)
from bunsho.services.content_repository import ContentCounts, ContentRepository, ContentWriter
from bunsho.services.kana_source import KanaSource
from tests.base import make_kanji_details, make_vocab


def _kanji(char: str, level: JlptLevel) -> Kanji:
    details = make_kanji_details()
    return Kanji.model_validate({"id": kanji_id(char), "char": char, "level": level, **details.model_dump()})


def _write(target: Path) -> None:
    ContentWriter().write(
        target,
        kana=KanaSource().all_kana(),
        kanji=[_kanji("日", JlptLevel.N5), _kanji("曜", JlptLevel.N4)],
        vocab=[make_vocab("日本", "にほん"), make_vocab("日曜日", "にちようび", JlptLevel.N4)],
        meta={"schema_version": "1", "deck_sha256": "abc"},
    )


def test_round_trip(tmp_path: Path) -> None:
    target = tmp_path / "data" / "content.db"
    _write(target)
    repo = ContentRepository(target)
    assert repo.counts() == ContentCounts(kana=208, kanji=2, vocab=2)
    assert repo.meta() == {"schema_version": "1", "deck_sha256": "abc"}
    assert [k.char for k in repo.list_kanji()] == ["日", "曜"]
    assert [k.char for k in repo.list_kanji(JlptLevel.N4)] == ["曜"]
    assert [v.expression for v in repo.list_vocab(JlptLevel.N5)] == ["日本"]
    assert len(repo.list_kana(KanaScript.KATAKANA)) == 104
    assert len(repo.list_kana()) == 208
    assert repo.get_kanji("kanji:日") is not None
    assert repo.get_vocab("vocab:日本:にほん") == make_vocab("日本", "にほん")
    assert repo.get_kanji("kanji:無") is None
    assert repo.get_vocab("vocab:x:y") is None


def test_no_temp_file_left_behind(tmp_path: Path) -> None:
    target = tmp_path / "content.db"
    _write(target)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["content.db"]


def test_rebuild_replaces_previous_content(tmp_path: Path) -> None:
    target = tmp_path / "content.db"
    _write(target)
    ContentWriter().write(target, kana=[], kanji=[], vocab=[], meta={"schema_version": "2"})
    repo = ContentRepository(target)
    assert repo.counts() == ContentCounts(0, 0, 0)
    assert repo.meta() == {"schema_version": "2"}


def test_failed_build_keeps_existing_database(tmp_path: Path) -> None:
    target = tmp_path / "content.db"
    _write(target)
    duplicate = KanaSource().all_kana()[:1] * 2  # same primary key twice
    with pytest.raises(sqlite3.IntegrityError):
        ContentWriter().write(target, kana=duplicate, kanji=[], vocab=[], meta={})
    assert ContentRepository(target).counts().kana == 208
    assert [p.name for p in tmp_path.iterdir()] == ["content.db"]


def test_repository_requires_existing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="content database"):
        ContentRepository(tmp_path / "nope.db")
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/services/test_content_repository.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

```python
"""SQLite storage for rebuildable study content (``content.db``)."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

from bunsho.models.content import JlptLevel, Kana, KanaScript, Kanji, Vocab

_SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE kana (id TEXT PRIMARY KEY, script TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE kanji (id TEXT PRIMARY KEY, level INTEGER NOT NULL, data TEXT NOT NULL);
CREATE TABLE vocab (id TEXT PRIMARY KEY, level INTEGER NOT NULL, data TEXT NOT NULL);
CREATE INDEX idx_kanji_level ON kanji (level);
CREATE INDEX idx_vocab_level ON vocab (level);
"""


class ContentWriter:
    """Writes a complete content database atomically."""

    def write(
        self,
        target: Path,
        *,
        kana: Sequence[Kana],
        kanji: Sequence[Kanji],
        vocab: Sequence[Vocab],
        meta: Mapping[str, str],
    ) -> None:
        """Build ``target`` from scratch.

        The data is written to ``<target>.tmp`` and moved over ``target`` only after every
        insert succeeded. On failure the temp file is removed and ``target`` is untouched.

        Args:
            target: Destination ``content.db`` path (parent directories are created).
            kana: Kana to store.
            kanji: Kanji to store, in study order.
            vocab: Vocabulary to store, in deck order.
            meta: Build metadata (schema version, deck checksum, counts, ...).

        Raises:
            sqlite3.Error: If any insert fails (for example a duplicate ID).
        """
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f"{target.name}.tmp")
        tmp.unlink(missing_ok=True)
        try:
            with closing(sqlite3.connect(tmp)) as con:
                con.executescript(_SCHEMA)
                with con:
                    con.executemany("INSERT INTO meta (key, value) VALUES (?, ?)", list(meta.items()))
                    con.executemany(
                        "INSERT INTO kana (id, script, data) VALUES (?, ?, ?)",
                        [(k.id, k.script.value, k.model_dump_json()) for k in kana],
                    )
                    con.executemany(
                        "INSERT INTO kanji (id, level, data) VALUES (?, ?, ?)",
                        [(k.id, int(k.level), k.model_dump_json()) for k in kanji],
                    )
                    con.executemany(
                        "INSERT INTO vocab (id, level, data) VALUES (?, ?, ?)",
                        [(v.id, int(v.level), v.model_dump_json()) for v in vocab],
                    )
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        os.replace(tmp, target)


@dataclass(frozen=True, slots=True)
class ContentCounts:
    """Row counts per content type."""

    kana: int
    kanji: int
    vocab: int


class ContentRepository:
    """Read-only queries over ``content.db``."""

    def __init__(self, path: Path) -> None:
        """Open a repository.

        Args:
            path: Location of ``content.db``.

        Raises:
            FileNotFoundError: If the database does not exist.
        """
        if not path.is_file():
            raise FileNotFoundError(f"content database not found: {path}")
        self._uri = f"{path.resolve().as_uri()}?mode=ro"

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self._uri, uri=True)
        try:
            yield con
        finally:
            con.close()

    def counts(self) -> ContentCounts:
        """Return the number of stored items per type."""
        with self._connect() as con:
            return ContentCounts(
                kana=con.execute("SELECT COUNT(*) FROM kana").fetchone()[0],
                kanji=con.execute("SELECT COUNT(*) FROM kanji").fetchone()[0],
                vocab=con.execute("SELECT COUNT(*) FROM vocab").fetchone()[0],
            )

    def meta(self) -> dict[str, str]:
        """Return build metadata."""
        with self._connect() as con:
            return dict(con.execute("SELECT key, value FROM meta").fetchall())

    def list_kana(self, script: KanaScript | None = None) -> list[Kana]:
        """List kana in insertion order, optionally for one script."""
        with self._connect() as con:
            if script is None:
                rows = con.execute("SELECT data FROM kana ORDER BY rowid").fetchall()
            else:
                rows = con.execute(
                    "SELECT data FROM kana WHERE script = ? ORDER BY rowid", (script.value,)
                ).fetchall()
        return [Kana.model_validate_json(row[0]) for row in rows]

    def list_kanji(self, level: JlptLevel | None = None) -> list[Kanji]:
        """List kanji in study order, optionally for one level."""
        with self._connect() as con:
            if level is None:
                rows = con.execute("SELECT data FROM kanji ORDER BY rowid").fetchall()
            else:
                rows = con.execute(
                    "SELECT data FROM kanji WHERE level = ? ORDER BY rowid", (int(level),)
                ).fetchall()
        return [Kanji.model_validate_json(row[0]) for row in rows]

    def list_vocab(self, level: JlptLevel | None = None) -> list[Vocab]:
        """List vocabulary in deck order, optionally for one level."""
        with self._connect() as con:
            if level is None:
                rows = con.execute("SELECT data FROM vocab ORDER BY rowid").fetchall()
            else:
                rows = con.execute(
                    "SELECT data FROM vocab WHERE level = ? ORDER BY rowid", (int(level),)
                ).fetchall()
        return [Vocab.model_validate_json(row[0]) for row in rows]

    def get_kanji(self, item_id: str) -> Kanji | None:
        """Return the kanji with this stable ID, if any."""
        with self._connect() as con:
            row = con.execute("SELECT data FROM kanji WHERE id = ?", (item_id,)).fetchone()
        return Kanji.model_validate_json(row[0]) if row else None

    def get_vocab(self, item_id: str) -> Vocab | None:
        """Return the vocab item with this stable ID, if any."""
        with self._connect() as con:
            row = con.execute("SELECT data FROM vocab WHERE id = ?", (item_id,)).fetchone()
        return Vocab.model_validate_json(row[0]) if row else None
```

- [ ] **Step 4: Run tests and gates**

Run: `uv run pytest tests/unit/services/test_content_repository.py -v && uv run ruff check . && uv run ruff format --check . && uv run mypy src/`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bunsho/services/content_repository.py tests/unit/services/test_content_repository.py
git commit -m "feat(services): atomic content.db writer and read-only repository"
```

---

### Task 10: Content build orchestrator

**Files:**
- Create: `src/bunsho/orchestration/__init__.py`, `src/bunsho/orchestration/content_build.py`
- Test: `tests/unit/orchestration/test_content_build.py` (add empty `tests/unit/orchestration/__init__.py`)

**Interfaces:**
- Consumes: `DeckImporter`, `KanaProvider`, `KanjiInfoSource`, `ContentWriting` (Task 7); `derive_kanji_levels` (Task 7); `Kanji`, `KanjiDetails`, `JlptLevel`, `kanji_id` (Task 3).
- Produces:
  - `ContentBuildError(RuntimeError)`
  - `BuildProgress(stage: str, current: int, total: int)` frozen dataclass; stages in order: `import_deck` (0/1, 1/1), `enrich_kanji` (1..N of N), `write` (0/1, 1/1; skipped in dry run). `ProgressCallback = Callable[[BuildProgress], None]`
  - `BuildReport(dry_run: bool, target: Path, deck_sha256: str, kana_count: int, kanji_count: int, vocab_count: int, sentence_count: int, vocab_by_level: dict[str, int], kanji_by_level: dict[str, int], kanji_without_details: int, duration_seconds: float)` frozen dataclass; the `*_by_level` dicts list only levels that occur, in study order (`"N5"` first).
  - `ContentBuildOrchestrator(importer, kana_provider, kanji_source, writer, logger)` with `build(deck_path: Path, target: Path, *, dry_run: bool = False, on_progress: ProgressCallback | None = None) -> BuildReport`.
- Behaviour: kanji are stored in study order (easiest level first, then by KANJIDIC2 frequency rank ascending with unknown last, then codepoint). A kanji missing from the dictionary is still stored (empty details) and counted in `kanji_without_details`, with a warning. With `dry_run=True` everything is validated and planned but nothing is written.

- [ ] **Step 1: Write the failing tests**

```python
import logging
from pathlib import Path

import pytest

from bunsho.models.content import ImportedDeck, JlptLevel, Vocab
from bunsho.orchestration.content_build import BuildProgress, ContentBuildOrchestrator
from bunsho.services.anki_importer import DeckImportError
from bunsho.services.content_repository import ContentRepository, ContentWriter
from bunsho.services.kana_source import KanaSource
from tests.base import FakeKanjiSource, make_kanji_details, make_vocab


class _FakeImporter:
    def __init__(self, vocab: list[Vocab]) -> None:
        self._vocab = vocab

    def import_vocab(self, deck_path: Path) -> ImportedDeck:
        return ImportedDeck(vocab=self._vocab, sha256="a" * 64)


class _FailingImporter:
    def import_vocab(self, deck_path: Path) -> ImportedDeck:
        raise DeckImportError("boom")


VOCAB = [
    make_vocab("日本", "にほん", JlptLevel.N5),
    make_vocab("日曜日", "にちようび", JlptLevel.N4),
    make_vocab("無", "む", JlptLevel.N5),
]


def _orchestrator(importer: object, source: FakeKanjiSource | None = None) -> ContentBuildOrchestrator:
    source = source or FakeKanjiSource(
        {
            "日": make_kanji_details(frequency=1),
            "本": make_kanji_details(frequency=5),
            "曜": make_kanji_details(frequency=900),
        }
    )
    return ContentBuildOrchestrator(
        importer=importer,  # type: ignore[arg-type]
        kana_provider=KanaSource(),
        kanji_source=source,
        writer=ContentWriter(),
        logger=logging.getLogger("bunsho.tests"),
    )


def test_build_writes_content_and_reports(tmp_path: Path) -> None:
    target = tmp_path / "content.db"
    report = _orchestrator(_FakeImporter(VOCAB)).build(tmp_path / "deck.apkg", target)
    assert report.dry_run is False
    assert (report.kana_count, report.kanji_count, report.vocab_count) == (208, 4, 3)
    assert report.sentence_count == 0
    assert report.vocab_by_level == {"N5": 2, "N4": 1}
    assert report.kanji_by_level == {"N5": 3, "N4": 1}
    assert report.kanji_without_details == 1  # 無 has no dictionary entry
    assert report.deck_sha256 == "a" * 64
    repo = ContentRepository(target)
    assert [k.char for k in repo.list_kanji()] == ["日", "本", "無", "曜"]
    assert repo.meta()["deck_sha256"] == "a" * 64
    assert repo.meta()["vocab"] == "3"
    assert repo.get_kanji("kanji:無") is not None  # stored even without details


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    target = tmp_path / "content.db"
    stages: list[str] = []
    report = _orchestrator(_FakeImporter(VOCAB)).build(
        tmp_path / "deck.apkg", target, dry_run=True, on_progress=lambda p: stages.append(p.stage)
    )
    assert report.dry_run is True
    assert report.kanji_count == 4
    assert not target.exists()
    assert "write" not in stages


def test_progress_reports_every_stage_in_order(tmp_path: Path) -> None:
    events: list[BuildProgress] = []
    _orchestrator(_FakeImporter(VOCAB)).build(
        tmp_path / "deck.apkg", tmp_path / "c.db", on_progress=events.append
    )
    assert events[0] == BuildProgress("import_deck", 0, 1)
    assert events[1] == BuildProgress("import_deck", 1, 1)
    enrich = [e for e in events if e.stage == "enrich_kanji"]
    assert [e.current for e in enrich] == [1, 2, 3, 4]
    assert all(e.total == 4 for e in enrich)
    assert events[-2:] == [BuildProgress("write", 0, 1), BuildProgress("write", 1, 1)]


def test_failed_import_leaves_existing_database_untouched(tmp_path: Path) -> None:
    target = tmp_path / "content.db"
    _orchestrator(_FakeImporter(VOCAB)).build(tmp_path / "deck.apkg", target)
    with pytest.raises(DeckImportError):
        _orchestrator(_FailingImporter()).build(tmp_path / "deck.apkg", target)
    assert ContentRepository(target).counts().vocab == 3
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/orchestration -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

`src/bunsho/orchestration/__init__.py`:

```python
"""Workflows that coordinate several services."""
```

`src/bunsho/orchestration/content_build.py`:

```python
"""Build ``content.db`` from the vocabulary deck, kana tables and jamdict."""

from __future__ import annotations

import logging
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from bunsho.models.content import JlptLevel, Kanji, KanjiDetails, kanji_id
from bunsho.services.kanji_levels import derive_kanji_levels
from bunsho.services.protocols import ContentWriting, DeckImporter, KanaProvider, KanjiInfoSource

SCHEMA_VERSION = "1"
_NO_FREQUENCY = 10**9


class ContentBuildError(RuntimeError):
    """The content build cannot run (for example a required service is unavailable)."""


@dataclass(frozen=True, slots=True)
class BuildProgress:
    """One progress notification."""

    stage: str
    current: int
    total: int


ProgressCallback = Callable[[BuildProgress], None]


@dataclass(frozen=True, slots=True)
class BuildReport:
    """Summary of a build (or a dry run)."""

    dry_run: bool
    target: Path
    deck_sha256: str
    kana_count: int
    kanji_count: int
    vocab_count: int
    sentence_count: int
    vocab_by_level: dict[str, int]
    kanji_by_level: dict[str, int]
    kanji_without_details: int
    duration_seconds: float


def _ignore(_: BuildProgress) -> None:
    return None


def _by_level(levels: list[JlptLevel]) -> dict[str, int]:
    counts = Counter(levels)
    return {level.label: counts[level] for level in JlptLevel.study_order() if counts[level]}


class ContentBuildOrchestrator:
    """Coordinates deck import, kanji derivation, dictionary enrichment and persistence."""

    def __init__(
        self,
        importer: DeckImporter,
        kana_provider: KanaProvider,
        kanji_source: KanjiInfoSource,
        writer: ContentWriting,
        logger: logging.Logger,
    ) -> None:
        """Wire the collaborators (all behind Protocols)."""
        self._importer = importer
        self._kana = kana_provider
        self._kanji_source = kanji_source
        self._writer = writer
        self._logger = logger

    def build(
        self,
        deck_path: Path,
        target: Path,
        *,
        dry_run: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> BuildReport:
        """Run the full build.

        Args:
            deck_path: The pinned vocabulary ``.apkg``.
            target: Where ``content.db`` should be written.
            dry_run: Validate and plan only; write nothing.
            on_progress: Optional callback invoked after each step.

        Returns:
            A report of what was (or would be) written.

        Raises:
            DeckImportError: The deck is missing, altered or malformed.
            sqlite3.Error: Writing failed; any existing ``target`` is left untouched.
        """
        started = time.perf_counter()
        notify = on_progress or _ignore
        notify(BuildProgress("import_deck", 0, 1))
        deck = self._importer.import_vocab(deck_path)
        notify(BuildProgress("import_deck", 1, 1))

        kanji, without_details = self._build_kanji(derive_kanji_levels(deck.vocab), notify)
        kana = self._kana.all_kana()
        sentence_count = sum(1 for item in deck.vocab if item.sentence is not None)

        if dry_run:
            self._logger.info(
                "content_build dry_run=true target=%s kana=%d kanji=%d vocab=%d",
                target, len(kana), len(kanji), len(deck.vocab),
            )
        else:
            meta = {
                "schema_version": SCHEMA_VERSION,
                "built_at": datetime.now(UTC).isoformat(),
                "deck_sha256": deck.sha256,
                "deck_filename": deck_path.name,
                "kana": str(len(kana)),
                "kanji": str(len(kanji)),
                "vocab": str(len(deck.vocab)),
            }
            notify(BuildProgress("write", 0, 1))
            self._writer.write(target, kana=kana, kanji=kanji, vocab=deck.vocab, meta=meta)
            notify(BuildProgress("write", 1, 1))
            self._logger.info(
                "content_build dry_run=false target=%s kana=%d kanji=%d vocab=%d",
                target, len(kana), len(kanji), len(deck.vocab),
            )
        return BuildReport(
            dry_run=dry_run,
            target=target,
            deck_sha256=deck.sha256,
            kana_count=len(kana),
            kanji_count=len(kanji),
            vocab_count=len(deck.vocab),
            sentence_count=sentence_count,
            vocab_by_level=_by_level([item.level for item in deck.vocab]),
            kanji_by_level=_by_level([item.level for item in kanji]),
            kanji_without_details=without_details,
            duration_seconds=time.perf_counter() - started,
        )

    def _build_kanji(
        self, levels: dict[str, JlptLevel], notify: ProgressCallback
    ) -> tuple[list[Kanji], int]:
        ordered = sorted(levels.items(), key=lambda item: (-int(item[1]), item[0]))
        total = len(ordered)
        built: list[Kanji] = []
        without_details = 0
        for index, (char, level) in enumerate(ordered, start=1):
            details = self._kanji_source.get_kanji(char)
            if details is None:
                without_details += 1
                details = KanjiDetails()
            built.append(
                Kanji.model_validate(
                    {"id": kanji_id(char), "char": char, "level": level, **details.model_dump()}
                )
            )
            notify(BuildProgress("enrich_kanji", index, total))
        if without_details:
            self._logger.warning("kanji_without_details count=%d", without_details)
        built.sort(
            key=lambda k: (
                -int(k.level),
                k.frequency if k.frequency is not None else _NO_FREQUENCY,
                k.char,
            )
        )
        return built, without_details
```

- [ ] **Step 4: Run tests and gates**

Run: `uv run pytest tests/unit/orchestration -v && uv run ruff check . && uv run ruff format --check . && uv run mypy src/`
Expected: PASS. (Run `uv run ruff format .` first if the multi-argument log calls are reformatted.)

- [ ] **Step 5: Commit**

```bash
git add src/bunsho/orchestration tests/unit/orchestration
git commit -m "feat(orchestration): content build orchestrator with dry run and progress"
```

---

### Task 11: Logging, Context, factories, and the real-deck integration test

**Files:**
- Create: `src/bunsho/logging_setup.py`, `src/bunsho/context.py`, `src/bunsho/factories.py`
- Test: `tests/unit/test_logging_setup.py`, `tests/unit/test_factories.py`, `tests/integration/test_real_content_build.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `configure_logging(level: str = "INFO") -> None` (root handler, `key=value` format, replaces existing handlers)
  - `Context` (slots dataclass): `config: AppConfig`, `logger: logging.Logger`, `dry_run: bool = False`, `kanji_source: KanjiInfoSource | None = None`, `content_repo: ContentRepository | None = None`
  - `create_context(config: AppConfig, *, dry_run: bool = False, logger: logging.Logger | None = None) -> Context` — graceful init: a jamdict failure logs `service_init_failed service=jamdict ...` and leaves `kanji_source=None`; `content_repo` is set only if `content.db` exists.
  - `create_content_build_orchestrator(ctx: Context) -> ContentBuildOrchestrator` — raises `ContentBuildError` when `ctx.kanji_source is None`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_logging_setup.py`:

```python
import logging

from bunsho.logging_setup import configure_logging


def test_configure_logging_sets_root_level() -> None:
    root = logging.getLogger()
    previous_level, previous_handlers = root.level, list(root.handlers)
    try:
        configure_logging("DEBUG")
        assert root.level == logging.DEBUG
        configure_logging("WARNING")
        assert root.level == logging.WARNING
        assert len(root.handlers) == 1  # force=True replaced the old handler
    finally:
        root.handlers[:] = previous_handlers
        root.setLevel(previous_level)
```

`tests/unit/test_factories.py`:

```python
import dataclasses
import logging
from pathlib import Path

import pytest

from bunsho.config.settings import AppConfig
from bunsho.factories import create_content_build_orchestrator, create_context
from bunsho.orchestration.content_build import ContentBuildError, ContentBuildOrchestrator
from bunsho.services.content_repository import ContentWriter
from tests.base import FakeKanjiSource, make_vocab

LOGGER_NAME = "bunsho.test_factories"


def test_missing_jamdict_degrades_gracefully(
    app_config: AppConfig, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config = dataclasses.replace(app_config, jamdict_db=tmp_path / "missing.db")
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        ctx = create_context(config, logger=logging.getLogger(LOGGER_NAME))
    assert ctx.kanji_source is None
    assert "service_init_failed service=jamdict" in caplog.text
    with pytest.raises(ContentBuildError, match="jamdict"):
        create_content_build_orchestrator(ctx)


def test_content_repo_only_when_database_exists(app_config: AppConfig, quiet_logger: logging.Logger) -> None:
    assert create_context(app_config, logger=quiet_logger).content_repo is None
    ContentWriter().write(
        app_config.content_db_path, kana=[], kanji=[], vocab=[make_vocab()], meta={}
    )
    ctx = create_context(app_config, dry_run=True, logger=quiet_logger)
    assert ctx.content_repo is not None
    assert ctx.content_repo.counts().vocab == 1
    assert ctx.dry_run is True


def test_orchestrator_is_built_from_context(app_config: AppConfig, quiet_logger: logging.Logger) -> None:
    ctx = create_context(app_config, logger=quiet_logger)
    ctx.kanji_source = FakeKanjiSource()
    assert isinstance(create_content_build_orchestrator(ctx), ContentBuildOrchestrator)
```

`tests/integration/test_real_content_build.py`:

```python
from pathlib import Path

import pytest

from bunsho.config.settings import DEFAULT_DECK_FILENAME, DEFAULT_DECK_SHA256, AppConfig
from bunsho.factories import create_content_build_orchestrator, create_context
from bunsho.models.content import JlptLevel, kanji_id
from bunsho.orchestration.content_build import BuildReport
from bunsho.services.content_repository import ContentRepository

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[BuildReport, ContentRepository]:
    config = AppConfig(
        data_dir=tmp_path_factory.mktemp("data"),
        resources_dir=REPO_ROOT / "resources",
        deck_filename=DEFAULT_DECK_FILENAME,
        deck_sha256=DEFAULT_DECK_SHA256,
        jamdict_db=None,
        log_level="INFO",
    )
    if not config.deck_path.is_file():
        pytest.skip(f"deck not present: {config.deck_path}")
    ctx = create_context(config)
    if ctx.kanji_source is None:
        pytest.skip("jamdict-data-fix database unavailable")
    report = create_content_build_orchestrator(ctx).build(config.deck_path, config.content_db_path)
    return report, ContentRepository(config.content_db_path)


@pytest.mark.integration
def test_counts_match_the_pinned_deck(built: tuple[BuildReport, ContentRepository]) -> None:
    report, repo = built
    assert report.vocab_count == 7734
    assert report.vocab_by_level == {"N5": 667, "N4": 630, "N3": 1647, "N2": 1737, "N1": 3053}
    assert report.kanji_count == 2109
    assert report.kanji_by_level == {"N5": 480, "N4": 352, "N3": 544, "N2": 357, "N1": 376}
    assert report.kana_count == 208
    assert report.sentence_count == 6775
    counts = repo.counts()
    assert (counts.kana, counts.kanji, counts.vocab) == (208, 2109, 7734)
    assert repo.meta()["deck_sha256"] == DEFAULT_DECK_SHA256


@pytest.mark.integration
def test_well_known_kanji_are_n5_with_dictionary_details(
    built: tuple[BuildReport, ContentRepository],
) -> None:
    _, repo = built
    for char in "日本人大学水食":
        kanji = repo.get_kanji(kanji_id(char))
        assert kanji is not None
        assert kanji.level is JlptLevel.N5
        assert kanji.meanings and kanji.on_readings + kanji.kun_readings
    nichi = repo.get_kanji(kanji_id("日"))
    assert nichi is not None and nichi.stroke_count == 4


@pytest.mark.integration
def test_few_kanji_lack_dictionary_details(built: tuple[BuildReport, ContentRepository]) -> None:
    report, _ = built
    # If this fails, read the kanji_without_details warning before loosening the bound.
    assert report.kanji_without_details <= report.kanji_count * 0.02
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_logging_setup.py tests/unit/test_factories.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

`src/bunsho/logging_setup.py`:

```python
"""Logging configuration."""

from __future__ import annotations

import logging

LOG_FORMAT = "%(asctime)s level=%(levelname)s logger=%(name)s %(message)s"


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger with a logfmt-style line format.

    Args:
        level: A standard level name such as ``INFO`` or ``DEBUG``.
    """
    logging.basicConfig(level=level.upper(), format=LOG_FORMAT, force=True)
```

`src/bunsho/context.py`:

```python
"""Shared application context passed explicitly instead of using globals."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from bunsho.config.settings import AppConfig
from bunsho.services.content_repository import ContentRepository
from bunsho.services.protocols import KanjiInfoSource


@dataclass(slots=True)
class Context:
    """Configuration, logger, operational flags and shared services.

    Services that failed to initialize are ``None``; callers must check before use.
    """

    config: AppConfig
    logger: logging.Logger
    dry_run: bool = False
    kanji_source: KanjiInfoSource | None = None
    content_repo: ContentRepository | None = None
```

`src/bunsho/factories.py`:

```python
"""Factory functions that build concrete services from configuration."""

from __future__ import annotations

import logging

from bunsho.config.settings import AppConfig
from bunsho.context import Context
from bunsho.orchestration.content_build import ContentBuildError, ContentBuildOrchestrator
from bunsho.services.anki_importer import AnkiDeckImporter
from bunsho.services.content_repository import ContentRepository, ContentWriter
from bunsho.services.jamdict_service import JamdictService, JamdictUnavailableError
from bunsho.services.kana_source import KanaSource
from bunsho.services.protocols import KanjiInfoSource


def create_context(
    config: AppConfig, *, dry_run: bool = False, logger: logging.Logger | None = None
) -> Context:
    """Build a ``Context``, tolerating optional services that fail to start.

    A jamdict failure is logged as a warning and leaves ``kanji_source`` as ``None``;
    ``content_repo`` is set only when ``content.db`` already exists.

    Args:
        config: Validated configuration.
        dry_run: Operational flag carried on the context.
        logger: Logger to use (defaults to ``bunsho``).

    Returns:
        The initialized context.
    """
    log = logger or logging.getLogger("bunsho")
    kanji_source: KanjiInfoSource | None = None
    try:
        kanji_source = JamdictService(config.jamdict_db)
    except JamdictUnavailableError as exc:
        log.warning("service_init_failed service=jamdict error=%s", exc)
    content_repo = (
        ContentRepository(config.content_db_path) if config.content_db_path.is_file() else None
    )
    return Context(
        config=config,
        logger=log,
        dry_run=dry_run,
        kanji_source=kanji_source,
        content_repo=content_repo,
    )


def create_content_build_orchestrator(ctx: Context) -> ContentBuildOrchestrator:
    """Assemble the content build orchestrator.

    Raises:
        ContentBuildError: If the jamdict service is unavailable.
    """
    if ctx.kanji_source is None:
        raise ContentBuildError(
            "cannot build content: the jamdict database is unavailable "
            "(install jamdict-data-fix or set paths.jamdict_db)"
        )
    return ContentBuildOrchestrator(
        importer=AnkiDeckImporter(ctx.config.deck_sha256, ctx.logger),
        kana_provider=KanaSource(),
        kanji_source=ctx.kanji_source,
        writer=ContentWriter(),
        logger=ctx.logger,
    )
```

- [ ] **Step 4: Run the whole suite and every gate**

Run:
```bash
uv run pytest --cov=src --cov-report=term-missing -v
uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run bandit -r src/ -l
```
Expected: all tests PASS, including the three integration tests against the real deck and the real jamdict database (the build takes roughly 30 to 60 seconds because each of the 2,109 kanji costs about 10 ms). Coverage is `>= 90%`; bandit reports no issues. If `test_counts_match_the_pinned_deck` fails on kanji counts, print `report` and compare with the deck facts in Global Constraints before changing any expected number.

- [ ] **Step 5: Commit**

```bash
git add src/bunsho/logging_setup.py src/bunsho/context.py src/bunsho/factories.py tests
git commit -m "feat: context, factories and real-deck content build integration test"
```

---

## Self-review against the spec

- **Content model** (kana, derived-level kanji, vocab, sentences, furigana, stable IDs): Tasks 3-5, 6, 7, 8.
- **`content.db` rebuildable, atomic, separate from progress**: Tasks 9-10 (`progress.db` itself is Plan 1B).
- **Deck pinned by sha256, GPL-3.0 provenance in repo**: Tasks 1 and 6.
- **`dry_run` and progress reporting for the build**: Task 10 (exposed over HTTP/WebSocket in Plan 1B).
- **Config layering, case-insensitive keys, validation reporting all failures**: Task 2.
- **Context object, factories, graceful service init**: Task 11.
- **Rename to `bunsho`, hatchling, Python 3.13, `dev` extra, tooling**: Task 1.
- **Shared test base, 90% coverage, integration marker**: Tasks 1, 3, 11.
- **Deviation from the spec, noted in "Scope note":** kanji outside the deck are not stored.

Deferred to Plan 1B: `progress.db` schema, Alembic, startup backup; JWT auth (moved ahead of the admin routes so none are unauthenticated); FastAPI app, `/health`, `/admin/config-check`, `/admin/content/build`, WebSocket progress; `bunsho` launcher entry point; Dockerfile and compose; CI rewrite and `release.yml` review; cleanup of the Jidou-specific skills and `settings.local.json`.

Type consistency check: `KanjiInfoSource.get_kanji`, `DeckImporter.import_vocab`, `KanaProvider.all_kana` and `ContentWriting.write` signatures in Task 7 match their implementations in Tasks 6, 5, 8 and 9. `Kanji` is built the same way in Tasks 9 (tests) and 10 (`{"id", "char", "level", **details.model_dump()}`). `BuildReport` field names used in Task 11's integration test match Task 10.
