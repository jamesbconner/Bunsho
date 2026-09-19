# Bunshō (文章) — Design & Plan for Sub-projects 1 + 2

## Context

Bunshō is a personal Japanese-learning tool: kana, JLPT N5–N1 kanji and vocabulary, then sentences and
grammar, studied with spaced-repetition flashcards. It uses the `jamdict` library with the
`jamdict-data-fix` SQLite database, plus a community Anki deck for JLPT-levelled vocabulary.

Requirements gathered in brainstorming:
- Single user (James), Mac + Windows, progress must follow him across machines.
- An always-on home box exists; access is home network only (no phone, no offline).
- Flashcards: own SRS engine, Anki-compatible (import now, `.apkg` export later).
- First slice: kana + kanji + vocabulary. N5–N1 levels come from the Anki deck.

## Decisions (locked)

| Topic | Decision |
|---|---|
| Service type | Containerized web app: FastAPI + React/Vite in one Docker container on the home box, port **8192** |
| Native desktop / hybrid | Rejected (sync burden, two installers, offline not needed). Web app can grow into a PWA later |
| Interface | **No CLI.** FastAPI only. `bunsho` script is a thin uvicorn launcher (no click/rich) |
| Auth | **JWT, single local user** (env-configured username + hashed password; short-lived access + refresh; all REST and WebSocket routes protected) |
| SRS | `Scheduler` interface, **FSRS first** (`py-fsrs`), SM-2 addable later |
| Anki role | Own in-browser SRS + import `.apkg`; export `.apkg` in sub-project 5 |
| Kanji levels | **Derived** from the vocab deck: each kanji gets the easiest level of any word containing it. KANJIDIC2 (via jamdict) enriches. Kanji in no deck word → unleveled, excluded from lessons by default |
| Vocab source | `resources/JLPT_N5_to_N1_Japanese_Vocabulary.apkg` — 7,734 notes, 15,468 cards, tags `jlpt_N1`…`jlpt_N5` (authoritative; deck hierarchy is misleading). License **GPL-3.0** (verified) |
| Deck in git | **Yes**, with `resources/LICENSE`, `resources/README.md` (source URL, version, sha256); importer verifies sha256 |
| Name | Display name **Bunshō** everywhere user-visible. ASCII slug for technical identifiers: **`bunsho`** (PyPI names, Docker image/service, import package, URLs must be ASCII) |
| progress DB stack | SQLAlchemy 2.0 async (aiosqlite) + Alembic, SQLite batch-mode migrations |

## Architecture (modular monolith, hexagonal boundaries)

```
src/bunsho/
  models/          Pydantic domain types: Kana, Kanji, Vocab, Sentence, Card, ReviewLog, Grade
  services/        JamdictService, AnkiDeckImporter, FuriganaParser, ContentRepository,
                   ProgressRepository, Scheduler (Protocol) + FSRSScheduler, AuthService
  orchestration/   ContentBuildOrchestrator, ReviewSessionOrchestrator
  api/             APIRouter modules under /api/v1 (auth, content, reviews, stats, admin, health, ws)
  config/          ConfigNormalizer (case-insensitive, typed accessors), .env loading, validation
  context.py       Context dataclass: config, paths, logger, services, dry_run flag
  factories.py     create_scheduler(config) etc. — validate config, ValueError on unsupported type
  main.py          uvicorn launcher + FastAPI app factory
frontend/          React 18 + Vite + TypeScript
alembic/           progress.db migrations
tests/             TestBase / shared fixtures, unit/, integration/
```

Three SQLite files, split by how replaceable they are:

| File | Role | Written by | If lost |
|---|---|---|---|
| `jamdict.db` (jamdict-data-fix) | reference data | never | re-install |
| `content.db` | kana, kanji (derived levels), vocab, sentences | content build only | **rebuild** |
| `progress.db` | card state, review log, settings | the app on every review | **irreplaceable** |

Stable content IDs decouple the two: `kana:hira:あ`, `kanji:漢`, `vocab:{expression}:{reading}`
(handles the 128 duplicate expressions), where `reading` is the plain kana reading. Two notes with
the same expression and plain reading but different raw `Reading` markup (a homograph, e.g. the two
N3 notes for 度 with reading `ど`) are disambiguated in deck order: the second gets `#2`, the third
`#3` (`vocab:度:ど#2`). Two notes with identical raw markup are a true duplicate and fail the build.
Rebuilding `content.db` never orphans progress (the deck is sha256-pinned, so suffixes are stable).

