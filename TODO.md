# Bunshō TODO

Status: Plans 1A, 1B, 1C, 2A, 2B-1, 2B-2, 2B-3, and the typed-answer/multiple-choice review modes
plan are all merged into `main`. The first version of the UI — login, first-run build, dashboard,
three review modes (flip, typed, multiple-choice), statistics, and settings — is complete. Design:
the specs in `docs/superpowers/specs/`. Plans: `docs/superpowers/plans/`.

Open items are grouped by category below, most important first within each category. Completed
items are kept at the bottom of the file, grouped by the plan that delivered them, for history.

## Open Items

### Security & Auth

- [ ] Content-Security-Policy header for the served UI (Mantine injects inline styles: needs nonces or hashes)
- [ ] Security headers (nosniff, Referrer-Policy, X-Frame-Options) are set on static responses only;
      extend to API/docs responses together with the CSP work
- [ ] The JSON 500 from unhandled errors is produced outside CORS middleware (only matters for
      cross-origin setups)
- [ ] Login: map 422 field errors onto the form inputs; tighten `returnPath` (reject backslash) and
      carry search/hash through RequireAuth

### Reliability & Data Integrity

- [ ] Orphaned due cards (item removed from content) inflate `counts.due` and, if 50 or more sort first,
      hide valid due cards (`_ORPHAN_SCAN` in `orchestration/review_session.py`): filter in SQL or page
      past them
- [ ] A corrupt `progress.db` makes the container restart loop print a full traceback on every attempt;
      log only the `StartupError` message
- [ ] Backup retention: backups in `data_dir/backups/` are never pruned
- [ ] `sqlite3.Error` from a full backups volume is not wrapped in the actionable startup error
- [ ] Test for the migration `downgrade()` path
- [ ] Two keydowns landing before the re-render after the first grade both call `mutate` (the server
      rejects the second with a 409, shown as a spurious "changed elsewhere" notice): add a synchronous
      in-flight guard
- [ ] A held Enter that flips the next card through native button repeat (preventDefault repeated
      Space/Enter inside the review controls)
- [ ] An unmatched WebSocket path under the `/` static mount reaches StaticFiles'
      `assert scope["type"] == "http"` (AssertionError instead of a clean rejection): guard it
- [ ] Wrong-method requests to real API routes behave differently when the UI is served: the catch-all
      `/` mount wins the full match over the router's partial (method) match, so POST to a GET-only
      route gives 405 without an `Allow` header, GET on a POST-only route gives 404 instead of 405, and
      `HEAD /api/...` gives 404
- [ ] After a second close-1008 the stream stays offline until a reload: retry on `online`/`visibilitychange`
- [ ] Windows: a CTRL_BREAK shutdown exits with code 3 (uvicorn re-raises the signal)

### API Gaps

- [ ] `GET /reviews/next` cannot say why no card is offered (daily limit used up vs everything
      introduced): add a reason field and use it in the finished state (the new `type_availability` service already returns a per-type block reason, so a blocked type could be reported here)
- [ ] Undo of a grade and study-ahead need API support (the review log is append-only, `next` has no look-ahead)
- [ ] Expose the review-setting defaults through the API so the form does not repeat them
      (`RECOMMENDED_SETTINGS` is checked against the OpenAPI snapshot)
- [ ] Settings: show the server timezone and the next study-day rollover (needs an API field)
- [ ] Statistics: a longer range than 30 days and a retention-by-day line need API changes
- [ ] A 503 on `POST /reviews/answer` shows the generic save-failed alert without the Build link
      (a card on screen implies built content)
