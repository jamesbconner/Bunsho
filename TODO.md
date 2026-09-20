# Bunshō TODO

Status: Plans 1A, 1B and 1C are merged. Plan 2A (review engine backend) is implemented on
`feat/plan-2a-review-engine`; Plan 2B (frontend and delivery) is next. Design: the specs in
`docs/superpowers/specs/`. Plans: `docs/superpowers/plans/`.

## Now

- [x] **Unleveled kanji rows** — done (commits `3509d04`, `bbdc2f7`). Kanji with a KANJIDIC2 grade of 1–10
      (jōyō + jinmeiyō) that are not in the deck are stored with `level = None`: +979 rows, 3,088 kanji in
      total, schema v2. Compatibility code points (e.g. U+FA19) are excluded. The real build now takes ~31 s.
- [ ] Follow-ups from that review (minor):
  - [x] Plan 2: `list_kanji()` / `counts().kanji` now include unleveled rows and `Kanji.level` may be `None`;
        lessons filter them via `ContentRepository.catalog` (Plan 2A)
  - [ ] Add a unit test that guards the percent-encoded read-only URI for paths like `Bunshō dir #1 100%x`
  - [ ] `test_few_kanji_lack_dictionary_details`: bound on leveled kanji (`sum(kanji_by_level.values())`), not all 3,088
  - [ ] Note in the integration tests that the hard-coded 2,941 / 979 / grade histogram depend on the locked
        `jamdict-data-fix` version (1.5.1a2)
  - [ ] `build()` docstring `Raises:` should list `JamdictUnavailableError` (from `graded_kanji()`); test a catalog that raises
  - [ ] Log the literals of skipped unleveled candidates at DEBUG; put `Context.kanji_catalog` after `content_repo`

## Plan 1B — service shell (merged) and Plan 1C — delivery

Baseline from the spec:
- [x] `progress.db` schema (SQLAlchemy 2.0 async + aiosqlite) + Alembic migrations, timestamped backup at startup
- [x] JWT auth, single local user (all REST and WebSocket routes protected)
- [x] FastAPI app factory, `/api/v1`: `health`, `admin/config-check`, `admin/content/build` (`dry_run`, background task), WebSocket progress
- [x] `bunsho` launcher entry point (uvicorn, no click/rich)
- [x] Plan 1C: Dockerfile (multi-stage, non-root), `compose.yaml` (port 8192, named data volume, read-only root filesystem),
      `.dockerignore`, `.gitattributes`
- [x] CI rewrite (drop postgres/redis/jidou-api), plus a container smoke-test job (Plan 1C)
- [x] Jidou content stripped from `.claude/skills/{db-migration,release-notes,check-pr}` and `.claude/settings.local.json`
      (no Jidou/TMDB text left there); the committed `.gitignore` (commit `ff3621b`) ignores `.claude/` and `.agents/`

Carry-forward from Plan 1A's final review:
- [x] Rebuild endpoint: `_replace_with_retry` retries `PermissionError` (`services/content_repository.py`); a second
      build is refused with `BuildAlreadyRunningError` -> HTTP 409 (`orchestration/build_tasks.py`, `api/routers/admin.py`)
- [x] `on_progress` callback cannot raise into the build (`build_tasks.py`, `_make_callback`); `content_build_failed`
      is logged when `writer.write` raises (`orchestration/content_build.py`)
- [x] Dry run is a background task with progress (`BuildTaskManager.start(dry_run=...)`), never a synchronous request
- [x] `create_context` catches `JamdictUnavailableError`/`OSError`/`sqlite3.Error` from the jamdict service (`factories.py`);
      `ContentRepository(...)` opens no connection and is only built when `content.db` exists; `/health` exists
- [x] Config loader wraps `FileNotFoundError`/`TOMLDecodeError` in `ConfigError` (`config/loader.py`); `data_dir` is
      validated (`config/settings.py`); the image sets absolute `/data` and `/app/resources` (`Dockerfile`)