Startup behavior: `progress.db` failure → **fail fast**. `content.db` missing → app starts in
"content not built" state and the UI shows a first-run Build screen. jamdict is build-time only; missing at
runtime → warning, continue. Alembic `upgrade head` runs at startup after a **timestamped copy of
`progress.db`**. Config is validated at startup, reporting all failures together.

## Content model

- **Kana:** hiragana + katakana incl. dakuten/handakuten and yōon. Static table; no jamdict needed.
- **Kanji:** two groups, stored in this order. (1) *Leveled*: one row per kanji found in deck vocabulary,
  with its derived level (2,109 in the pinned deck). (2) *Unleveled* (`level` is `None`): every kanji with a
  KANJIDIC2 grade of 1–10 (jōyō + jinmeiyō) that is not in the deck, ordered by grade then frequency
  (979 rows; only unified-ideograph code points, so CJK compatibility forms such as U+FA19 are excluded).
  Rows carry on/kun readings, meanings, stroke count, radical, grade, frequency (KANJIDIC2 via jamdict).
  `ContentRepository.list_kanji()` returns all 3,088 rows; use `level=X` or `unleveled=True` to filter.
  Unleveled kanji are excluded from lessons by default (Plan 2 must filter them). `content.db` schema
  version is `"2"` (nullable `kanji.level`).
- **Vocab:** deck fields `Expression`, `English definition`, `Reading`, `Grammar` (actually POS),
  `Additional definitions`, `Example JP`, `Example EN`; tags for level, register
  (`honorific/polite/humble`), `usually_kana`.
- **Furigana:** parse `漢字[かんじ]` into ruby segments; strip HTML; keep `<mark>` target word as a highlight span.
- **Sentences:** deck example JP/EN become `Sentence` rows linked to their vocab item (basis for sub-project 6).

## Review engine

- **Card** = item + direction. Kana: glyph→sound, sound→glyph. Kanji: kanji→meaning, kanji→reading,
  meaning→kanji. Vocab: Recognition / Recall (as in the deck).
- **`Scheduler` Protocol:** `schedule(state, grade, now) -> state`. `FSRSScheduler` wraps `py-fsrs`;
  target retention configurable (default 90%). Clock injected for deterministic tests.
- **Modes produce a Grade; the engine only sees the Grade** (Again/Hard/Good/Easy). Sub-project 2 ships
  flip + self-grade behind a `ReviewMode` interface; typed/multiple-choice/stroke-order plug in later.
- **Sessions:** due cards first, then new cards up to a per-type daily limit; new material unlocks N5→N1
  (overridable). Append-only `review_log` (enables FSRS parameter optimization later).

## API (all under `/api/v1`, JWT-protected except login/health)

`POST /auth/login`, `POST /auth/refresh` · `GET /content/...` · `GET /reviews/next`,
`POST /reviews/{card_id}/answer` · `GET /stats/summary` · `GET /health` ·
`GET /admin/config-check` · `POST /admin/content/build` (`dry_run` flag, background task) ·
WebSocket for task progress (typed messages, same Pydantic schemas as REST). CORS explicit.

## Frontend (sub-project 2)

React 18 + Vite + TS (strict), TanStack Query, `ofetch` client layer, types generated from the OpenAPI spec
(`openapi-typescript`), error boundaries, WebSocket with reconnect (backoff + jitter) and a visible
connection-state indicator. Screens: login, first-run Build, dashboard (due counts by type/level),
review (flip + grade), basic stats. Tests: Vitest + React Testing Library, network mocked (MSW).

## Testing & delivery

- pytest with shared `TestBase`/fixtures: in-memory SQLite for `progress.db`, synthetic tiny `.apkg` for
  importer unit tests, jamdict mocked in unit tests, `integration` marker for the real deck + real
  jamdict-data-fix DB. Coverage ≥ 90%. Key unit targets: furigana parser, kanji level derivation, FSRS
  wrapper, grade mapping, queue building, JWT flow, migration backup.
- Docker: multi-stage (Node build → slim Python runtime), non-root, `HEALTHCHECK` on `/api/v1/health`,
  single compose service on 8192, volumes `/data` (rw) and `resources/` (ro).
- Docs: Google-style docstrings, sphinx later; `CHANGELOG.md` maintained.

## Repo cleanup (part of sub-project 1)