- [ ] Re-derive `WS_MAX_MESSAGE_BYTES` if review batches use the WebSocket
- [ ] Sibling burying (hold a new item's other directions until a later day)
- [ ] `review_log` retention/export before the file grows unwieldy

### Performance

- [ ] `ReviewSessionOrchestrator._plan` recomputes on every `next` and `answer` (25k-row `card_states`
      read, three catalogue queries, sorting on the event loop): measure on the real deck and cache if
      it shows
- [ ] The statistics chunk is about 410 kB because of recharts: if it grows, consider a lighter chart
- [ ] A Prometheus-style or structured metric for review latency (only if the box gets monitoring)

### Frontend UX

- [ ] The Show furigana switch keeps focus after it is toggled, so Space then toggles it again instead
      of flipping the card (and digits are ignored until focus moves): decide on blur/refocus after
      toggling (check in a browser)
- [ ] An empty on/kun reading list renders an empty `span lang=ja`; after the last card focus falls to
      the body and only the status text announces the finish; the nav active state is an exact path
      match (`/review/` is not highlighted)
- [ ] Mobile shell: Burger aria-expanded/aria-controls, hide the collapsed drawer from keyboard users,
      verify header fit at 360 px; an `ErrorBoundary` now wraps the routed page content (`AppLayout.tsx`),
      but not the header/nav/Burger around it — consider one further out if those can throw
- [ ] Toasts: session-expiry toast plus the inline 'Signed out' alert overlap in meaning; toasts at
      top-right overlap header controls
- [ ] Ask before leaving the settings page with unsaved changes
- [ ] Add Mantine `ColorSchemeScript` to `index.html` to avoid a light flash for dark-scheme users
- [ ] Check Japanese font rendering in real browsers (Hiragino, Yu Gothic, Noto) and self-host Noto Sans
      JP if the system stack looks poor
- [ ] Per-level progress is on the statistics screen (Plan 2B-3); optionally summarise it on the
      dashboard too
- [ ] Deferred review notes: `buildJustFinished` treats a cached `null` (no build ever) like nothing
      cached; Build screen: disable the button while the summary query errored, guard the modal Rebuild
      against a build started elsewhere, clamp progress percent; Home: keep good data when a background
      refetch fails (`isError && data === undefined`), add a missing-level test; shell: h1 and toast
      placement; `RequireAuth` `from`/`returnPath` hardening (also listed under Security & Auth)

### Code Quality & Types

- [ ] Type `LevelProgress.level` and the `*_by_level` keys with `LevelLabel` so the generated TypeScript
      gets a union
- [ ] Put an upper bound on the `fsrs` dependency (for example `<7`) and decouple tests from FSRS
      default learning steps
- [ ] `formatCount` is imported from `features/build` by the stats components: move it to a shared utility
- [ ] `SettingsPage.tsx` holds the page and a ~230-line form (split it)
- [ ] Move to TypeScript 7 once `typescript-eslint` and `openapi-typescript` support it (TypeScript is
      pinned to 6.0.3; see the Plan 2B-1 plan). Dependabot's `ignore` rule for TypeScript (and
      `@types/node`) major versions stops it proposing 7, so adopt it by hand: remove the ignore rule
      and the pin together

### Testing & Coverage Gaps

- [ ] Add a unit test that guards the percent-encoded read-only URI for paths like `Bunshō dir #1 100%x`
- [ ] `test_few_kanji_lack_dictionary_details`: bound on leveled kanji (`sum(kanji_by_level.values())`), not all 3,088
- [ ] Note in the integration tests that the hard-coded 2,941 / 979 / grade histogram depend on the
      locked `jamdict-data-fix` version (1.5.1a2)
- [ ] `build()` docstring `Raises:` should list `JamdictUnavailableError` (from `graded_kanji()`); test
      a catalog that raises
- [ ] Log the literals of skipped unleveled candidates at DEBUG; put `Context.kanji_catalog` after `content_repo`
- [ ] Tests for a non-UTC study-day timezone through the orchestrator and stats service (only
      `study_day` itself is DST-tested; every orchestrator and stats test uses UTC)
- [ ] Coverage gaps below 90 % per file: `db/migrations/env.py` and the `login_throttle` prune branch
      (the `0001` `downgrade()` test is listed under Reliability & Data Integrity)
