# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Content pipeline: imports the JLPT N5-N1 vocabulary Anki deck (checksum-verified), and builds a
  `content.db` of vocabulary, kanji (leveled from the deck, plus unleveled jōyō and jinmeiyō kanji
  from KANJIDIC2), kana and example sentences with furigana segments, using the `jamdict-data-fix`
  dictionary for kanji details. The build reports counts per JLPT level and supports a dry run.
- Authenticated REST and WebSocket API under `/api/v1`, for a single local user: login with a
  refresh token, throttled failed logins, `GET /health` (component status only), `GET
  /admin/config-check`, background `POST /admin/content/build` with polling, `GET
  /content/summary`, and a WebSocket stream (`/ws/tasks`) of content build progress. Interactive
  docs are served at `/docs`. The `bunsho` command starts the service (single worker, default port
  8192).
- Layered settings (environment variables over `.env` over an optional TOML file) with all
  configuration problems reported together at startup.
- Progress database (`progress.db`, SQLite with Alembic migrations): a timestamped backup is written
  before any schema migration, migrations are serialised by a lock file so concurrent starts cannot
  collide, and startup fails with an actionable message when the database is unreadable or its
  folder is not writable. Stale temporary files from an interrupted content build are removed at
  startup.
- Trusted proxy setting (`server.trusted_proxies`): proxy headers such as `X-Forwarded-For` are
  ignored unless they come from a listed address or network, so the login throttle cannot be
  bypassed; wildcard and host-bit entries are rejected.
- Bounded graceful shutdown and a tighter WebSocket frame limit.
- Docker image (multi-stage, Python only, non-root user, health check on `/api/v1/health`) and a
  compose file that runs one service on port 8192 with a persistent data volume and the resources
  folder mounted read-only.
- CI container smoke test (`scripts/smoke_test.py`): builds the image, logs in, builds content from
  the real deck, and restarts the container to check that data and tokens survive.
- Pre-commit configuration (YAML and TOML checks, ruff lint and format, mypy, bandit); installing
  the hooks is optional and per clone.
- CI policy: integration tests that skip because the real deck or dictionary database is missing
  fail instead when the `CI` environment variable is set; bandit now reads its configuration from
  `pyproject.toml`. A `py.typed` marker ships with the package.
