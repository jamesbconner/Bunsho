# Bunshō TODO

Status: Plan 1A (content pipeline library) and Plan 1B (authenticated API service) are merged to `main`.
Plan 1C (delivery: Docker, compose, smoke test, tooling, docs) is implemented on branch
`feat/plan-1c-delivery`. Design: `docs/superpowers/specs/2026-09-19-bunsho-foundation-and-review-engine-design.md`.
Plans: `docs/superpowers/plans/` (`1a`, `1b`, `1c`).

## Now

- [x] **Unleveled kanji rows** — done (commits `3509d04`, `bbdc2f7`). Kanji with a KANJIDIC2 grade of 1–10
      (jōyō + jinmeiyō) that are not in the deck are stored with `level = None`: +979 rows, 3,088 kanji in
      total, schema v2. Compatibility code points (e.g. U+FA19) are excluded. The real build now takes ~31 s.
- [ ] Follow-ups from that review (minor):
  - [ ] Plan 2: `list_kanji()` / `counts().kanji` now include unleveled rows and `Kanji.level` may be `None`;
        lessons must filter them. Consider a `leveled_only` convenience on `ContentRepository`
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
- [ ] Strip Jidou content from `.claude/skills/{db-migration,release-notes,check-pr}` and `.claude/settings.local.json`
      — first confirm with the user: the working-tree `.gitignore` now ignores `.claude/` and `.agents/`

Carry-forward from Plan 1A's final review:
- [ ] Rebuild endpoint: Windows `os.replace` over an open reader raises `PermissionError` -> retry/handle; serialize builds
- [ ] Guard the WebSocket `on_progress` callback (an exception aborts the build); log/report `content_build_failed` when `writer.write` raises
- [ ] Dry run costs ~2,109 x ~10 ms jamdict lookups (~20 s): background task with progress, never a synchronous request
- [ ] `create_context`: also handle `OSError`/`sqlite3.Error` from the `Jamdict()` constructor and from `ContentRepository(...)`; add `/health`
- [ ] Config loader: wrap `FileNotFoundError`/`TOMLDecodeError` in `ConfigError` for `config-check`; validate `data_dir`/`resources_dir`, absolute defaults for Docker
- [x] Integration fixtures must fail, not skip, when `CI` is set (Plan 1C); `bandit -c pyproject.toml` runs in CI
- [x] `src/bunsho/py.typed` and `.pre-commit-config.yaml` (Plan 1C; pre-commit is optional per clone)
- [ ] Call `ContentRepository.verify_schema()` at startup (and in Plan 2 before reading)

Delivered by Plan 1C (see `CHANGELOG.md` and the README's "Running with Docker"):
- [x] Migration lock file, actionable startup errors (database path, backups folder, ownership hint), sweep of stale
      `content.db.<hex>.tmp` files
- [x] Proxy story: `server.trusted_proxies`, strict validation, documented nginx `X-Forwarded-For` requirement
- [x] Bounded graceful shutdown (`stop_grace_period: 60s`), 64 KiB WebSocket frame limit
- [x] Container smoke test (`scripts/smoke_test.py`) and CI job; CI skip policy; CHANGELOG

## Deferred from Plan 1C (open)

API and app:
- [ ] OpenAPI quality, needed before generating TypeScript types: explicit operation ids, documented 401/404/409/429/503
      responses, WebSocket message schemas in `components`
- [ ] CORS: allow methods beyond GET/POST when the frontend needs them
- [ ] Typed `unleveled_kanji` in the content summary (today it is only in `meta` as a string)
- [ ] Logout / revocation for the stateless refresh tokens
- [ ] Cap on unauthenticated WebSocket connections
- [ ] Health-check access-log noise: the Docker healthcheck adds ~2,900 uvicorn access-log lines a day

Data:
- [ ] WAL journal mode and `PRAGMA foreign_keys=ON` for `progress.db`
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

- [ ] `Scheduler` interface + `FSRSScheduler` (py-fsrs), card generation, `ReviewSessionOrchestrator`
- [ ] Review/stats endpoints; React 18 + Vite + TS frontend (login, first-run build, dashboard, flip + grade review, stats)
- [ ] Document that content ids are opaque (`vocab:度:ど#2` exists); add an unfiltered `list_vocab()` consumer test

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
- [ ] The uncommitted working-tree `.gitignore` (ignores `.claude/`, `.agents/`, `data/`, ...) needs a decision before the
      Plan 1B skills cleanup: commit it, or stop ignoring `.claude/`

## Deferred minor findings (low priority)

- [ ] furigana parser: untested edge cases (multiple/leading spaces, bare `[reading]`, unclosed `<mark>`); `(?<=])` vs `(?<=\])` spelling
- [ ] importer: empty `Expression`/`Reading` accepted silently; encrypted-zip `RuntimeError`/`OSError` not wrapped
- [ ] `is_kanji` misses CJK Extension B+ and compatibility ideographs
- [ ] `logging_setup`: `force=True` would wipe uvicorn handlers if called after startup; format only half logfmt
- [ ] `.gitattributes` now covers the Dockerfile, `.dockerignore`, YAML and shell files only; add `* text=auto eol=lf`
      and `*.apkg binary` to stop the remaining CRLF warnings (for example on Markdown)
- [ ] Test thinness: kana romaji spot-checks (~6 of 208), repeated-kanji case, `Kanji` frozen inheritance, Protocol conformance assertions