- [ ] Browser end-to-end tests of the whole UI, run against the built/deployed container image
- [ ] Study loop hardening and test follow-ups from the reviews:
      - `formatDueTime` throws a RangeError on an unparseable string: guard NaN; `formatInterval` rounds after
        comparing, so 59.6 s shows "60 s", 3599.6 s "60 m" and about 350-364 days "12 mo" (round first, then
        promote the unit)
      - `cardFaces`: add a table test that every front has no answer lines (`lines` empty except recall's part of
        speech, `sentence` null, recognition `segments` null with furigana off); a kana direction other than
        glyph_to_sound or sound_to_glyph renders as sound_to_glyph instead of the placeholder; an empty main text
        has no placeholder
      - `FlipMode`/`useReviewShortcuts` tests: the Shift guard, keys typed in a text field after the flip,
        `defaultPrevented`; the flip button is not disabled while pending
      - `ReviewPage` tests: the lower clamp of `duration_ms`
      - Shell tests: the Study nav link's active state and href, a failed lazy chunk reaching the ErrorBoundary
      - `useAnswerReview` sets no explicit `retry: false` (it relies on the query client default)
      - No test isolates the "active-level" middle tier of `choices_for`'s distractor ranking (a
        candidate that is not same-level but is within `settings.active_levels`, ranked ahead of a
        truly out-of-active candidate) — the 5 shipped tests cover same-level-preferred, thin-pool
        degradation, target exclusion, and duplicate exclusion, but not this middle band specifically
      - `TypedMode`'s `accepted[0] ?? ''` fallback for an empty `accepted_answers` list is
        unexercised by any test; in practice this should be guaranteed non-empty by the backend's
        downgrade-to-flip logic, but a content-validation edge case upstream could theoretically
        defeat that guarantee
      - No regression test exists for a 409 (stale card) or network failure specifically arriving
        *during* the held-feedback window for a non-flip mode (typed/multiple-choice) — the existing
        409/failed-save tests all use flip-mode fixtures; the logic was traced by hand during review
        and found correct, but isn't test-covered for this specific interaction
      - `ChoiceMode`'s `vocab_mode` select's onChange path (and the third mode selector generally,
        in `SettingsPage.test.tsx`) isn't directly exercised by a test — `kana_mode` and
        `kanji_mode` are, `vocab_mode` isn't; low risk since all three are structurally identical
      - A failed background next-card refetch (`next.isError`) during a typed/multiple-choice
        card's held feedback replaces the whole `ReviewPage` body with the generic load-failed
        alert, discarding the still-valid feedback and Continue button; flip mode has no feedback
        step to lose this way. Gate the `next.isError` branch on `heldCard === null`, or surface
        the fetch error as a small inline notice alongside the held card instead of replacing the
        body.
- [ ] Statistics and settings hardening and test follow-ups from the reviews:
      - `useSettings` has no test that it skips refetch on window focus/reconnect or that `staleTime: 0`
        overrides the app default; the `useUpdateSettings` test does not assert the submitted document reached
        `updateSettings` or that a failed save triggers no invalidation
      - Statistics: the chart's `series.name`/`dataKey` are not tied to the row keys by a test (a rename would
        blank the bars with green tests: share constants); the pending skeleton has no `aria-busy` and no test;
        the loading/503/error states of the page render no heading; the cards-by-type row names should be
        `th scope="row"`; `VisuallyHidden` wraps a table in a span (use `component="div"`); the date tests
        assume an English locale; small dimmed text has weak contrast (design-wide)
      - Settings: Try again re-sends the original request and a success resets the form to it (newer
        edits are dropped); the 422 test should assert the field's accessible error and that an error clears
        on edit; `slider.focus()` in a test runs outside `act`; `SettingsPage.tsx` holds the page and a
        ~230-line form (split it, also listed under Code Quality & Types)
      - No focus or announcement moves to the first invalid field after a failed client-side submit
      - The settings form has no test of a second failure or 422 on Try again, and Try again drops edits made
        after the failed save

