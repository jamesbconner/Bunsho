# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

## [1.3.0] - 2026-09-24

### Added

- Settings: **Discard changes** puts every field on every tab back to what was last saved.

### Changed

- Settings: the Learning path, Pace and Reviewing tabs are now titled cards, like the System tab.
  The type and Kana first switches are rows with the label and its explanation on the left and
  the toggle on the right.
- Settings, Reviewing: each card type's review mode is a segmented control (Flip, Typed, Multiple
  choice) with a line explaining the selected mode, instead of a drop-down.
- Settings: Save, Discard and Reset stay in view at the bottom of the window, and the bar says
  whether there are unsaved changes.
- Settings: the form cannot be edited while a save is in progress, so the saved values can no
  longer overwrite an edit made in that moment. The field you were in keeps its focus afterwards.

## [1.2.1] - 2026-09-24

### Fixed

- Study screen: the button text was too small to read comfortably. The grade buttons, the
  multiple-choice options, Show answer, Submit, Continue and Home's "Study now" are larger, and so
  are the number-key hints on them. Multiple-choice options whose answer is Japanese (a kana, a
  kanji or a reading) are set at a much larger size so the glyphs are easy to tell apart, and the
  option buttons grow to fit them.

## [1.2.0] - 2026-09-23

### Added

- Settings, System tab: the service version and the health of each component (`GET /health`), and
  whether the study content is built with its kana, kanji and vocabulary counts.

### Changed

- The Settings page is now four tabs instead of one long form: **Learning path** (new-card policy,
  levels, the type switches and Kana first), **Pace** (daily limits, when the study day starts,
  target retention), **Reviewing** (review modes) and **System**. There is still one form and one
  Save for the first three; a tab that holds a problem is marked, and Save opens the first one. The
  selected tab is in the address (`/settings?tab=pace`).
- "Build content" moved from its own page into Settings, System. `/build` redirects there, and the
  "Build your content" buttons on Home, Statistics and the finished-review screen open it directly.
- "Reset to recommended values" is now "Reset all tabs to recommended values".
- A greyed-out daily limit now says it is switched off in Learning path, and a server error on a
  review-mode field is shown on that field.

## [1.1.2] - 2026-09-23

### Fixed

- Tests: `test_missing_settings_report_every_problem` no longer picks up a developer's own `./.env`
  (which supplied the required login settings and made the test fail on any machine with one). No
  change to the service itself.

## [1.1.1] - 2026-09-23

### Fixed

- Multiple-choice review: the wrong options are now picked at random instead of always being the
  first items in study order (every kana card used to offer "a, i, u"). They still prefer the card's
  own JLPT level, then the other active levels, then everything else. Kana options also stay in the
  card's own script, so hiragana cards no longer offer katakana and the reverse. (#24)

## [1.1.0] - 2026-09-23

### Added

- Study plan control (Settings): each of kana, kanji and vocabulary can be switched off for new cards
  (cards already introduced stay due, so nothing is lost; all three off gives a reviews-only
  session), and kanji and vocabulary can each be made to wait until a chosen share (default 80%) of
  all kana cards, both directions, hiragana and katakana together, is in the FSRS Review state. The
  gate works with every new-card policy and is checked on every plan, so if the kana share later
  falls below the threshold, new kanji and vocabulary pause until it recovers; scheduled reviews are
  never held back. The settings document gains `type_enabled` and `kana_gate`; defaults keep the
  previous behaviour and saved settings from 1.0.0 load unchanged. (#20)

## [1.0.0] - 2026-09-23

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
- Review engine: FSRS scheduling (`fsrs`) with a configurable target retention, cards created
  on first grade, `GET /reviews/next`, `POST /reviews/answer` (stale answers get 409),
  `GET /stats/summary` and `GET`/`PUT /settings`. New cards follow one of three user-selectable
  policies (strict N5-to-N1 order, mastery unlock, pinned levels) within per-type daily limits and
  a study-day rollover hour. New runtime dependencies: `fsrs` (scheduling) and `tzdata` (makes the
  study-day timezone work on Windows and in slim images).
- `GET /content/summary` reports unleveled kanji (`unleveled_kanji`) and per-level counts for
  kanji and vocabulary.
- Unhandled errors return `{"detail": "internal error"}` (status 500) and are logged; the exception
  text is never sent to the client.
- OpenAPI: explicit operation ids, documented 401/404/409/429/503 responses, and the WebSocket
  message schemas in `components`, so a typed client can be generated.
- Web UI (`frontend/`, React with Mantine): log in (the refresh token is remembered in the browser,
  the access token only in memory), an app shell with a light, dark or system theme, a Home page
  showing what has been built, and a Build screen that runs a content build or dry run with live
  progress over the WebSocket (with reconnect and a polling fallback). Log out only clears this
  browser; the server does not revoke tokens yet. The Docker image builds the UI in a Node stage and
  the service serves it (`paths.frontend_dir`), with cache and security headers and a fallback to
  `index.html` for client-side routes.
- Study screens in the web UI: a dashboard on the Home page (what is due and what is new, per type,
  and a *Study now* button) and a flip-and-grade review with keyboard shortcuts (Space or Enter to
  flip, 1 to 4 to grade), the projected interval on every grade button, furigana on the answer side
  (and on the front with a switch), and a finished state with the next due time. The pages are
  loaded on demand, so the first screen no longer carries the study and build code.
- Statistics and settings screens in the web UI. Statistics: today's reviews and new cards, 30-day
  retention, a 30-day chart (Mantine Charts, with the same numbers in an accessible table), cards by
  state and progress by JLPT level. Settings: one form for the new-card policy, daily limits, levels,
  mastery threshold, target retention and the study-day hour, with validation in the browser, the
  server's messages placed on the matching fields, and the new limits applied from the next card. The
  review screen's "done for now" state links to Settings. Adds the `@mantine/charts` and `recharts`
  dependencies (loaded only on the statistics page).
- The API's OpenAPI document is committed as `frontend/openapi.json`; a unit test fails when it is
  stale, and the frontend's TypeScript types are generated from it.
- CI: a `frontend` job (Prettier, ESLint, type-check and build, vitest with coverage, and a check
  that the generated API types are current); Dependabot updates the npm dependencies; the
  container smoke test checks that the UI is served.
- Typed-answer and multiple-choice review modes, alongside the existing flip-and-grade mode,
  chosen per item type on the Settings page.

### Changed

- `progress.db` runs in WAL mode with foreign keys enforced, and the service takes an exclusive
  lock on the data folder: a second instance on the same folder refuses to start.
- CORS allows `PUT` in addition to `GET` and `POST` (still off unless origins are configured).
- Startup checks the `content.db` schema version and logs an error when a rebuild is needed.