1. **Rename** slug: `pyproject.toml` (`name`, entry point), `src/bunshou/` → `src/bunsho/`; description and
   README use "Bunshō". Recreate `.venv` (`uv sync`) so the editable install matches.
2. **pyproject.toml** to project standards: `hatchling` backend (currently `uv_build`), `requires-python
   >=3.13` (currently `>=3.11`), `dev` extra (CI already runs `uv sync --extra dev`), real dependencies.
3. **Skills — strip Jidou content:**
   - `.claude/skills/db-migration/SKILL.md`: rewrite for SQLite + aiosqlite + `src/bunsho/models/` +
     `progress.db` (batch mode; keep review steps: downgrade check, destructive-op flags, `--sql` dry run,
     backup).
   - `.claude/skills/release-notes/SKILL.md`: replace "Jidou" and the example headings with Bunshō ones.
   - `.claude/skills/check-pr/` (`SKILL.md`, `.sh`, `.ps1`): remove hardcoded `jamesbconner/Jidou`; derive
     the repo via `gh repo view` / `{owner}/{repo}`.
   - Inspect `.claude/settings.local.json` (8 Jidou-related matches) and clean up.
4. **`.github/workflows/ci.yml`:** drop `postgres`, `redis`, `jidou-api`, `/api/shows`, `/api/files`,
   `alembic current` against Postgres; replace integration job with a compose smoke test (login → content
   build from the real deck → `/health`). Keep lint/mypy/bandit/test matrix/frontend/build jobs. Review
   `release.yml` for the same.
5. **Not touched without approval:** `.claude/CLAUDE.md` and the other guideline docs. CLI, TMDB and
   external-API rate-limiting sections simply don't apply here (no CLI; no external APIs; no LLM in scope).
6. Add `resources/LICENSE` (GPL-3.0), `resources/README.md` (provenance, sha256).

## Out of scope (later sub-projects)

3. Typed-answer and multiple-choice modes · 4. Stroke order/handwriting (needs a stroke-data source,
likely KanjiVG; not verified that jamdict ships one) · 5. Anki `.apkg` export · 6. Sentence practice and
grammar (grammar source still open). If an LLM feature is ever added, the LLM caching/rate-limit guidelines apply.

## Open items (non-blocking)

- **Bunshō's own license.** Deck is GPL-3.0; GPL-3.0 for the whole repo is the simplest consistent
  choice if the repo is ever published. Decide before first publish. `pyproject.toml` currently has none.
- Confirm the `bunsho` ASCII slug (alternative: keep `bunshou`, which you said you don't want).
- jamdict/KANJIDIC2/KanjiVG data licenses (attribution-required) — verify wording before publishing.
- Verify `jamdict-data-fix` DB path resolution inside the container, and current versions of `py-fsrs`,
  `jamdict`, FastAPI, SQLAlchemy, Alembic (via context7) at implementation time.

## Implementation order

**Sub-project 1 (foundation + content):** repo cleanup & pyproject → config/context/factories →
migrations + `progress.db` schema → `FuriganaParser` + `AnkiDeckImporter` (sha256 check) →
`JamdictService` → kanji level derivation → `ContentBuildOrchestrator` (+ `dry_run`) →
`content.db` repos → health/config-check/admin build endpoints + WebSocket progress → Dockerfile/compose → CI.

**Sub-project 2 (review engine + UI):** `Scheduler` + `FSRSScheduler` → card generation →
`ReviewSessionOrchestrator` → auth (JWT) → review/stats endpoints → frontend scaffold with generated types →
login, first-run, dashboard, review (flip + grade), stats → end-to-end smoke test.

## Verification

- `uv sync --extra dev`, then `uv run ruff check .`, `ruff format --check .`, `mypy src/`, `bandit -r src/ -l`,
  `pytest --cov=src` (≥ 90%, integration marker run against the real deck + jamdict).
- Build content from the real deck: expect 7,734 vocab items, level counts N1 3053 / N2 1737 / N3 1647 /
  N4 630 / N5 667, derived kanji levels sane (spot check well-known N5 kanji land at N5), `dry_run` writes nothing.
- `docker compose up --build`: `/api/v1/health` passes on port 8192; log in from both the Mac and the
  Windows machine; complete a review on one, see the updated due counts on the other.
- Restart the container: progress persists on the `/data` volume; a startup migration creates a timestamped backup.
- Frontend: `npx tsc -b`, `npm run lint`, `npm run test`.