### Infrastructure, Build & CI

- [ ] Pin the base image by digest and add OCI labels
- [ ] Image trim candidates: `pip` in the base image, `watchfiles`, the venv `activate` scripts
- [ ] Local (git-ignored) `.claude/` guideline documents (`CLAUDE.md`, `llm-patterns.md`, `react.md`)
      still carry Jidou/TMDB rules
- [ ] Single source of truth for the uv pin (0.12.17 is in `ci.yml`, `release.yml` and the `Dockerfile`),
      for example an `ARG UV_VERSION` shared through a build-arg
- [ ] Use a separate image tag for the smoke project (`bunsho:smoke`) so it never retags a developer's
      `bunsho:local`
- [ ] First real run of `release.yml` (it has never run), and check that Dependabot's docker ecosystem
      can bump the two Dockerfile image references
- [ ] Docker Node stage: add `--platform=$BUILDPLATFORM` so multi-arch builds do not run the JS build
      under emulation
- [ ] Health-check access-log noise: the Docker healthcheck adds ~2,900 uvicorn access-log lines a day
- [ ] `.gitattributes` `frontend/** text eol=lf` would corrupt binary assets: add `binary` overrides
      before committing any image or font
- [ ] If the root `.gitignore` `build/` pattern is narrowed to `/build/`, remove the
      `!src/features/build/` override in `frontend/.gitignore`
- [ ] Root `.gitignore` patterns `lib/`, `env/`, `var/`, `parts/`, `downloads/` would silently ignore a
      future `frontend/src/lib` or `src/env`: anchor them (as with `build/` -> `/build/`)
- [ ] The OpenAPI snapshot embeds `info.version`: a release version bump fails
      `test_the_committed_snapshot_matches_the_app` until `scripts/export_openapi.py` and
      `npm run gen:api` are re-run (add to the release checklist)

### Open Decisions

- [ ] Verify the JMdict/KANJIDIC2 (EDRDG licence) and, later, KanjiVG attribution wording before
      distributing a built `content.db` or a Docker image that contains it
- [ ] Optional history cleanup: four haiku-authored commits carry a "Claude Haiku 4.5" trailer (two on
      the subject line)

### Later Sub-Projects

- [ ] 4. Stroke order / handwriting (needs a stroke-data source, probably KanjiVG; jamdict has none)
- [ ] 5. Anki `.apkg` export
- [ ] 6. Sentence practice and grammar (grammar source still open)
- [ ] Study-path presets (for example Beginner: kana first, then kanji and vocabulary together)
      built on the type switches and the kana gate

### Deferred Minor Findings (low priority)

- [ ] furigana parser: untested edge cases (multiple/leading spaces, bare `[reading]`, unclosed
      `<mark>`); `(?<=])` vs `(?<=\])` spelling
- [ ] importer: empty `Expression`/`Reading` accepted silently; encrypted-zip `RuntimeError`/`OSError` not wrapped
- [ ] `is_kanji` misses CJK Extension B+ and compatibility ideographs
- [ ] `logging_setup`: `force=True` is still the default (a `force=False` option exists; the launcher
      configures logging before uvicorn starts, so nothing is wiped today); the line format is only
      half logfmt (free-text message)
- [ ] `.gitattributes` now covers the Dockerfile, `.dockerignore`, YAML and shell files only; add
      `* text=auto eol=lf` and `*.apkg binary` to stop the remaining CRLF warnings (for example on Markdown)
- [ ] Test thinness: kana romaji spot-checks (~6 of 208), repeated-kanji case, `Kanji` frozen
      inheritance, Protocol conformance assertions

---

## Completed

Kept in the order delivered, grouped by the plan that shipped each item, for history.

### Now (unleveled kanji, Plan 2)

- [x] **Unleveled kanji rows** — done (commits `3509d04`, `bbdc2f7`). Kanji with a KANJIDIC2 grade of
      1–10 (jōyō + jinmeiyō) that are not in the deck are stored with `level = None`: +979 rows, 3,088
      kanji in total, schema v2. Compatibility code points (e.g. U+FA19) are excluded. The real build
      now takes ~31 s.