- [x] Integration fixtures fail, not skip, when `CI` is set (Plan 1C); `bandit -c pyproject.toml` runs in CI
- [x] `src/bunsho/py.typed` and `.pre-commit-config.yaml` (Plan 1C; pre-commit is optional per clone)
- [x] Call `ContentRepository.verify_schema()` at startup and in Plan 2 before reading (today only `/health` calls it) (Plan 2A)

Delivered by Plan 1C (see `CHANGELOG.md` and the README's "Running with Docker"):
- [x] Migration lock file, actionable startup errors (database path, backups folder, ownership hint), sweep of stale
      `content.db.<hex>.tmp` files
- [x] Proxy story: `server.trusted_proxies`, strict validation, documented nginx `X-Forwarded-For` requirement
- [x] Bounded graceful shutdown (`stop_grace_period: 60s`), 64 KiB WebSocket frame limit
- [x] Container smoke test (`scripts/smoke_test.py`) and CI job; CI skip policy; CHANGELOG

## Deferred from Plan 1C (open)

API and app:
- [x] OpenAPI quality, needed before generating TypeScript types: explicit operation ids, documented 401/404/409/429/503
      responses, WebSocket message schemas in `components` (Plan 2A)
- [ ] CORS: methods beyond GET/POST are done for `PUT` (Plan 2A); the Vite dev origin is an opt-in setting (documented,
      `BUNSHO_SERVER__CORS_ORIGINS`); open it in development only once the frontend exists (Plan 2B)
- [x] Typed `unleveled_kanji` in the content summary (today it is only in `meta` as a string) (Plan 2A)
- [ ] Logout / revocation for the stateless refresh tokens
- [ ] Cap on unauthenticated WebSocket connections
- [ ] Health-check access-log noise: the Docker healthcheck adds ~2,900 uvicorn access-log lines a day

Data:
- [x] WAL journal mode and `PRAGMA foreign_keys=ON` for `progress.db` (Plan 2A)
- [ ] Test for the migration `downgrade()` path
- [ ] Backup retention: backups in `data_dir/backups/` are never pruned
- [ ] `sqlite3.Error` from a full backups volume is not wrapped in the actionable startup error

Image and platform:
- [ ] Pin the base image by digest and add OCI labels
- [ ] Image trim candidates: `pip` in the base image, `watchfiles`, the venv `activate` scripts
- [ ] Windows: a CTRL_BREAK shutdown exits with code 3 (uvicorn re-raises the signal)
- [ ] Local (git-ignored) `.claude/` guideline documents (`CLAUDE.md`, `llm-patterns.md`, `react.md`) still carry
      Jidou/TMDB rules

## Plan 2 — review engine and first UI

- [x] `Scheduler` interface + `FSRSScheduler` (fsrs), card generation, `ReviewSessionOrchestrator` (Plan 2A)
- [ ] Review/stats/settings endpoints (Plan 2A); React 18 + Vite + TS frontend (Plan 2B) (login, first-run build, dashboard, flip + grade review, stats)
- [x] Document that content ids are opaque (`vocab:度:ど#2` exists); add an unfiltered `list_vocab()` consumer test (Plan 2A)
- [x] Instance lock for the data folder: one instance per volume (today two instances on one volume both start and
      the startup temp-file sweep can break the other's running build); pair it with WAL and `PRAGMA foreign_keys=ON`
      once every card grade writes to `progress.db` (Plan 2A)
- [ ] Image: a Node stage (`FROM node AS frontend`), an explicit `COPY --from=frontend` of the built assets, a
      `StaticFiles` mount in the app, and the read-only root filesystem implications
- [ ] CI: a `frontend` job (`tsc -b`, eslint, vitest); decide whether `smoke` needs the built frontend
- [ ] Dependabot: add the `npm` entry for `/frontend` (stubbed in the `.github/dependabot.yml` header comment)
- [ ] Extend the smoke test: `index.html` is served, a review round-trip; revisit `EXPECTED_COUNTS` if the content
      schema changes
- [ ] Re-derive `WS_MAX_MESSAGE_BYTES` if review batches use the WebSocket
- [ ] Single source of truth for the uv pin (0.12.17 is in `ci.yml`, `release.yml` and the `Dockerfile`), for example
      an `ARG UV_VERSION` shared through a build-arg
- [ ] Use a separate image tag for the smoke project (`bunsho:smoke`) so it never retags a developer's `bunsho:local`
- [ ] First real run of `release.yml` (it has never run), and check that Dependabot's docker ecosystem can bump the
      two Dockerfile image references
- [ ] A corrupt `progress.db` makes the container restart loop print a full traceback on every attempt; log only the
      `StartupError` message
- [ ] Orphaned due cards (item removed from content) inflate `counts.due` and, if 50 or more sort first, hide valid due
      cards (`_ORPHAN_SCAN` in `orchestration/review_session.py`): filter in SQL or page past them
- [ ] `ReviewSessionOrchestrator._plan` recomputes on every `next` and `answer` (25k-row `card_states` read, three
      catalogue queries, sorting on the event loop): measure on the real deck and cache if it shows
- [ ] Tests for a non-UTC study-day timezone through the orchestrator and stats service (only `study_day` itself is
      DST-tested; every orchestrator and stats test uses UTC)
- [ ] Type `LevelProgress.level` and the `*_by_level` keys with `LevelLabel` so the generated TypeScript gets a union
- [ ] Put an upper bound on the `fsrs` dependency (for example `<7`) and decouple tests from FSRS default learning steps
- [ ] Sibling burying (hold a new item's other directions until a later day)
- [ ] `review_log` retention/export before the file grows unwieldy
- [ ] A Prometheus-style or structured metric for review latency (only if the box gets monitoring)
- [ ] Coverage gaps below 90 % per file: `db/migrations/env.py` and the `login_throttle` prune branch (the `0001`
      `downgrade()` test is listed under Data)

## Later sub-projects

- [ ] 3. Typed-answer (romaji -> kana; ぢ/じ and づ/ず share romaji, accept both) and multiple-choice modes
- [ ] 4. Stroke order / handwriting (needs a stroke-data source, probably KanjiVG; jamdict has none)
- [ ] 5. Anki `.apkg` export
- [ ] 6. Sentence practice and grammar (grammar source still open)

## Decisions still open

- [x] Bunshō's own license: **MIT** (decided 2026-09-19; `LICENSE`, `pyproject.toml`, README license section).
      The deck in `resources/` stays GPL-3.0 with its own LICENSE; a built `content.db` is a derived work.
- [ ] Verify the JMdict/KANJIDIC2 (EDRDG licence) and, later, KanjiVG attribution wording before distributing a built
      `content.db` or a Docker image that contains it
- [x] Plan 1A merged to `main` (PR #1, 2026-09-19). Working method going forward: branch -> push -> PR; James merges.
- [ ] Optional history cleanup: four haiku-authored commits carry a "Claude Haiku 4.5" trailer (two on the subject line)
- [x] The `.gitignore` decision: committed in `ff3621b`; `.claude/` and `.agents/` stay ignored (local agent config)

## Deferred minor findings (low priority)

- [ ] furigana parser: untested edge cases (multiple/leading spaces, bare `[reading]`, unclosed `<mark>`); `(?<=])` vs `(?<=\])` spelling
- [ ] importer: empty `Expression`/`Reading` accepted silently; encrypted-zip `RuntimeError`/`OSError` not wrapped
- [ ] `is_kanji` misses CJK Extension B+ and compatibility ideographs
- [ ] `logging_setup`: `force=True` is still the default (a `force=False` option exists; the launcher configures logging
      before uvicorn starts, so nothing is wiped today); the line format is only half logfmt (free-text message)
- [ ] `.gitattributes` now covers the Dockerfile, `.dockerignore`, YAML and shell files only; add `* text=auto eol=lf`
      and `*.apkg binary` to stop the remaining CRLF warnings (for example on Markdown)
- [ ] Test thinness: kana romaji spot-checks (~6 of 208), repeated-kanji case, `Kanji` frozen inheritance, Protocol conformance assertions
