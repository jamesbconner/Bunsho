# Bunshō Plan 2A: Review Engine Backend — Design

Status: design approved 2026-09-20 (brainstorming). Next: implementation plan.
Parent design: `2026-09-19-bunsho-foundation-and-review-engine-design.md` (this spec refines its
"Review engine" and "API" sections; where they differ, this spec wins).

## Scope and slicing

Plan 2 is split by layer, as Plans 1A/1B/1C were:

- **2A (this spec): backend.** FSRS scheduler, card model, new-card policies, review session
  orchestration, review/stats/settings API, and the `progress.db` hardening that must land with the
  first grade writes. Verified end to end through the API and the container smoke test. No UI.
- **2B (later, own spec): frontend and delivery.** React 18 + Vite + TS UI, generated API types, Docker
  Node stage, frontend CI job, Dependabot `npm`, smoke-test additions for `index.html`.

Out of scope for 2A: refresh-token logout/revocation, a cap on unauthenticated WebSocket connections,
backup pruning, sibling burying, typed-answer and multiple-choice modes (sub-project 3), Anki export.

## Decisions (locked in brainstorming)

| Topic | Decision |
|---|---|
| Card materialization | **Lazy.** A `card_state` row exists only once the card has been graded. `GET /reviews/next` creates nothing. |
| New-card selection | A `NewCardPolicy` strategy, chosen by the `new_card_policy` setting: `strict_order`, `mastery_unlock`, `pinned_levels`. Factory validates and raises `ValueError` on unknown values. |
| Daily limits | Count **cards** (not items), per type, derived from `review_log`. Defaults: kana 20, kanji 15, vocab 20. `0` = unlimited. |
| Study day | Starts at a rollover hour (default 04:00) in the server timezone (`TZ`). |
| Card identity in the API | `(item_id, direction)` in a request body. `POST /reviews/answer` replaces the parent spec's `POST /reviews/{card_id}/answer` because content ids contain `:` and `#` (for example `vocab:度:ど#2`). |
| Concurrency | Answer requests carry `expected_last_review`; a mismatch returns 409. |
| Schema | No new migration. `card_state`, `review_log` and `app_setting` already have every column needed. |

## Cards and scheduler

**Card = `(item_id, direction)`.** Direction values (string enums):

- Kana: `glyph_to_sound`, `sound_to_glyph`
- Kanji: `kanji_to_meaning`, `kanji_to_reading`, `meaning_to_kanji`
- Vocab: `recognition`, `recall`

A direction is valid only for its item type; an invalid pair is a 422, an unknown `item_id` a 404.
Content ids are opaque strings; nothing parses them.

**Types (`models/`).**

- `Grade`: `IntEnum`, Again=1, Hard=2, Good=3, Easy=4.
- `CardSchedule`: frozen Pydantic model with `state`, `step`, `stability`, `difficulty`, `due`,
  `last_review`; these map one to one onto the `card_state` columns. `state` follows the FSRS states
  (New=0, Learning=1, Review=2, Relearning=3).
- `Scheduler` Protocol (`services/protocols.py`): `initial(now) -> CardSchedule` and
  `schedule(state, grade, now) -> CardSchedule`. The scheduler has no clock; callers pass `now`.
- `FSRSScheduler` wraps `py-fsrs` with a configurable target retention (default 0.90) and a fuzzing
  switch (off in tests). `create_scheduler(config)` is the factory (ValueError on unsupported type).
  The current `py-fsrs` API must be verified (context7) before implementation.
- The scheduler also exposes projected next intervals for all four grades, used for button labels.

**`ProgressRepository`** (async SQLAlchemy over `progress.db`):

- `get_card(key)`.
- `record_review(key, before, after, grade, mode, duration_ms)`: upserts `card_state` and appends
  `review_log` in **one transaction**. `state_before` is 0 for a new card.