- [x] Plan 2: `list_kanji()` / `counts().kanji` now include unleveled rows and `Kanji.level` may be
      `None`; lessons filter them via `ContentRepository.catalog` (Plan 2A)

### Plan 1B — service shell and Plan 1C — delivery

Baseline from the spec:
- [x] `progress.db` schema (SQLAlchemy 2.0 async + aiosqlite) + Alembic migrations, timestamped backup at startup
- [x] JWT auth, single local user (all REST and WebSocket routes protected)
- [x] FastAPI app factory, `/api/v1`: `health`, `admin/config-check`, `admin/content/build` (`dry_run`,
      background task), WebSocket progress
- [x] `bunsho` launcher entry point (uvicorn, no click/rich)
- [x] Plan 1C: Dockerfile (multi-stage, non-root), `compose.yaml` (port 8192, named data volume,
      read-only root filesystem), `.dockerignore`, `.gitattributes`
- [x] CI rewrite (drop postgres/redis/jidou-api), plus a container smoke-test job (Plan 1C)
- [x] Jidou content stripped from `.claude/skills/{db-migration,release-notes,check-pr}` and
      `.claude/settings.local.json` (no Jidou/TMDB text left there); the committed `.gitignore`
      (commit `ff3621b`) ignores `.claude/` and `.agents/`

Carry-forward from Plan 1A's final review:
- [x] Rebuild endpoint: `_replace_with_retry` retries `PermissionError` (`services/content_repository.py`);
      a second build is refused with `BuildAlreadyRunningError` -> HTTP 409 (`orchestration/build_tasks.py`,
      `api/routers/admin.py`)
- [x] `on_progress` callback cannot raise into the build (`build_tasks.py`, `_make_callback`);
      `content_build_failed` is logged when `writer.write` raises (`orchestration/content_build.py`)
- [x] Dry run is a background task with progress (`BuildTaskManager.start(dry_run=...)`), never a
      synchronous request
- [x] `create_context` catches `JamdictUnavailableError`/`OSError`/`sqlite3.Error` from the jamdict
      service (`factories.py`); `ContentRepository(...)` opens no connection and is only built when
      `content.db` exists; `/health` exists
- [x] Config loader wraps `FileNotFoundError`/`TOMLDecodeError` in `ConfigError` (`config/loader.py`);
      `data_dir` is validated (`config/settings.py`); the image sets absolute `/data` and
      `/app/resources` (`Dockerfile`)
- [x] Integration fixtures fail, not skip, when `CI` is set (Plan 1C); `bandit -c pyproject.toml` runs in CI
- [x] `src/bunsho/py.typed` and `.pre-commit-config.yaml` (Plan 1C; pre-commit is optional per clone)
- [x] Call `ContentRepository.verify_schema()` at startup and in Plan 2 before reading (today only
      `/health` calls it) (Plan 2A)

