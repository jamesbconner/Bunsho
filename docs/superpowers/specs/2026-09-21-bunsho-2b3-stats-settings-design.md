# Bunshō Plan 2B-3: Statistics and Settings Screens — Design

Status: design approved 2026-09-21 (brainstorming). Next: implementation plan.
Parent designs: `2026-09-19-bunsho-foundation-and-review-engine-design.md` (its "Frontend" section),
`2026-09-20-bunsho-2a-review-engine-design.md` (the stats and settings API, merged in PR #9),
`2026-09-20-bunsho-2b1-frontend-skeleton-design.md` and `2026-09-20-bunsho-2b2-study-loop-design.md`
(the app this extends, merged in PRs #11 and #13).

## Scope

The last two screens of the UI: **statistics** (`/stats`) and **settings** (`/settings`), each a lazy-loaded
route with its own navigation link, plus two link-ups promised by earlier plans: the review screen's
"done for now" state links to Settings, and per-level progress lives on the statistics screen. No backend
change.

Out of scope: an unsaved-changes prompt when navigating away; per-field autosave; typed-answer and
multiple-choice review modes; stroke order; undo and study-ahead (they need API support); the CSP header;
browser end-to-end tests.

## Decisions (locked in brainstorming)

| Topic | Decision |
|---|---|
| Charts | **Mantine Charts** (`@mantine/charts`, which uses `recharts`), latest versions, loaded only on the statistics route. The one chart is a 30-day bar chart. |
| Stats layout | One page: Today, Last 30 days, Your cards, Progress by level. Per-level progress is not on the dashboard. |
| Settings model | One form over the whole document; explicit **Save** (`PUT /settings`, all or nothing); **Reset to recommended values** only refills the form. No autosave, no leave-page prompt. |
| Policy-specific fields | Active levels are used only by *Pinned levels* and the mastery threshold only by *Mastery unlock*: shown disabled with a hint under other policies, values still saved. |
| Validation | The API's ranges in the browser (`@mantine/form`), server 422 field messages mapped onto the matching fields, a general alert as the fallback. |
| Versions | Same rule as before: latest stable of everything; any older major needs a recorded reason. The two new packages are the only dependency change. |

## Structure

```
frontend/src/
  api/endpoints.ts        + statsSummary(), getSettings(), updateSettings()   (types from schema.d.ts only)
  api/queries.ts          + queryKeys.statsSummary / settings, useStatsSummary(), useSettings(), useUpdateSettings()
  features/stats/
    StatsPage.tsx         page, states (loading, error, 503 -> Build link), layout
    TodayPanel.tsx        reviewed today, introduced today, 30-day retention
    ReviewsChart.tsx      Mantine BarChart + visually hidden data table + empty state
    CardsByType.tsx       table: total / learning / review / relearning per type
    LevelProgress.tsx     per-level rows with a two-tone progress bar and the numbers
  features/settings/
    SettingsPage.tsx      load, form, Save/Reset, error and success handling
    settingsForm.ts       defaults constant, validation rules, 422 -> field-error mapping (pure)
    PolicyField.tsx       the three policy radio cards
  components/AppLayout.tsx  + Statistics and Settings links
  features/review/ReviewFinished.tsx  + "Change your daily limits in Settings" link
  App.tsx                 + lazy routes /stats and /settings
```

## Statistics screen

Data: one query `['stats','summary']` on `GET /stats/summary` (`StatsSummary`: `reviewed_today`,
`introduced_today` per type, `retention_30d` or null, `daily_reviews` for the last 30 study days, `by_type`
counts per scheduling state, `by_level` progress). A 503 (content not built) shows the message and a link to
the Build screen; other errors show the usual alert with Try again.

- **Today:** cards reviewed today; new cards introduced today per type and in total; 30-day retention as a
  percentage with one decimal ("Not enough reviews yet" when it is null), with a short note that it is the
  share of reviews of known cards graded Hard or better.
- **Last 30 days:** a Mantine `BarChart` of reviews per day (x axis: short dates, values in reviews, light and
  dark mode via Mantine colours). An empty state ("No reviews yet: study a few cards and they appear here")
  replaces the chart when every day is zero. A visually hidden `<table>` lists date and count as the
  accessible alternative (the chart is `aria-hidden`).
- **Your cards:** one table with a row per type (kana, kanji, vocabulary) and columns total, learning, review,
  relearning; "cards" means the item and direction pairs the API counts.
- **Progress by level:** for kanji and vocabulary (kana has no level), rows N5 to N1: a two-tone progress bar
  (cards in Review, then introduced but not yet in Review, of the level's total) with the numbers beside it
  ("120 in review, 340 of 667 introduced"), so the bar is never the only carrier. Levels with a total of zero
  are omitted.

## Settings screen

Data: `GET /settings` (`ReviewSettings`) fills the form; `PUT /settings` replaces the whole document. Query key
`['settings']`.

- **New cards:** the policy as three radio cards with a one-line explanation (Strict order: finish a level
  before the next starts; Mastery unlock: the next level also waits until enough of the current level is in
  Review; Pinned levels: only the levels you pick). Below it, the daily new-card limits for kana, kanji and
  vocabulary (integers 0 to 10,000; "0 means unlimited" under the fields).
- **Levels:** active levels as chips N5 to N1 (at least one must stay selected, always, because the API
  requires it) and the mastery threshold as a percentage (0 to 100). Each is disabled with a hint under the
  policies that do not use it.
- **Scheduling:** target retention as a slider from 70% to 99% (step 1) with the value shown; stored as the
  fraction the API expects (0.90).
- **Study day:** the rollover hour (0 to 23, shown as "4:00") with a note that it is read in the server's
  timezone (the `TZ` setting).
- **Buttons:** **Save** (disabled while the form is unchanged or a request is in flight) and **Reset to
  recommended values** (refills the form; you still press Save). "Recommended values" are a single constant
  in `settingsForm.ts` mirroring the backend defaults (strict order; limits 20, 15, 20; retention 0.90;
  rollover 4; levels N5; threshold 0.80), because the API does not expose its defaults; a test pins the
  constant against the API's declared defaults in the OpenAPI snapshot.
- **Validation:** the API's constraints in the browser. A server 422 is mapped onto fields with the existing
  `ApiError.fieldErrors` (keyed by the last string of the error location, so `new_limits.kana` is the field
  `kana`); anything that does not map goes into a general alert. A network or 5xx failure keeps the edits and
  offers Try again (the same `PUT` body).
- **After a successful save:** a "Settings saved" toast, the form is reset to the server's response (so it is
  clean again), the `['settings']` cache is updated, and the review and stats queries are invalidated so the
  dashboard and statistics show the new limits at once. The new settings apply from the next card.
- **Accessibility:** every control has a label and its help text is associated with it
  (`aria-describedby`); the slider has an accessible value text; disabled fields keep their hint visible;
  errors are announced through the form's own field errors (no ticking live regions).

## Delivery

- **Dependencies:** `@mantine/charts` (matching the installed `@mantine/core` version) and `recharts`,
  installed with `@latest`, resolved versions recorded in the PR. Verified against React 19 and jsdom before
  the plan is written. `@mantine/charts/styles.css` is imported where the chart lives, so it ships in the
  stats chunk.
- **Bundle:** `/stats` and `/settings` are `React.lazy` routes under the existing Suspense. The main chunk must
  not grow; the stats chunk size (recharts) is reported in the PR; the build must still show no "larger than
  500 kB" warning (no raised limit).
- **Backend:** no change; `frontend/openapi.json` and `schema.d.ts` are unchanged (a drift check confirms).
- **Docs:** README (the Statistics and Settings paragraph), CHANGELOG, TODO (tick the Plan 2B-3 item, keep the
  new follow-ups) and an "Implementation notes" section on this spec.

## Testing

Vitest, React Testing Library and MSW at the network layer; fake timers only if needed.

- **Stats:** loading, error with retry, 503 with the Build link, and data states; the hidden table matches the
  API numbers; the retention percentage and its null case; the empty-chart state; per-level rows (zero-total
  levels omitted, numbers beside the bar); `by_type` table. The chart itself is smoke-tested (recharts cannot
  measure sizes in jsdom), so the numbers are asserted through the accessible table.
- **Settings:** the form fills from the API; every client validation rule and its message; a server 422 lands
  on the matching fields and unknown ones in the alert; the `PUT` body is exactly the edited document;
  policy-dependent fields are disabled with the hint but still saved; Reset only fills the form; Save is
  disabled until something changes and while saving; a network error keeps the edits and Try again re-sends
  the identical request; a successful save shows the toast, cleans the form and invalidates the review and
  stats queries; the recommended-values constant equals the OpenAPI defaults.
- **Wiring:** the new navigation links, the lazy routes (deep links to `/stats` and `/settings` after login),
  the link from the "done for now" screen; existing tests keep passing.
- The coverage gate stays at 80% on all four metrics.

## Order of work

One branch (`feat/plan-2b3-stats-settings`), draft PR opened early, no stacked PRs.

1. Add `@mantine/charts` and `recharts`; the stats and settings endpoints, query keys, hooks and fixtures.
2. The statistics screen.
3. The settings screen.
4. Wiring: navigation links, lazy routes, the done-screen link, cache invalidation after a save, bundle check.
5. Docs, whole-branch verification (frontend gate, Python gate, drift check, smoke test) and the final review.

## Risks

- **recharts in jsdom:** it needs a measured container, so the chart is only smoke-tested and the numbers are
  asserted through the hidden table; a `ResizeObserver` polyfill is already part of the test setup.
- **Bundle size:** recharts is large; it is confined to the stats chunk and its size is reported.
- **Defaults duplication:** the recommended values duplicate the backend defaults; one constant plus a test
  against the OpenAPI snapshot keeps them honest.
- **422 field names:** the error helper keys messages by the last string in the location, which is enough for
  every field here (`kana`, `kanji`, `vocab` under `new_limits`, and the top-level names); an error on an
  array element (an integer last location) falls into the general alert.
- **Browser verification:** the authenticated screens cannot be checked in a browser by the assistant
  (credentials are not typed into login forms); the PR lists what to eyeball: the chart, the slider, the
  policy cards, dark mode and the mobile layout.