- `due_cards(now, limit)`, ordered by `due`.
- `introduced_keys()`.
- `new_cards_introduced(window)`: count of `review_log` rows in the window whose `state_before` is New.
  No separate counter table, so the count cannot drift.
- Settings get/set over `app_setting`.

## New-card policies and the session

**Study day.** `study_day_window(now, rollover_hour, tz)` is a pure function returning the window start
and end as UTC instants. Timestamps are stored as UTC ISO strings (existing columns).

**Catalogue.** A `ContentCatalog` service builds the ordered, level-tagged catalogue per type from
`ContentRepository`, in stable `content.db` order. It excludes unleveled kanji in one place;
`ContentRepository` gains a `leveled_only` option. Kana has no level.

**Policies** (`NewCardPolicy` Protocol: catalogue + introduced keys + per-level progress in, next
unintroduced cards out). Two rules apply to all three: kana is never level-gated, and unleveled kanji
are never offered. Level gates are evaluated **per type** (kanji progress never gates vocab, and the
reverse).

| Policy | Rule |
|---|---|
| `strict_order` | N5 first, then N4 and so on. Level N+1 starts only when every card of level N has been introduced. |
| `mastery_unlock` | Same order, and level N+1 also waits until at least a threshold share (default 0.80, setting) of **all** cards at level N are in the FSRS Review state. |
| `pinned_levels` | Draws only from the levels listed in settings (default N5), in order. |

Rationale for measuring mastery against all cards at the level: measured against introduced cards only,
passing 8 of the first 10 cards would unlock N4 while N5 was barely touched.

**`ReviewSessionOrchestrator.next(now)`:**

1. If any card is due, return the earliest-due card (any type).
2. Otherwise choose a new card: pick the type with the largest remaining share of its daily allowance
   (ties: kana, kanji, vocab), then take that type's next card from the active policy.
3. Otherwise return no card and set `next_due_at` to the soonest future due time.

`next` is stateless: an ungraded new card is returned again in the same order.

**`ReviewSessionOrchestrator.answer(...)`:** load the card (or `initial()`), check
`expected_last_review` (409 on mismatch), `schedule`, `record_review`, return fresh counts.

## API (all under `/api/v1`, JWT-protected)

| Route | Purpose |
|---|---|
| `GET /reviews/next` | Hydrated card or none, plus `next_due_at` and counts (due, new remaining by type) |
| `POST /reviews/answer` | Body: `item_id`, `direction`, `grade`, `expected_last_review` (null for a new card), `duration_ms?`. Returns fresh counts |
| `GET /stats/summary` | Reviewed and introduced today; daily review counts for the last 30 days; 30-day retention (share of reviews of cards in the Review state graded Hard or better); cards per type and state; per-level introduced / total / in-Review |
| `GET /settings`, `PUT /settings` | `new_card_policy`, `new_limits` per type, `target_retention`, `rollover_hour`, `active_levels`, `mastery_threshold` |

- The hydrated card carries front and back fields, furigana segments, examples, `expected_last_review`,
  and the projected interval for each grade.
- `PUT /settings` validates everything and applies all or nothing (422 with the list of problems).
  Ranges: retention 0.70–0.99, rollover 0–23, limits ≥ 0, threshold 0–1. The orchestrator reads settings
  per call, so changes apply immediately.
- Errors: 401 auth; 404 unknown item; 422 invalid direction/settings; 409 stale
  `expected_last_review`; 503 `content.db` not built. `detail` is a string except for 422 (a list).

## Hardening bundled with the first grade writes

- **WAL and foreign keys:** `journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON` via an engine
  connect hook on `progress.db`. The startup backup is a plain file copy today, which is unsafe under
  WAL: verify it and, if needed, switch to the SQLite backup API.
- **Instance lock:** a lock file in the data folder with an OS-level exclusive lock held for the process
  lifetime (reuse the Plan 1C migration-lock mechanism). A second instance on the volume fails fast with
  an actionable `StartupError`. This also closes the startup temp-file sweep hazard.