Delivered by Plan 1C (see `CHANGELOG.md` and the README's "Running with Docker"):
- [x] Migration lock file, actionable startup errors (database path, backups folder, ownership hint),
      sweep of stale `content.db.<hex>.tmp` files
- [x] Proxy story: `server.trusted_proxies`, strict validation, documented nginx `X-Forwarded-For` requirement
- [x] Bounded graceful shutdown (`stop_grace_period: 60s`), 64 KiB WebSocket frame limit
- [x] Container smoke test (`scripts/smoke_test.py`) and CI job; CI skip policy; CHANGELOG

Deferred from Plan 1C, delivered later:
- [x] OpenAPI quality, needed before generating TypeScript types: explicit operation ids, documented
      401/404/409/429/503 responses, WebSocket message schemas in `components` (Plan 2A)
- [x] CORS: methods beyond GET/POST are done for `PUT` (Plan 2A); the Vite dev server uses a proxy, so
      no CORS is needed (Plan 2B-1); `BUNSHO_SERVER__CORS_ORIGINS` stays for setups without the proxy
- [x] Typed `unleveled_kanji` in the content summary (today it is only in `meta` as a string) (Plan 2A)
- [x] WAL journal mode and `PRAGMA foreign_keys=ON` for `progress.db` (Plan 2A)

### Plan 2 — review engine and first UI

- [x] `Scheduler` interface + `FSRSScheduler` (fsrs), card generation, `ReviewSessionOrchestrator` (Plan 2A)
- [x] Review/stats/settings endpoints (Plan 2A); React 18 + Vite + TS frontend (Plan 2B) (login,
      first-run build, dashboard, flip + grade review, stats)
- [x] Document that content ids are opaque (`vocab:度:ど#2` exists); add an unfiltered `list_vocab()`
      consumer test (Plan 2A)
- [x] Instance lock for the data folder: one instance per volume (today two instances on one volume both
      start and the startup temp-file sweep can break the other's running build); pair it with WAL and
      `PRAGMA foreign_keys=ON` once every card grade writes to `progress.db` (Plan 2A)
- [x] Image: a Node stage (`FROM node AS frontend`), an explicit `COPY --from=frontend` of the built
      assets, a `StaticFiles` mount in the app, and the read-only root filesystem implications (Plan 2B-1)
- [x] CI: a `frontend` job (`tsc -b`, eslint, vitest); decide whether `smoke` needs the built frontend (Plan 2B-1)
- [x] Dependabot: add the `npm` entry for `/frontend` (stubbed in the `.github/dependabot.yml` header
      comment) (Plan 2B-1)
- [x] Extend the smoke test: `index.html` is served, a review round-trip (round trip: Plan 2A;
      `index.html` check: Plan 2B-1); revisit `EXPECTED_COUNTS` if the content schema changes

### Plan 2B-2 and later

- [x] Dashboard and flip-and-grade review with keyboard shortcuts and furigana (Plan 2B-2)
- [x] Statistics and settings screens (Plan 2B-3)
- [x] Code-split the routes: the production main chunk was about 540 kB, now about 388 kB (lazy routes, Plan 2B-2)
- [x] Typed-answer and multiple-choice review modes plug into the `ReviewMode` contract
      (`features/review/reviewMode.ts`) (Plan: typed-mc-review-modes)

### Later sub-projects

- [x] 3. Typed-answer (romaji -> kana; ぢ/じ and づ/ず share romaji, accept both) and multiple-choice
      modes (Plan: typed-mc-review-modes)

### Session revocation (1.4.0)

- [x] Server-side logout: every login has a `sid` claim, `POST /auth/logout` revokes it (stored in
      `progress.db`, migration 0002), old tokens without a `sid` are rejected, and the session's open
      WebSockets are closed with 1008
- [x] Logout can no longer be undone by a refresh in flight: `session.ts` has an epoch and a late
      refresh answer (success or 401) from an earlier epoch is dropped
- [x] Tested the logout -> login stream lifecycle (stream closes on logout, a new one opens after
      login) and the StrictMode double mount

### WebSocket connection cap

- [x] At most 16 WebSockets can be connected but unauthenticated at once (`PendingAuthGate`); a
      17th is refused with 1008 before it is accepted. The cap is global, not per client host (behind
      a proxy without `server.trusted_proxies` every client shares one host), and authenticated
      streams never count against it

### Decisions

- [x] Bunshō's own license: **MIT** (decided 2026-09-19; `LICENSE`, `pyproject.toml`, README license
      section). The deck in `resources/` stays GPL-3.0 with its own LICENSE; a built `content.db` is a
      derived work.
- [x] Plan 1A merged to `main` (PR #1, 2026-09-19). Working method going forward: branch -> push -> PR;
      James merges.
- [x] The `.gitignore` decision: committed in `ff3621b`; `.claude/` and `.agents/` stay ignored (local
      agent config)