- **`ContentRepository.verify_schema()`** is called at startup, not only by `/health`.
- **OpenAPI quality:** explicit `operation_id` on every route, documented 401/404/409/429/503 responses,
  WebSocket message models published in `components`, and a test that fails if any route lacks an
  `operation_id` (keeps 2B's generated types stable).
- **Content summary:** a typed `unleveled_kanji` count plus per-level counts.
- **CORS:** `PUT` added to the allowed methods; the Vite dev origin documented as an opt-in setting;
  empty by default.
- Document that content ids are opaque, and add an unfiltered `list_vocab()` consumer test.

## Testing

pytest with shared fixtures, in-memory `progress.db`, coverage at least 90%.

- **Scheduler:** deterministic (fuzzing off, injected `now`); interval projections increase from Again to
  Easy; `CardSchedule` round-trips through the `card_state` columns.
- **Study day:** rollover boundaries and a DST transition.
- **Policies:** table-driven, including the level gate, the mastery threshold edge, kana and unleveled
  kanji handling.
- **Orchestrator:** queue order (due before new, then type balancing) with a fake clock; `record_review`
  rolls back both tables together when the log insert fails; stale `expected_last_review` gives 409;
  settings validation is all-or-nothing.
- **Hardening:** WAL and foreign-key pragmas active; backup copes with WAL; a second instance is refused
  by the lock. Concurrency and lock tests run 40 or more times before being called stable.
- **API/OpenAPI:** 401/404/409/422/503 route tests; the operation-id guard.
- **Integration (real `content.db`, CI fails rather than skips):** a full day simulation — new cards are
  introduced up to the limits, grading moves them, and `next` returns nothing when the day's work is done.
- **Container smoke test:** login, next, answer, next, stats, settings against the real image.

## Order of work

One branch (`feat/plan-2a-review-engine`), draft PR opened early so CI runs, no stacked PRs.

1. Add `py-fsrs` (verify its API first), domain types, `Scheduler`, `FSRSScheduler`, factory.
2. `ProgressRepository`, WAL/FK hook, backup check.
3. Instance lock and `verify_schema()` at startup.
4. `ContentCatalog`, `leveled_only`, study-day window, the three policies, policy factory.
5. Settings service and validation.
6. `ReviewSessionOrchestrator` (next, answer, stats).
7. Routers, schemas, error mapping.
8. OpenAPI quality, operation-id guard, typed content summary, CORS.
9. Smoke test extension, README, CHANGELOG, TODO.
10. Whole-branch review.

## Risks

- `py-fsrs` API drift: verify the installed version's API before writing the wrapper.
- DST on the rollover hour: covered by an explicit test.
- FSRS learning steps for cards that come due minutes later in the same session: `next` returns none
  with `next_due_at`, and the UI (2B) decides how to wait.
- WAL on the volume: the compose file uses a named volume, which supports it; a network filesystem would not.

## Implementation notes (added while planning and building)

- The item type is derived from the direction, so an unknown item is a 404 and an unknown
  direction a 422; there is no "invalid pair" case.
- `ContentRepository.catalog(item_type)` returns ids and levels only (unleveled kanji excluded in
  SQL); it replaces the `leveled_only` option on `list_kanji`.
- The hydrated card carries the domain item (`kana`, `kanji` or `vocab`) rather than pre-rendered
  front/back fields; the frontend decides the layout per direction.
- The study-day timezone is `TZ` when set, otherwise UTC with a startup warning; `tzdata` is a
  dependency.
- The startup backup already used the SQLite backup API (WAL-safe); a test now proves it.
- The review settings are one JSON document in `app_setting` (`review_settings`); `PUT` is a full
  replacement.
- The FSRS library's PyPI distribution is `fsrs` (import name `fsrs`), not `py-fsrs`; the
  references to `py-fsrs` above are the name used while planning.
