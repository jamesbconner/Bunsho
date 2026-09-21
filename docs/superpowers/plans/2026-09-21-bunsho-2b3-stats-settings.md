# Bunshō Plan 2B-3: Statistics and Settings Screens Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the web UI with a statistics screen (today's numbers, a 30-day chart, cards by state, progress by level) and a settings screen (one form over all review settings), both lazy-loaded, linked from the navigation, with the review screen's "done for now" state linking to Settings.

**Architecture:** No backend change. The frontend gains typed wrappers for `GET /stats/summary`, `GET /settings` and `PUT /settings`, query hooks under their own keys, a `StatsPage` built from small presentational parts (the 30-day bar chart is a Mantine Charts `BarChart` with a visually hidden table as its accessible twin), and a `SettingsPage` whose `SettingsForm` is seeded once from the saved document and edited with `@mantine/form` (client validation mirrors the API's ranges; a server 422 is placed on the matching fields; a save updates the cache and marks the review and statistics queries stale).

**Tech Stack:** Same as Plan 2B-2 plus `@mantine/charts` 9.6.1 and `recharts` 3.10.1 (the two new dependencies, resolved on 2026-09-21; see "Version notes").

**Spec:** `docs/superpowers/specs/2026-09-21-bunsho-2b3-stats-settings-design.md` (parents: `2026-09-20-bunsho-2a-review-engine-design.md`, `2026-09-20-bunsho-2b2-study-loop-design.md`). Read it before starting.

## Global Constraints

Every task's requirements include this section.

- **Latest stable versions of every library and tool** (James): the only dependency change in this plan is adding `@mantine/charts` and `recharts` with `@latest` (Task 1); record the resolved versions in the PR. `@mantine/charts` must be the same version as the installed `@mantine/core` (9.6.1 today). The one standing exception is unchanged: TypeScript is pinned to 6.0.3 (with the npm `overrides` entry) and `@types/node` to the 24 line.
- Frontend: strict TypeScript (`strict`, `noUncheckedIndexedAccess`, `erasableSyntaxOnly`: no enums, no parameter properties, no namespaces; use `import type`); ESLint (flat config, `recommendedTypeChecked`, `react-hooks`, `react-refresh`) with zero errors and **no new `eslint-disable` comments**; Prettier (`singleQuote`, `printWidth: 100`, `trailingComma: all`) with `format:check` clean; coverage gate 80% (lines, functions, branches, statements).
- Hand-written API types are forbidden: every request/response type comes from `src/api/schema.d.ts` (generated from `frontend/openapi.json`). This plan does not change the backend, `frontend/openapi.json` or `schema.d.ts`.
- All UI text is English; every Japanese text run carries `lang="ja"` (this plan adds none); the HTML root is `lang="en"`.
- Tokens (access or refresh) are never put in URLs, logs, query keys or the query cache. The refresh token is stored only under `localStorage` key `bunsho.refresh_token`.
- Live regions announce static text only (nothing that changes every second); form errors are shown through the form's own field errors.
- Port `8192` for the API (never `8000`).
- Commits: conventional commits, stage explicit paths only (never `git add .` / `-A`), trailer as its own paragraph: `git commit -m "<subject>" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"`. Never stage `.gitignore` (the repo-root one is user-owned), `.python-version`, `.superpowers/`. Never merge to `main`; James merges.
- Windows / Git Bash quirks: run `unset VIRTUAL_ENV` before `uv`; quote paths (`Bunshō` contains ō); prefer the Write tool over shell heredocs for files (heredocs containing apostrophes can fail to parse in this shell). The repo-root `.gitignore` ignores any directory named `build/`, `lib/`, `env/`, `var/`, `parts/` or `downloads/`: this plan creates none, but check that `git status` shows every new file you expect before committing.
- Verification commands. Frontend (`frontend/`): `npm run format:check && npm run lint && npm run build && npm run coverage`. Backend (repo root, only in Task 5): `uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run bandit -c pyproject.toml -r src -q && uv run pytest -q`.

## Version notes (resolved 2026-09-21)

`@mantine/charts` 9.6.1 (peer dependencies `@mantine/core` and `@mantine/hooks` 9.6.1, `react ^19.2`, `recharts >=3.2.1`) and `recharts` 3.10.1 were the latest releases and installed cleanly next to React 19.3.0. If newer releases exist when this plan runs, install those, keep `@mantine/charts` equal to the installed `@mantine/core`, and report any difference from this note.

## Refinements to the spec

Decisions taken while building the verified prototype; the spec's body describes the intent, these are the details.

1. **Mantine's `NumberInput` clamps a typed value to its `min`/`max` when it loses focus** (its default `clampBehavior`), so from the keyboard the only invalid limit is an empty field; the API's range rule is still checked before sending (defence in depth, and the unit test covers it), but the page tests reach it through empty fields.
2. **Toasts and alerts both have `role="alert"`**, so tests assert on text, not on the absence of that role, once a "Settings saved" toast may be on screen.
3. **The form owns its values after it mounts** (`SettingsForm` is seeded once from `initial`), and `useSettings` does not refetch on window focus or reconnect, so a background refetch can never replace what is being typed. After a successful save the form is reset to the server's response (`setValues`, `setInitialValues`, `resetDirty`).
4. **Percentages keep their precision:** retention and the mastery threshold are edited as percentages and converted with `toFixed`, so a stored 0.905 shows as 90.5% and is sent back as 0.905 (a saved-but-untouched value is never silently rounded).
5. The retention slider's thumb is named "Target retention" (its visible label above it carries the live value); the rollover hour is a native select named "A new study day starts at".
6. `RECOMMENDED_SETTINGS` is compared with the API's declared defaults through a `?raw` import of `frontend/openapi.json` (the app's tsconfig has no `resolveJsonModule`, and `?raw` needs no Node typings).
7. The spec's order of work steps 4 and 5 are Tasks 4 and 5 here.

## Verified prototype

All frontend code below was written and run in a scratch worktree with exactly the current dependencies plus the two new packages: `tsc -b`, ESLint, Prettier, **268 tests in 31 files** (about 98.2% statement coverage), and the production build were all green (main chunk about 388.6 kB, unchanged; the statistics chunk about 410.9 kB with recharts; the settings chunk about 52.7 kB; no "larger than 500 kB" warning), and the tests of this plan passed 8 runs in a row. The code is inlined verbatim; if a command disagrees, fix the disagreement minimally and report it, never weaken a check.

## File Structure

New (all under `frontend/src/`): `features/stats/{format.ts,format.test.ts,TodayPanel.tsx,ReviewsChart.tsx,CardsByType.tsx,LevelProgress.tsx,StatsPage.tsx,StatsPage.test.tsx}`, `features/settings/{settingsForm.ts,settingsForm.test.ts,PolicyField.tsx,SettingsPage.tsx,SettingsPage.test.tsx}`.

Modified: `frontend/package.json` and `frontend/package-lock.json` (two dependencies), `api/endpoints.ts`, `api/endpoints.test.ts`, `api/queries.ts`, `api/queries.test.tsx`, `test/fixtures.ts`, `components/AppLayout.tsx`, `components/AppLayout.test.tsx`, `features/review/ReviewFinished.tsx`, `features/review/ReviewPage.test.tsx` (one assertion), `App.tsx`, `App.test.tsx`; and `README.md`, `CHANGELOG.md`, `TODO.md` plus the spec's implementation notes.

---

## Task 0: Branch and draft PR

**Files:** none.

- [ ] **Step 1: Confirm the docs PR (spec and this plan) is merged**

Run: `gh pr list --state all --limit 3`
Expected: the `docs/plan-2b3` PR shows `MERGED`. If it does not, stop and ask James (no stacked branches).

- [ ] **Step 2: Branch from a fresh main**

```bash
git checkout main && git pull
git checkout -b feat/plan-2b3-stats-settings
```

- [ ] **Step 3: Draft PR after the first commit (Task 1)**

After Task 1's commit: `git push -u origin feat/plan-2b3-stats-settings`, then `gh pr create --draft --title "Plan 2B-3: statistics and settings screens" --body "<summary>\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"`. CI then runs on every push.

---

## Task 1: Chart dependencies, endpoints, query hooks and fixtures

**Files:**
- Modify: `frontend/package.json`, `frontend/package-lock.json`, `frontend/src/api/endpoints.ts`, `frontend/src/api/queries.ts`, `frontend/src/test/fixtures.ts`, `frontend/src/api/endpoints.test.ts`, `frontend/src/api/queries.test.tsx`

**Interfaces:**
- Consumes: `request()` from `api/client.ts`; the generated types `StatsSummary`, `LevelProgress`, `ReviewSettings-Output`, `ReviewSettings-Input`, `NewCardPolicyName` from `api/schema.d.ts`; `queryKeys.reviewNext` and `useQueryClient` already in `api/queries.ts`.
- Produces: `endpoints.statsSummary()`, `endpoints.getSettings()`, `endpoints.updateSettings(settings)`; types `StatsSummary`, `LevelProgress`, `ReviewSettings`, `ReviewSettingsInput`, `NewCardPolicyName` (re-exported from `api/endpoints`); `queryKeys.statsSummary`, `queryKeys.settings`; `useStatsSummary()`, `useSettings()`, `useUpdateSettings()`; fixtures `makeSettings(overrides?)`, `makeDailyReviews()`, `makeStatsSummary(overrides?)`.

- [ ] **Step 1: Add the two dependencies**

Run (in `frontend/`): `npm install @mantine/charts@latest recharts@latest`
Expected: `package.json` gains exactly `"@mantine/charts": "^9.6.1"` under `dependencies` and `"recharts": "^3.10.1"` (a comma is added after `react-router`), `package-lock.json` is updated, and `npm ls @mantine/charts @mantine/core recharts react` shows `@mantine/charts` and `@mantine/core` on the same version and one deduped `react`. Note the resolved versions for the PR.

- [ ] **Step 2: Write the fixtures and the tests**

Replace `frontend/src/test/fixtures.ts` with:

```typescript
import type {
  BuildStatus,
  CardView,
  NextCard,
  ReviewSettings,
  RubySegment,
  StatsSummary,
} from '../api/endpoints';

export type BuildReport = NonNullable<BuildStatus['report']>;

export function makeBuildStatus(overrides: Partial<BuildStatus> = {}): BuildStatus {
  return {
    task_id: 'task-1',
    state: 'running',
    dry_run: false,
    started_at: '2026-09-20T12:00:00Z',
    finished_at: null,
    progress: { stage: 'import_deck', current: 0, total: 1 },
    report: null,
    error: null,
    ...overrides,
  };
}

export function makeReport(overrides: Partial<BuildReport> = {}): BuildReport {
  return {
    dry_run: false,
    target: '/data/content.db',
    deck_sha256: 'a'.repeat(64),
    kana_count: 208,
    kanji_count: 3088,
    unleveled_kanji_count: 979,
    vocab_count: 7734,
    sentence_count: 6775,
    vocab_by_level: { N5: 667, N4: 630, N3: 1647, N2: 1737, N1: 3053 },
    kanji_by_level: { N5: 480, N4: 352, N3: 544, N2: 357, N1: 376 },
    kanji_without_details: 12,
    duration_seconds: 31.4,
    ...overrides,
  };
}

/** A ruby segment: text with an optional reading, optionally highlighted. */
export function segment(
  base: string,
  reading: string | null = null,
  highlighted = false,
): RubySegment {
  return { base, reading, highlighted };
}

const INTERVALS = { again: 60, hard: 600, good: 86_400, easy: 345_600 };
const ZERO = { kana: 0, kanji: 0, vocab: 0 };

/** A new kana card (あ, glyph to sound). */
export function makeKanaCard(overrides: Partial<CardView> = {}): CardView {
  return {
    item_id: 'kana:あ',
    direction: 'glyph_to_sound',
    item_type: 'kana',
    is_new: true,
    state: 0,
    expected_last_review: null,
    intervals: INTERVALS,
    kana: { id: 'kana:あ', char: 'あ', romaji: 'a', script: 'hira', kind: 'basic', group: 'a' },
    kanji: null,
    vocab: null,
    ...overrides,
  };
}

/** A kanji card (日, kanji to meaning). */
export function makeKanjiCard(overrides: Partial<CardView> = {}): CardView {
  return {
    item_id: 'kanji:日',
    direction: 'kanji_to_meaning',
    item_type: 'kanji',
    is_new: false,
    state: 2,
    expected_last_review: '2026-09-19T08:00:00Z',
    intervals: INTERVALS,
    kana: null,
    kanji: {
      id: 'kanji:日',
      char: '日',
      level: 5,
      meanings: ['day', 'sun'],
      on_readings: ['ニチ', 'ジツ'],
      kun_readings: ['ひ', 'か'],
    },
    vocab: null,
    ...overrides,
  };
}

/** A vocabulary card (食べる, recognition) with an example sentence. */
export function makeVocabCard(overrides: Partial<CardView> = {}): CardView {
  return {
    item_id: 'vocab:食べる:たべる',
    direction: 'recognition',
    item_type: 'vocab',
    is_new: false,
    state: 2,
    expected_last_review: '2026-09-19T09:30:00Z',
    intervals: INTERVALS,
    kana: null,
    kanji: null,
    vocab: {
      id: 'vocab:食べる:たべる',
      expression: '食べる',
      reading: 'たべる',
      meaning: 'to eat',
      level: 5,
      part_of_speech: ['verb', 'ichidan'],
      additional_definitions: '',
      tags: [],
      reading_segments: [segment('食', 'た'), segment('べる')],
      sentence: {
        english: 'I eat breakfast every day.',
        segments: [
          segment('毎日', 'まいにち'),
          segment('朝ご飯', 'あさごはん'),
          segment('を'),
          segment('食べる', null, true),
          segment('。'),
        ],
      },
    },
    ...overrides,
  };
}

/** The `GET /reviews/next` payload around `card` (a card, or null for nothing to study). */
export function makeNextCard(card: CardView | null, overrides: Partial<NextCard> = {}): NextCard {
  return {
    card,
    counts: {
      due: card === null ? ZERO : { ...ZERO, [card.item_type]: 1 },
      new_remaining: ZERO,
    },
    next_due_at: null,
    ...overrides,
  };
}

/** The settings a fresh install starts with (the backend's defaults). */
export function makeSettings(overrides: Partial<ReviewSettings> = {}): ReviewSettings {
  return {
    new_card_policy: 'strict_order',
    new_limits: { kana: 20, kanji: 15, vocab: 20 },
    target_retention: 0.9,
    rollover_hour: 4,
    active_levels: ['N5'],
    mastery_threshold: 0.8,
    ...overrides,
  };
}

/** 30 study days ending on 2026-09-20, with reviews on some of them. */
export function makeDailyReviews(): StatsSummary['daily_reviews'] {
  return Array.from({ length: 30 }, (_, index) => {
    const day = new Date(Date.UTC(2026, 7, 22 + index)).toISOString().slice(0, 10);
    return { day, reviews: index % 3 === 0 ? 0 : index * 2 };
  });
}

/** A statistics summary for someone a few weeks into studying. */
export function makeStatsSummary(overrides: Partial<StatsSummary> = {}): StatsSummary {
  return {
    reviewed_today: 42,
    introduced_today: { kana: 5, kanji: 3, vocab: 8 },
    retention_30d: 0.8765,
    daily_reviews: makeDailyReviews(),
    by_type: {
      kana: { total: 416, learning: 10, review: 120, relearning: 2 },
      kanji: { total: 2109, learning: 30, review: 200, relearning: 5 },
      vocab: { total: 15468, learning: 60, review: 900, relearning: 12 },
    },
    by_level: [
      { item_type: 'kanji', level: 'N5', total: 960, introduced: 300, review: 180 },
      { item_type: 'kanji', level: 'N4', total: 704, introduced: 20, review: 5 },
      { item_type: 'kanji', level: 'N3', total: 0, introduced: 0, review: 0 },
      { item_type: 'vocab', level: 'N5', total: 1334, introduced: 700, review: 500 },
      { item_type: 'vocab', level: 'N4', total: 1260, introduced: 100, review: 20 },
    ],
    ...overrides,
  };
}
```

Replace `frontend/src/api/endpoints.test.ts` with:

```typescript
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { session } from '../auth/session';
import { makeSettings, makeStatsSummary } from '../test/fixtures';
import { server } from '../test/server';
import { endpoints } from './endpoints';

const TASK = {
  task_id: 'abc 123',
  state: 'running',
  dry_run: false,
  started_at: '2026-09-20T12:00:00Z',
  finished_at: null,
  progress: { stage: 'import_deck', current: 0, total: 1 },
  report: null,
  error: null,
};

describe('endpoints', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  it('reads the content summary and the environment checks', async () => {
    server.use(
      http.get('/api/v1/content/summary', () => HttpResponse.json({ built: false })),
      http.get('/api/v1/admin/config-check', () => HttpResponse.json({ ok: true, checks: [] })),
    );
    await expect(endpoints.contentSummary()).resolves.toEqual({ built: false });
    await expect(endpoints.configCheck()).resolves.toEqual({ ok: true, checks: [] });
  });

  it('starts a build with the dry-run flag in the body', async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post('/api/v1/admin/content/build', async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(TASK, { status: 202 });
      }),
    );
    await endpoints.startBuild(true);
    await endpoints.startBuild(false);
    expect(bodies).toEqual([{ dry_run: true }, { dry_run: false }]);
  });

  it('treats "no build yet" (404) as null and passes other errors on', async () => {
    server.use(
      http.get('/api/v1/admin/content/build', () =>
        HttpResponse.json({ detail: 'no build has run yet' }, { status: 404 }),
      ),
    );
    await expect(endpoints.latestBuild()).resolves.toBeNull();

    server.use(
      http.get('/api/v1/admin/content/build', () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    );
    await expect(endpoints.latestBuild()).rejects.toMatchObject({ status: 500 });
  });

  it('reads the latest build and a build by id (the id is URL-encoded)', async () => {
    let requestedPath = '';
    server.use(
      http.get('/api/v1/admin/content/build', () => HttpResponse.json(TASK)),
      http.get('/api/v1/admin/content/build/:id', ({ request }) => {
        requestedPath = new URL(request.url).pathname;
        return HttpResponse.json(TASK);
      }),
    );
    await expect(endpoints.latestBuild()).resolves.toMatchObject({ task_id: 'abc 123' });
    await endpoints.getBuild('abc 123');
    expect(requestedPath).toBe('/api/v1/admin/content/build/abc%20123');
  });
  it('asks for the next card', async () => {
    const payload = {
      card: null,
      counts: {
        due: { kana: 0, kanji: 0, vocab: 0 },
        new_remaining: { kana: 0, kanji: 0, vocab: 0 },
      },
      next_due_at: null,
    };
    server.use(http.get('/api/v1/reviews/next', () => HttpResponse.json(payload)));
    await expect(endpoints.nextReview()).resolves.toEqual(payload);
  });

  it('posts a grade exactly as given, including the opaque expected_last_review', async () => {
    const bodies: unknown[] = [];
    const counts = {
      due: { kana: 0, kanji: 1, vocab: 0 },
      new_remaining: { kana: 0, kanji: 0, vocab: 0 },
    };
    server.use(
      http.post('/api/v1/reviews/answer', async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(counts);
      }),
    );
    const answer = {
      item_id: 'kanji:日',
      direction: 'kanji_to_meaning',
      grade: 3,
      expected_last_review: '2026-09-19T08:00:00.123456Z',
      duration_ms: 4200,
    } as const;
    await expect(endpoints.answerReview(answer)).resolves.toEqual(counts);
    expect(bodies).toEqual([answer]);
  });
  it('reads the statistics summary', async () => {
    const payload = makeStatsSummary();
    server.use(http.get('/api/v1/stats/summary', () => HttpResponse.json(payload)));
    await expect(endpoints.statsSummary()).resolves.toEqual(payload);
  });

  it('reads the settings and replaces them with a PUT of the whole document', async () => {
    const bodies: unknown[] = [];
    const saved = makeSettings({ new_card_policy: 'pinned_levels', active_levels: ['N5', 'N4'] });
    server.use(
      http.get('/api/v1/settings', () => HttpResponse.json(makeSettings())),
      http.put('/api/v1/settings', async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(saved);
      }),
    );
    await expect(endpoints.getSettings()).resolves.toEqual(makeSettings());
    await expect(endpoints.updateSettings(saved)).resolves.toEqual(saved);
    expect(bodies).toEqual([saved]);
  });
});
```

Replace `frontend/src/api/queries.test.tsx` with:

```tsx
import { onlineManager, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { createTestQueryClient } from '../test/render';
import {
  makeBuildStatus,
  makeKanaCard,
  makeNextCard,
  makeSettings,
  makeStatsSummary,
} from '../test/fixtures';
import { endpoints, type NextCard } from './endpoints';
import { ApiError, NetworkError } from './errors';
import { shouldRetry } from '../queryClient';
import {
  BUILD_POLL_MS,
  buildJustFinished,
  pollInterval,
  queryKeys,
  useAnswerReview,
  useLatestBuild,
  useNextReview,
  useSettings,
  useStatsSummary,
  useUpdateSettings,
} from './queries';

describe('pollInterval', () => {
  it('polls only while a build runs and the live stream is not connected', () => {
    const running = makeBuildStatus({ state: 'running' });
    expect(pollInterval(running, false)).toBe(BUILD_POLL_MS);
    expect(pollInterval(running, true)).toBe(false);
  });

  it('never polls a finished build, no build, or an unknown state', () => {
    expect(pollInterval(makeBuildStatus({ state: 'succeeded' }), false)).toBe(false);
    expect(pollInterval(makeBuildStatus({ state: 'failed' }), false)).toBe(false);
    expect(pollInterval(null, false)).toBe(false);
    expect(pollInterval(undefined, false)).toBe(false);
  });
});

describe('buildJustFinished', () => {
  const running = makeBuildStatus();
  const succeeded = makeBuildStatus({ state: 'succeeded' });

  it('is true when a running build finished, or a newer build finished', () => {
    expect(buildJustFinished(running, succeeded)).toBe(true);
    expect(buildJustFinished(succeeded, makeBuildStatus({ task_id: 'new', state: 'failed' }))).toBe(
      true,
    );
  });

  it('is false for the first load, an unchanged finished build, or a build still running', () => {
    expect(buildJustFinished(undefined, succeeded)).toBe(false);
    expect(buildJustFinished(null, succeeded)).toBe(false);
    expect(buildJustFinished(succeeded, succeeded)).toBe(false);
    expect(buildJustFinished(running, running)).toBe(false);
    expect(buildJustFinished(running, null)).toBe(false);
  });
});

describe('useLatestBuild', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  function setup(queryClient: QueryClient) {
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    const invalidated = () => invalidate.mock.calls.map((call) => call[0]?.queryKey);
    return { wrapper, invalidated };
  }

  it('refreshes the summary and the checks once when a polled build finished', async () => {
    const queryClient = createTestQueryClient();
    queryClient.setQueryData(queryKeys.latestBuild, makeBuildStatus());
    const latest = vi
      .spyOn(endpoints, 'latestBuild')
      .mockResolvedValue(makeBuildStatus({ state: 'succeeded' }));
    const { wrapper, invalidated } = setup(queryClient);

    const { result } = renderHook(() => useLatestBuild(false), { wrapper });
    await waitFor(() => {
      expect(result.current.data?.state).toBe('succeeded');
    });
    expect(invalidated()).toEqual([queryKeys.contentSummary, queryKeys.configCheck]);

    // Fetching the same finished build again is not a new completion.
    await queryClient.refetchQueries({ queryKey: queryKeys.latestBuild });
    expect(latest).toHaveBeenCalledTimes(2);
    expect(invalidated()).toEqual([queryKeys.contentSummary, queryKeys.configCheck]);
  });

  it('invalidates nothing on the first load of a finished build', async () => {
    const queryClient = createTestQueryClient();
    vi.spyOn(endpoints, 'latestBuild').mockResolvedValue(makeBuildStatus({ state: 'succeeded' }));
    const { wrapper, invalidated } = setup(queryClient);

    const { result } = renderHook(() => useLatestBuild(false), { wrapper });
    await waitFor(() => {
      expect(result.current.data?.state).toBe('succeeded');
    });
    expect(invalidated()).toEqual([]);
  });
});

function wrapperFor(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('useNextReview', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('loads the next card under the review key', async () => {
    const payload = makeNextCard(makeKanaCard());
    vi.spyOn(endpoints, 'nextReview').mockResolvedValue(payload);
    const queryClient = createTestQueryClient();
    const { result } = renderHook(() => useNextReview(), { wrapper: wrapperFor(queryClient) });
    await waitFor(() => {
      expect(result.current.data).toEqual(payload);
    });
    expect(queryClient.getQueryData(queryKeys.reviewNext)).toEqual(payload);
  });
});

describe('useNextReview retries and refetching', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  // The application's retry policy, with the delay removed so the test stays fast.
  function appLikeClient(): QueryClient {
    return new QueryClient({
      defaultOptions: { queries: { retry: shouldRetry, retryDelay: 0, staleTime: 30_000 } },
    });
  }

  it('asks once when the content is not built (503) instead of retrying', async () => {
    const fetchNext = vi
      .spyOn(endpoints, 'nextReview')
      .mockRejectedValue(new ApiError(503, 'content is not built'));
    const { result } = renderHook(() => useNextReview(), {
      wrapper: wrapperFor(appLikeClient()),
    });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(fetchNext).toHaveBeenCalledTimes(1);
  });

  it('still retries other server errors and connection failures, twice at most', async () => {
    const fetchNext = vi
      .spyOn(endpoints, 'nextReview')
      .mockRejectedValueOnce(new ApiError(500, 'boom'))
      .mockRejectedValueOnce(new NetworkError())
      .mockRejectedValue(new ApiError(500, 'boom'));
    const { result } = renderHook(() => useNextReview(), {
      wrapper: wrapperFor(appLikeClient()),
    });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(fetchNext).toHaveBeenCalledTimes(3);
  });

  it('does not refetch when the connection comes back', async () => {
    const fetchNext = vi.spyOn(endpoints, 'nextReview').mockResolvedValue(makeNextCard(null));
    const { result } = renderHook(() => useNextReview(), {
      wrapper: wrapperFor(createTestQueryClient()),
    });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    onlineManager.setOnline(false);
    onlineManager.setOnline(true);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(fetchNext).toHaveBeenCalledTimes(1);
  });
});

describe('useAnswerReview', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('caches the fresh counts at once and stays pending until the next card arrives', async () => {
    const before = makeNextCard(makeKanaCard());
    const after = makeNextCard(null);
    const counts = { ...before.counts, due: { kana: 5, kanji: 0, vocab: 0 } };
    vi.spyOn(endpoints, 'answerReview').mockResolvedValue(counts);
    const fetchNext = vi.spyOn(endpoints, 'nextReview').mockResolvedValueOnce(before);
    const queryClient = createTestQueryClient();
    const next = renderHook(() => useNextReview(), { wrapper: wrapperFor(queryClient) });
    await waitFor(() => {
      expect(next.result.current.data).toEqual(before);
    });

    // From here the next-card fetch stays in flight until the test lets it settle.
    let settle: (value: NextCard) => void = () => undefined;
    fetchNext.mockClear();
    fetchNext.mockImplementation(
      () =>
        new Promise<NextCard>((resolve) => {
          settle = resolve;
        }),
    );

    const answer = renderHook(() => useAnswerReview(), { wrapper: wrapperFor(queryClient) });
    answer.result.current.mutate({
      item_id: 'kana:あ',
      direction: 'glyph_to_sound',
      grade: 3,
      expected_last_review: null,
    });
    await waitFor(() => {
      expect(fetchNext).toHaveBeenCalledTimes(1);
    });

    // The counts are already in the cache, the old card still is, and the mutation waits.
    const cached = queryClient.getQueryData<NextCard>(queryKeys.reviewNext);
    expect(cached?.counts).toEqual(counts);
    expect(cached?.card).toEqual(before.card);
    expect(answer.result.current.isPending).toBe(true);

    settle(after);
    await waitFor(() => {
      expect(answer.result.current.isSuccess).toBe(true);
    });
    expect(queryClient.getQueryData(queryKeys.reviewNext)).toEqual(after);
  });

  it('does not retry a failed answer', async () => {
    const send = vi.spyOn(endpoints, 'answerReview').mockRejectedValue(new Error('network down'));
    const queryClient = createTestQueryClient();
    const answer = renderHook(() => useAnswerReview(), { wrapper: wrapperFor(queryClient) });
    answer.result.current.mutate({
      item_id: 'kana:あ',
      direction: 'glyph_to_sound',
      grade: 3,
      expected_last_review: null,
    });
    await waitFor(() => {
      expect(answer.result.current.isError).toBe(true);
    });
    expect(send).toHaveBeenCalledTimes(1);
  });
});

describe('useStatsSummary and useSettings', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('load the statistics and the settings under their own keys', async () => {
    vi.spyOn(endpoints, 'statsSummary').mockResolvedValue(makeStatsSummary());
    vi.spyOn(endpoints, 'getSettings').mockResolvedValue(makeSettings());
    const queryClient = createTestQueryClient();
    const stats = renderHook(() => useStatsSummary(), { wrapper: wrapperFor(queryClient) });
    const settings = renderHook(() => useSettings(), { wrapper: wrapperFor(queryClient) });
    await waitFor(() => {
      expect(stats.result.current.data?.reviewed_today).toBe(42);
      expect(settings.result.current.data?.rollover_hour).toBe(4);
    });
    expect(queryClient.getQueryData(queryKeys.statsSummary)).toEqual(makeStatsSummary());
    expect(queryClient.getQueryData(queryKeys.settings)).toEqual(makeSettings());
  });
});

describe('useUpdateSettings', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('caches the saved document and marks the next card and the statistics stale', async () => {
    const saved = makeSettings({ target_retention: 0.95 });
    vi.spyOn(endpoints, 'updateSettings').mockResolvedValue(saved);
    const queryClient = createTestQueryClient();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    const { result } = renderHook(() => useUpdateSettings(), { wrapper: wrapperFor(queryClient) });

    result.current.mutate(makeSettings({ target_retention: 0.95 }));
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(queryClient.getQueryData(queryKeys.settings)).toEqual(saved);
    const keys = invalidate.mock.calls.map((call) => call[0]?.queryKey);
    expect(keys).toEqual([queryKeys.reviewNext, queryKeys.statsSummary]);
  });

  it('does not retry a failed save and leaves the cache alone', async () => {
    const send = vi.spyOn(endpoints, 'updateSettings').mockRejectedValue(new Error('down'));
    const queryClient = createTestQueryClient();
    queryClient.setQueryData(queryKeys.settings, makeSettings());
    const { result } = renderHook(() => useUpdateSettings(), { wrapper: wrapperFor(queryClient) });

    result.current.mutate(makeSettings({ rollover_hour: 6 }));
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(send).toHaveBeenCalledTimes(1);
    expect(queryClient.getQueryData(queryKeys.settings)).toEqual(makeSettings());
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run (in `frontend/`): `npx vitest run src/api`
Expected: FAIL (`endpoints.statsSummary is not a function`, `useStatsSummary` is not exported, and similar).

- [ ] **Step 4: Write the implementation**

Replace `frontend/src/api/endpoints.ts` with:

```typescript
import { request } from './client';
import { ApiError } from './errors';
import type { components } from './schema';

type Schemas = components['schemas'];

export type ContentSummary = Schemas['ContentSummaryResponse'];
export type ConfigCheck = Schemas['ConfigCheckResponse'];
export type BuildStatus = Schemas['BuildStatusResponse'];
export type NextCard = Schemas['NextCard'];
export type CardView = Schemas['CardView'];
export type ReviewCounts = Schemas['ReviewCounts'];
export type AnswerRequest = Schemas['AnswerRequest'];
export type Grade = Schemas['Grade'];
export type GradeIntervals = Schemas['GradeIntervals'];
export type RubySegment = Schemas['RubySegment'];
export type StatsSummary = Schemas['StatsSummary'];
export type LevelProgress = Schemas['LevelProgress'];
export type ReviewSettings = Schemas['ReviewSettings-Output'];
export type ReviewSettingsInput = Schemas['ReviewSettings-Input'];
export type NewCardPolicyName = Schemas['NewCardPolicyName'];

/** Every authenticated API call the screens make, typed from the generated schema. */
export const endpoints = {
  contentSummary: () => request<ContentSummary>('/content/summary'),

  configCheck: () => request<ConfigCheck>('/admin/config-check'),

  startBuild: (dryRun: boolean) =>
    request<BuildStatus>('/admin/content/build', { method: 'POST', body: { dry_run: dryRun } }),

  /** The most recent build, or null when none has run yet (the server answers 404). */
  latestBuild: async (): Promise<BuildStatus | null> => {
    try {
      return await request<BuildStatus>('/admin/content/build');
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  },

  getBuild: (taskId: string) =>
    request<BuildStatus>(`/admin/content/build/${encodeURIComponent(taskId)}`),

  /** The next card to study (or none), with the counts and the next time something is due. */
  nextReview: () => request<NextCard>('/reviews/next'),

  /** Study statistics: today's counts, the last 30 days, retention, cards by state and level. */
  statsSummary: () => request<StatsSummary>('/stats/summary'),

  getSettings: () => request<ReviewSettings>('/settings'),

  /** Replace the whole settings document (all or nothing: a 422 changes nothing). */
  updateSettings: (settings: ReviewSettingsInput) =>
    request<ReviewSettings>('/settings', { method: 'PUT', body: settings }),

  /** Grade a card; the server answers with the fresh counts. */
  answerReview: (answer: AnswerRequest) =>
    request<ReviewCounts>('/reviews/answer', { method: 'POST', body: answer }),
};
```

Replace `frontend/src/api/queries.ts` with:

```typescript
import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';

import { endpoints, type BuildStatus, type NextCard } from './endpoints';
import { ApiError } from './errors';

/** Query keys, shared by the hooks and by the code that updates the cache from the live stream. */
export const queryKeys = {
  contentSummary: ['content', 'summary'] as const,
  configCheck: ['admin', 'config-check'] as const,
  latestBuild: ['build', 'latest'] as const,
  reviewNext: ['review', 'next'] as const,
  statsSummary: ['stats', 'summary'] as const,
  settings: ['settings'] as const,
};

/** While a build runs and the live stream is down, ask the server this often. */
export const BUILD_POLL_MS = 2_000;

export function pollInterval(
  build: BuildStatus | null | undefined,
  streamConnected: boolean,
): number | false {
  return build?.state === 'running' && !streamConnected ? BUILD_POLL_MS : false;
}

/** Whether a build has ended (succeeded or failed) rather than still running. */
export function isFinished(build: BuildStatus): boolean {
  return build.state !== 'running';
}

/**
 * Whether `next` reports a build that finished since `previous` was cached: it was running, or it
 * is a different (newer) build. Nothing cached yet is not a transition (the first load), and an
 * already finished build seen again is not either, so each completion is reported once.
 */
export function buildJustFinished(
  previous: BuildStatus | null | undefined,
  next: BuildStatus | null | undefined,
): boolean {
  if (previous == null || next == null || !isFinished(next)) return false;
  return previous.task_id !== next.task_id || !isFinished(previous);
}

/** A finished build changes the content and the environment checks: refetch what shows them. */
export function invalidateBuildDependents(queryClient: QueryClient): void {
  void queryClient.invalidateQueries({ queryKey: queryKeys.contentSummary });
  void queryClient.invalidateQueries({ queryKey: queryKeys.configCheck });
}

export function useContentSummary() {
  return useQuery({ queryKey: queryKeys.contentSummary, queryFn: endpoints.contentSummary });
}

export function useConfigCheck() {
  return useQuery({ queryKey: queryKeys.configCheck, queryFn: endpoints.configCheck });
}

/**
 * The latest build (null when none ran yet). Polls only while the live stream cannot be trusted.
 * A fetched build that finished since the cached one also refreshes what depends on the content
 * (a build can finish while the stream is down).
 */
export function useLatestBuild(streamConnected: boolean) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: queryKeys.latestBuild,
    queryFn: async () => {
      const previous = queryClient.getQueryData<BuildStatus | null>(queryKeys.latestBuild);
      const next = await endpoints.latestBuild();
      if (buildJustFinished(previous, next)) invalidateBuildDependents(queryClient);

      return next;
    },
    refetchInterval: (query) => pollInterval(query.state.data, streamConnected),
  });
}

/**
 * The next card to study, with the counts. What is due changes with the clock, so opening a screen
 * always asks the server (`staleTime: 0`); switching windows or a reconnect does not, so a card
 * never changes under the learner's hands. A 503 (content not built) is an answer, not a glitch,
 * so it is never retried and the not-built screen shows at once; any other failure follows the
 * query client's retry policy (a client without a retry function, such as the tests', never retries).
 */
export function useNextReview() {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: queryKeys.reviewNext,
    queryFn: endpoints.nextReview,
    staleTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status === 503) return false;
      const policy = queryClient.getDefaultOptions().queries?.retry;
      return typeof policy === 'function' ? policy(failureCount, error) : false;
    },
  });
}

/**
 * Grade a card. On success the fresh counts go into the cache at once and the next card is
 * fetched; the mutation stays pending until that fetch settles, so the screen never shows the card
 * that was just graded. It never retries by itself: a repeated POST would count the review twice.
 */
export function useAnswerReview() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: endpoints.answerReview,
    onSuccess: async (counts) => {
      queryClient.setQueryData<NextCard>(
        queryKeys.reviewNext,
        (previous) => previous && { ...previous, counts },
      );
      await queryClient.invalidateQueries({ queryKey: queryKeys.reviewNext });
    },
  });
}

/** Statistics are cheap to compute and change with every review: ask again whenever a screen opens. */
export function useStatsSummary() {
  return useQuery({
    queryKey: queryKeys.statsSummary,
    queryFn: endpoints.statsSummary,
    staleTime: 0,
  });
}

/**
 * The review settings. The form copies them once when it opens, so a background refetch must not
 * replace what the learner is typing: no refetch on window focus or reconnect.
 */
export function useSettings() {
  return useQuery({
    queryKey: queryKeys.settings,
    queryFn: endpoints.getSettings,
    staleTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
}

/**
 * Save the whole settings document. On success the saved document goes into the cache and what
 * depends on it (the next card, whose limits changed, and the statistics) is marked stale, so
 * the dashboard shows the new numbers when it is next opened. The mutation never retries by
 * itself.
 */
export function useUpdateSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: endpoints.updateSettings,
    onSuccess: async (saved) => {
      queryClient.setQueryData(queryKeys.settings, saved);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.reviewNext }),
        queryClient.invalidateQueries({ queryKey: queryKeys.statsSummary }),
      ]);
    },
  });
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run (in `frontend/`): `npx vitest run src/api`
Expected: PASS (5 files, 45 tests).

- [ ] **Step 6: Run the frontend gate**

Run (in `frontend/`): `npm run format:check && npm run lint && npm run build && npm run coverage`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/api/endpoints.ts frontend/src/api/endpoints.test.ts frontend/src/api/queries.ts frontend/src/api/queries.test.tsx frontend/src/test/fixtures.ts
git commit -m "feat: chart dependencies, stats and settings endpoints, hooks and fixtures" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

Then open the draft PR (Task 0, Step 3).

---

## Task 2: The statistics screen

**Files:**
- Create: `frontend/src/features/stats/format.ts`, `format.test.ts`, `TodayPanel.tsx`, `ReviewsChart.tsx`, `CardsByType.tsx`, `LevelProgress.tsx`, `StatsPage.tsx`, `StatsPage.test.tsx` (all under `frontend/src/features/stats/`)

**Interfaces:**
- Consumes: `useStatsSummary` and the `StatsSummary` type (Task 1); `formatCount` from `features/build/format.ts`; `ApiError`, `messageFor` from `api/errors.ts`; fixtures `makeStatsSummary`, `makeDailyReviews` (Task 1); `@mantine/charts` (`BarChart`, and its `styles.css`).
- Produces: `<StatsPage />` (no props; not routed until Task 4); `formatPercent(fraction)` and `formatShortDay(day)`.

- [ ] **Step 1: Write the tests**

Create `frontend/src/features/stats/format.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';

import { formatPercent, formatShortDay } from './format';

describe('formatPercent', () => {
  it.each([
    [0, '0.0%'],
    [0.8765, '87.7%'],
    [0.9, '90.0%'],
    [1, '100.0%'],
    [0.00049, '0.0%'],
  ])('formats %s as %s', (fraction, label) => {
    expect(formatPercent(fraction)).toBe(label);
  });
});

describe('formatShortDay', () => {
  it('formats a study day as month and day whatever the timezone', () => {
    expect(formatShortDay('2026-09-20')).toMatch(/Sep(tember)? 20/);
    expect(formatShortDay('2026-01-01')).toMatch(/Jan(uary)? 1/);
  });
});
```

Create `frontend/src/features/stats/StatsPage.test.tsx`:

```tsx
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it } from 'vitest';

import type { StatsSummary } from '../../api/endpoints';
import { session } from '../../auth/session';
import { makeDailyReviews, makeStatsSummary } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { StatsPage } from './StatsPage';

function serve(stats: StatsSummary) {
  server.use(http.get('/api/v1/stats/summary', () => HttpResponse.json(stats)));
}

function renderStats() {
  return renderWithProviders(
    <Routes>
      <Route path="/" element={<StatsPage />} />
      <Route path="/build" element={<p>Build page</p>} />
    </Routes>,
  );
}

describe('StatsPage', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  it('shows today, retention, the chart, the cards and the progress by level', async () => {
    serve(makeStatsSummary());
    const { container } = renderStats();

    expect(await screen.findByRole('heading', { name: 'Statistics' })).toBeInTheDocument();
    const reviewed = screen.getByText('Reviewed today').parentElement;
    expect(reviewed).toHaveTextContent('42');
    const introduced = screen.getByText('New cards today').parentElement;
    expect(introduced).toHaveTextContent('16');
    expect(introduced).toHaveTextContent('5 kana, 3 kanji, 8 vocabulary');
    const retention = screen.getByText('Retention, last 30 days').parentElement;
    expect(retention).toHaveTextContent('87.7%');

    expect(screen.getByRole('heading', { name: 'Last 30 days' })).toBeInTheDocument();
    expect(container.querySelector('.mantine-BarChart-root')).not.toBeNull();
    expect(screen.getByRole('heading', { name: 'Your cards' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Progress by level' })).toBeInTheDocument();
  });

  it('gives the numbers behind the chart in a table for screen readers', async () => {
    serve(makeStatsSummary());
    renderStats();
    const table = await screen.findByRole('table', { name: 'Reviews per day, last 30 days' });
    const rows = within(table).getAllByRole('row');
    expect(rows).toHaveLength(31);
    expect(within(rows[1] as HTMLElement).getByText('0')).toBeInTheDocument();
    expect(rows[30]).toHaveTextContent(/Sep(tember)? 20/);
    expect(rows[30]).toHaveTextContent('58');
  });

  it('says so instead of drawing an empty chart', async () => {
    serve(
      makeStatsSummary({
        daily_reviews: makeDailyReviews().map((day) => ({ ...day, reviews: 0 })),
      }),
    );
    const { container } = renderStats();
    expect(await screen.findByText(/No reviews yet/)).toBeInTheDocument();
    expect(container.querySelector('.mantine-BarChart-root')).toBeNull();
    expect(
      screen.queryByRole('table', { name: 'Reviews per day, last 30 days' }),
    ).not.toBeInTheDocument();
  });

  it('explains a missing retention figure', async () => {
    serve(makeStatsSummary({ retention_30d: null }));
    renderStats();
    const retention = (await screen.findByText('Retention, last 30 days')).parentElement;
    expect(retention).toHaveTextContent('Not enough reviews yet');
  });

  it('lists the cards of each type by state', async () => {
    serve(makeStatsSummary());
    renderStats();
    const table = await screen.findByRole('table', { name: 'Cards by type and state' });
    const kanji = within(table).getByRole('row', { name: /Kanji/ });
    expect(kanji).toHaveTextContent('2,109');
    expect(kanji).toHaveTextContent('30');
    expect(kanji).toHaveTextContent('200');
    expect(kanji).toHaveTextContent('5');
    expect(within(table).getByRole('row', { name: /Vocabulary/ })).toHaveTextContent('15,468');
    expect(within(table).getByRole('row', { name: /Kana/ })).toHaveTextContent('416');
  });

  it('shows progress per level with the numbers beside the bar and skips empty levels', async () => {
    serve(makeStatsSummary());
    renderStats();
    const kanji = await screen.findByRole('region', { name: 'Kanji progress by level' });
    expect(within(kanji).getByText('N5')).toBeInTheDocument();
    expect(within(kanji).getByText('180 in review, 300 of 960 introduced')).toBeInTheDocument();
    expect(within(kanji).getByText('5 in review, 20 of 704 introduced')).toBeInTheDocument();
    expect(within(kanji).queryByText('N3')).not.toBeInTheDocument();
    const vocab = screen.getByRole('region', { name: 'Vocabulary progress by level' });
    expect(within(vocab).getByText('500 in review, 700 of 1,334 introduced')).toBeInTheDocument();
  });

  it('leaves out a type that has no levels with cards', async () => {
    serve(makeStatsSummary({ by_level: [] }));
    renderStats();
    await screen.findByRole('heading', { name: 'Progress by level' });
    expect(screen.queryByRole('region', { name: /progress by level/ })).not.toBeInTheDocument();
  });

  it('links to the Build screen when the content is not built (503)', async () => {
    server.use(
      http.get('/api/v1/stats/summary', () =>
        HttpResponse.json({ detail: 'content is not built' }, { status: 503 }),
      ),
    );
    renderStats();
    expect(await screen.findByText('Nothing to show yet')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Build your content' })).toHaveAttribute(
      'href',
      '/build',
    );
  });

  it('explains a failed load and can try again', async () => {
    const user = userEvent.setup();
    let calls = 0;
    server.use(
      http.get('/api/v1/stats/summary', () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json({ detail: 'boom' }, { status: 500 })
          : HttpResponse.json(makeStatsSummary());
      }),
    );
    renderStats();
    expect(await screen.findByText("Couldn't load your statistics")).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('heading', { name: 'Statistics' })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (in `frontend/`): `npx vitest run src/features/stats`
Expected: FAIL (modules not found).

- [ ] **Step 3: Write the implementation**

Create `frontend/src/features/stats/format.ts`:

```typescript
/** A fraction as a percentage with one decimal: 0.8765 becomes "87.7%". */
export function formatPercent(fraction: number): string {
  return `${(Math.round(fraction * 1000) / 10).toFixed(1)}%`;
}

/** A study day ("2026-09-20") as a short label ("Sep 20"), the same in every timezone. */
export function formatShortDay(day: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${day}T00:00:00Z`));
}
```

Create `frontend/src/features/stats/TodayPanel.tsx`:

```tsx
import { Paper, SimpleGrid, Text } from '@mantine/core';

import type { StatsSummary } from '../../api/endpoints';
import { formatCount } from '../build/format';
import { formatPercent } from './format';

function Figure({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <Paper withBorder p="md">
      <Text size="sm" c="dimmed">
        {label}
      </Text>
      <Text fz={28} fw={600}>
        {value}
      </Text>
      {note !== undefined && (
        <Text size="xs" c="dimmed">
          {note}
        </Text>
      )}
    </Paper>
  );
}

/** Reviews and new cards today, and how well what you know is holding up. */
export function TodayPanel({ stats }: { stats: StatsSummary }) {
  const { introduced_today: introduced, retention_30d: retention } = stats;
  const introducedTotal = introduced.kana + introduced.kanji + introduced.vocab;
  return (
    <SimpleGrid cols={{ base: 1, sm: 3 }}>
      <Figure label="Reviewed today" value={formatCount(stats.reviewed_today)} />
      <Figure
        label="New cards today"
        value={formatCount(introducedTotal)}
        note={`${introduced.kana} kana, ${introduced.kanji} kanji, ${introduced.vocab} vocabulary`}
      />
      <Figure
        label="Retention, last 30 days"
        value={retention === null ? 'Not enough reviews yet' : formatPercent(retention)}
        note="Reviews of cards you already knew that were graded Hard or better"
      />
    </SimpleGrid>
  );
}
```

Create `frontend/src/features/stats/ReviewsChart.tsx`:

```tsx
import '@mantine/charts/styles.css';

import { BarChart } from '@mantine/charts';
import { Text, VisuallyHidden } from '@mantine/core';

import type { StatsSummary } from '../../api/endpoints';
import { formatShortDay } from './format';

/**
 * Reviews per day for the last 30 study days. The chart is decoration for sighted users
 * (`aria-hidden`); the same numbers are in a visually hidden table for everyone else.
 */
export function ReviewsChart({ days }: { days: StatsSummary['daily_reviews'] }) {
  if (days.every((day) => day.reviews === 0)) {
    return <Text c="dimmed">No reviews yet: study a few cards and they will appear here.</Text>;
  }
  const rows = days.map((day) => ({ label: formatShortDay(day.day), reviews: day.reviews }));
  return (
    <>
      <div aria-hidden="true">
        <BarChart
          h={240}
          data={rows}
          dataKey="label"
          series={[{ name: 'reviews', label: 'Reviews', color: 'indigo.6' }]}
          tickLine="y"
          withLegend={false}
        />
      </div>
      <VisuallyHidden>
        <table aria-label="Reviews per day, last 30 days">
          <thead>
            <tr>
              <th scope="col">Day</th>
              <th scope="col">Reviews</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label}>
                <th scope="row">{row.label}</th>
                <td>{row.reviews}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </VisuallyHidden>
    </>
  );
}
```

Create `frontend/src/features/stats/CardsByType.tsx`:

```tsx
import { Table } from '@mantine/core';

import type { StatsSummary } from '../../api/endpoints';
import { formatCount } from '../build/format';

const TYPES = [
  { key: 'kana', label: 'Kana' },
  { key: 'kanji', label: 'Kanji' },
  { key: 'vocab', label: 'Vocabulary' },
] as const;

/** How many cards of each type are being learned, known, or being relearned. */
export function CardsByType({ byType }: { byType: StatsSummary['by_type'] }) {
  return (
    <Table withTableBorder aria-label="Cards by type and state">
      <Table.Thead>
        <Table.Tr>
          <Table.Th>Type</Table.Th>
          <Table.Th ta="right">Total</Table.Th>
          <Table.Th ta="right">Learning</Table.Th>
          <Table.Th ta="right">Review</Table.Th>
          <Table.Th ta="right">Relearning</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {TYPES.map(({ key, label }) => {
          const row = byType[key];
          return (
            <Table.Tr key={key}>
              <Table.Td>{label}</Table.Td>
              <Table.Td ta="right">{formatCount(row?.total ?? 0)}</Table.Td>
              <Table.Td ta="right">{formatCount(row?.learning ?? 0)}</Table.Td>
              <Table.Td ta="right">{formatCount(row?.review ?? 0)}</Table.Td>
              <Table.Td ta="right">{formatCount(row?.relearning ?? 0)}</Table.Td>
            </Table.Tr>
          );
        })}
      </Table.Tbody>
    </Table>
  );
}
```

Create `frontend/src/features/stats/LevelProgress.tsx`:

```tsx
import { Group, Progress, Stack, Text, Title } from '@mantine/core';

import type { StatsSummary } from '../../api/endpoints';
import { formatCount } from '../build/format';

const TYPES = [
  { key: 'kanji', label: 'Kanji' },
  { key: 'vocab', label: 'Vocabulary' },
] as const;

/**
 * Progress through each JLPT level (kana has no levels): a two-tone bar of the cards in Review and
 * the cards introduced but not yet in Review, with the numbers beside it so the bar is never the
 * only carrier. Levels with nothing in them are left out.
 */
export function LevelProgress({ byLevel }: { byLevel: StatsSummary['by_level'] }) {
  return (
    <Stack gap="lg">
      {TYPES.map(({ key, label }) => {
        const levels = byLevel.filter((row) => row.item_type === key && row.total > 0);
        if (levels.length === 0) return null;
        return (
          <Stack key={key} gap="xs" component="section" aria-label={`${label} progress by level`}>
            <Title order={4}>{label}</Title>
            {levels.map((row) => {
              const known = (row.review / row.total) * 100;
              const learning = (Math.max(row.introduced - row.review, 0) / row.total) * 100;
              return (
                <Group key={row.level} wrap="nowrap" gap="md" align="center">
                  <Text w={36} fw={500}>
                    {row.level}
                  </Text>
                  <Progress.Root size="lg" style={{ flex: 1 }} aria-hidden="true">
                    <Progress.Section value={known} color="indigo" />
                    <Progress.Section value={learning} color="indigo.2" />
                  </Progress.Root>
                  <Text size="sm" c="dimmed" w={{ base: 130, sm: 260 }}>
                    {formatCount(row.review)} in review, {formatCount(row.introduced)} of{' '}
                    {formatCount(row.total)} introduced
                  </Text>
                </Group>
              );
            })}
          </Stack>
        );
      })}
    </Stack>
  );
}
```

Create `frontend/src/features/stats/StatsPage.tsx`:

```tsx
import { Alert, Button, Skeleton, Stack, Text, Title } from '@mantine/core';
import { Link } from 'react-router';

import { ApiError, messageFor } from '../../api/errors';
import { useStatsSummary } from '../../api/queries';
import { CardsByType } from './CardsByType';
import { LevelProgress } from './LevelProgress';
import { ReviewsChart } from './ReviewsChart';
import { TodayPanel } from './TodayPanel';

/** How you are doing: today's numbers, the last 30 days, and progress through the levels. */
export function StatsPage() {
  const stats = useStatsSummary();

  if (stats.isPending) {
    return (
      <Stack>
        <Skeleton height={32} width={220} />
        <Skeleton height={112} />
        <Skeleton height={240} />
      </Stack>
    );
  }
  if (stats.isError) {
    if (stats.error instanceof ApiError && stats.error.status === 503) {
      return (
        <Alert color="blue" title="Nothing to show yet">
          <Text size="sm">The study content has not been built yet.</Text>
          <Button component={Link} to="/build" mt="sm" size="xs">
            Build your content
          </Button>
        </Alert>
      );
    }
    return (
      <Alert color="red" title="Couldn't load your statistics">
        <Text size="sm">{messageFor(stats.error)}</Text>
        <Button
          mt="sm"
          size="xs"
          onClick={() => {
            void stats.refetch();
          }}
        >
          Try again
        </Button>
      </Alert>
    );
  }

  const data = stats.data;
  return (
    <Stack gap="xl">
      <Title order={2}>Statistics</Title>
      <TodayPanel stats={data} />
      <Stack gap="sm">
        <Title order={3}>Last 30 days</Title>
        <ReviewsChart days={data.daily_reviews} />
      </Stack>
      <Stack gap="sm">
        <Title order={3}>Your cards</Title>
        <CardsByType byType={data.by_type} />
      </Stack>
      <Stack gap="sm">
        <Title order={3}>Progress by level</Title>
        <LevelProgress byLevel={data.by_level} />
      </Stack>
    </Stack>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run (in `frontend/`): `npx vitest run src/features/stats`
Expected: PASS (2 files, 15 tests).

- [ ] **Step 5: Run the frontend gate**

Run (in `frontend/`): `npm run format:check && npm run lint && npm run build && npm run coverage`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/stats/format.ts frontend/src/features/stats/format.test.ts frontend/src/features/stats/TodayPanel.tsx frontend/src/features/stats/ReviewsChart.tsx frontend/src/features/stats/CardsByType.tsx frontend/src/features/stats/LevelProgress.tsx frontend/src/features/stats/StatsPage.tsx frontend/src/features/stats/StatsPage.test.tsx
git commit -m "feat: the statistics screen with a 30-day chart and progress by level" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 3: The settings screen

**Files:**
- Create: `frontend/src/features/settings/settingsForm.ts`, `settingsForm.test.ts`, `PolicyField.tsx`, `SettingsPage.tsx`, `SettingsPage.test.tsx` (all under `frontend/src/features/settings/`)

**Interfaces:**
- Consumes: `useSettings`, `useUpdateSettings`, the types `ReviewSettings`, `ReviewSettingsInput`, `NewCardPolicyName` (Task 1); `ApiError` (with `fieldErrors`) and `messageFor` from `api/errors.ts`; `@mantine/form` (`useForm`), Mantine `notifications`; fixture `makeSettings` (Task 1); `frontend/openapi.json` (read through `?raw` in a test).
- Produces: `<SettingsPage />` (no props; not routed until Task 4); `LEVELS`, `Level`, `SettingsFormValues`, `RECOMMENDED_SETTINGS`, `POLICIES`, `toFormValues`, `toRequest`, `validateSettings`, `placeServerErrors`; `<PolicyField value onChange error? />`.

- [ ] **Step 1: Write the tests**

Create `frontend/src/features/settings/settingsForm.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';

import { ApiError } from '../../api/errors';
import openapi from '../../../openapi.json?raw';
import { makeSettings } from '../../test/fixtures';
import {
  RECOMMENDED_SETTINGS,
  placeServerErrors,
  toFormValues,
  toRequest,
  validateSettings,
  type SettingsFormValues,
} from './settingsForm';

const VALID = toFormValues(makeSettings());

function withValues(overrides: Partial<SettingsFormValues>): SettingsFormValues {
  return { ...VALID, ...overrides };
}

describe('toFormValues and toRequest', () => {
  it('turns fractions into whole percentages and back without noise', () => {
    const values = toFormValues(makeSettings({ target_retention: 0.9, mastery_threshold: 0.8 }));
    expect(values.target_retention_percent).toBe(90);
    expect(values.mastery_threshold_percent).toBe(80);
    const request = toRequest(values);
    expect(request.target_retention).toBe(0.9);
    expect(request.mastery_threshold).toBe(0.8);
  });

  it('keeps a retention that is not a whole percent as it was', () => {
    const settings = makeSettings({ target_retention: 0.905 });
    expect(toFormValues(settings).target_retention_percent).toBe(90.5);
    expect(toRequest(toFormValues(settings)).target_retention).toBe(0.905);
  });

  it('round-trips a whole document unchanged', () => {
    const settings = makeSettings({
      new_card_policy: 'pinned_levels',
      new_limits: { kana: 0, kanji: 7, vocab: 10_000 },
      rollover_hour: 23,
      active_levels: ['N5', 'N3'],
    });
    expect(toRequest(toFormValues(settings))).toEqual(settings);
  });

  it('sends numbers as numbers and levels in study order', () => {
    const request = toRequest(
      withValues({
        new_limits: { kana: '25', kanji: 15, vocab: '0' },
        active_levels: ['N1', 'N5', 'N3'],
        mastery_threshold_percent: '65',
      }),
    );
    expect(request.new_limits).toEqual({ kana: 25, kanji: 15, vocab: 0 });
    expect(request.active_levels).toEqual(['N5', 'N3', 'N1']);
    expect(request.mastery_threshold).toBe(0.65);
  });
});

describe('validateSettings', () => {
  it('accepts the recommended values and the edges of every range', () => {
    expect(validateSettings(VALID)).toEqual({});
    expect(
      validateSettings(
        withValues({
          new_limits: { kana: 0, kanji: 10_000, vocab: '0' },
          target_retention_percent: 70,
          rollover_hour: 23,
          mastery_threshold_percent: 100,
        }),
      ),
    ).toEqual({});
    expect(
      validateSettings(withValues({ target_retention_percent: 99, rollover_hour: 0 })),
    ).toEqual({});
  });

  const invalid: [string, Partial<SettingsFormValues>, string][] = [
    ['a cleared limit', { new_limits: { kana: '', kanji: 15, vocab: 20 } }, 'new_limits.kana'],
    ['a negative limit', { new_limits: { kana: 20, kanji: -1, vocab: 20 } }, 'new_limits.kanji'],
    [
      'a limit over 10,000',
      { new_limits: { kana: 20, kanji: 15, vocab: 10_001 } },
      'new_limits.vocab',
    ],
    ['a fractional limit', { new_limits: { kana: 2.5, kanji: 15, vocab: 20 } }, 'new_limits.kana'],
    ['retention below 70%', { target_retention_percent: 69 }, 'target_retention_percent'],
    ['retention above 99%', { target_retention_percent: 100 }, 'target_retention_percent'],
    ['a rollover hour of 24', { rollover_hour: 24 }, 'rollover_hour'],
    ['no levels', { active_levels: [] }, 'active_levels'],
    ['a cleared threshold', { mastery_threshold_percent: '' }, 'mastery_threshold_percent'],
    ['a threshold over 100%', { mastery_threshold_percent: 101 }, 'mastery_threshold_percent'],
  ];

  it.each(invalid)('rejects %s', (_name, overrides, field) => {
    const errors = validateSettings(withValues(overrides));
    expect(Object.keys(errors)).toEqual([field]);
  });

  it('reports every problem at once', () => {
    const errors = validateSettings(
      withValues({ new_limits: { kana: '', kanji: '', vocab: 20 }, active_levels: [] }),
    );
    expect(Object.keys(errors).sort()).toEqual([
      'active_levels',
      'new_limits.kana',
      'new_limits.kanji',
    ]);
  });
});

describe('placeServerErrors', () => {
  it('puts the server messages on the matching fields', () => {
    const placed = placeServerErrors(
      new ApiError(422, 'Request failed', {
        kana: 'Input should be less than or equal to 10000',
        target_retention: 'Input should be greater than or equal to 0.7',
        mastery_threshold: 'Input should be less than or equal to 1',
        rollover_hour: 'Input should be less than or equal to 23',
        active_levels: 'List should have at least 1 item',
        new_card_policy: 'Input should be a valid policy',
        kanji: 'bad',
        vocab: 'bad',
      }),
    );
    expect(placed.fields).toEqual({
      'new_limits.kana': 'Input should be less than or equal to 10000',
      target_retention_percent: 'Input should be greater than or equal to 0.7',
      mastery_threshold_percent: 'Input should be less than or equal to 1',
      rollover_hour: 'Input should be less than or equal to 23',
      active_levels: 'List should have at least 1 item',
      new_card_policy: 'Input should be a valid policy',
      'new_limits.kanji': 'bad',
      'new_limits.vocab': 'bad',
    });
    expect(placed.general).toBeNull();
  });

  it('keeps messages for unknown fields for the general alert', () => {
    const placed = placeServerErrors(
      new ApiError(422, 'Request failed', { kana: 'too big', surprise: 'unexpected field' }),
    );
    expect(placed.fields).toEqual({ 'new_limits.kana': 'too big' });
    expect(placed.general).toBe('surprise: unexpected field');
  });

  it('says something when a 422 carries no field messages at all', () => {
    const placed = placeServerErrors(new ApiError(422, 'Request failed'));
    expect(placed.fields).toEqual({});
    expect(placed.general).toBe('The server did not accept these settings.');
  });
});

interface Schema {
  properties: Record<string, { default?: unknown; enum?: unknown[] }>;
}

describe('RECOMMENDED_SETTINGS', () => {
  const schemas = (JSON.parse(openapi) as { components: { schemas: Record<string, Schema> } })
    .components.schemas;
  const settings = schemas['ReviewSettings-Input']?.properties ?? {};
  const limits = schemas['NewLimits-Input']?.properties ?? {};

  it('matches the defaults the API declares', () => {
    expect(RECOMMENDED_SETTINGS.new_card_policy).toBe(settings.new_card_policy?.default);
    expect(RECOMMENDED_SETTINGS.target_retention).toBe(settings.target_retention?.default);
    expect(RECOMMENDED_SETTINGS.rollover_hour).toBe(settings.rollover_hour?.default);
    expect(RECOMMENDED_SETTINGS.mastery_threshold).toBe(settings.mastery_threshold?.default);
    expect(RECOMMENDED_SETTINGS.new_limits.kana).toBe(limits.kana?.default);
    expect(RECOMMENDED_SETTINGS.new_limits.kanji).toBe(limits.kanji?.default);
    expect(RECOMMENDED_SETTINGS.new_limits.vocab).toBe(limits.vocab?.default);
  });

  it('is a document the API would accept', () => {
    expect(validateSettings(toFormValues(RECOMMENDED_SETTINGS))).toEqual({});
    expect(RECOMMENDED_SETTINGS.active_levels).toEqual(['N5']);
  });
});
```

Create `frontend/src/features/settings/SettingsPage.test.tsx`:

```tsx
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ReviewSettings } from '../../api/endpoints';
import { session } from '../../auth/session';
import { makeSettings } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { SettingsPage } from './SettingsPage';

/** Serve the settings and record every PUT body; the server echoes the document it was sent. */
function serveSettings(initial: ReviewSettings = makeSettings()) {
  const puts: unknown[] = [];
  server.use(
    http.get('/api/v1/settings', () => HttpResponse.json(initial)),
    http.put('/api/v1/settings', async ({ request }) => {
      const body = await request.json();
      puts.push(body);
      return HttpResponse.json(body);
    }),
  );
  return puts;
}

async function openSettings() {
  const view = renderWithProviders(<SettingsPage />);
  await screen.findByRole('button', { name: 'Save' });
  return view;
}

async function setNumber(user: ReturnType<typeof userEvent.setup>, name: string, value: string) {
  const input = screen.getByRole('textbox', { name });
  await user.clear(input);
  if (value !== '') await user.type(input, value);
}

describe('SettingsPage', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  it('fills the form from the saved settings', async () => {
    serveSettings(
      makeSettings({
        new_card_policy: 'mastery_unlock',
        new_limits: { kana: 5, kanji: 6, vocab: 7 },
        target_retention: 0.85,
        rollover_hour: 6,
        active_levels: ['N5', 'N4'],
        mastery_threshold: 0.65,
      }),
    );
    await openSettings();

    expect(screen.getByRole('radio', { name: /Mastery unlock/ })).toBeChecked();
    expect(screen.getByRole('textbox', { name: 'Kana per day' })).toHaveValue('5');
    expect(screen.getByRole('textbox', { name: 'Kanji per day' })).toHaveValue('6');
    expect(screen.getByRole('textbox', { name: 'Vocabulary per day' })).toHaveValue('7');
    expect(screen.getByRole('slider', { name: 'Target retention' })).toHaveAttribute(
      'aria-valuenow',
      '85',
    );
    expect(screen.getByRole('combobox', { name: /A new study day starts at/ })).toHaveValue('6');
    expect(screen.getByRole('checkbox', { name: 'N5' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'N4' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'N3' })).not.toBeChecked();
    expect(screen.getByRole('textbox', { name: /Mastery needed/ })).toHaveValue('65%');
  });

  it('keeps Save disabled until something changes, and says when there are unsaved changes', async () => {
    const user = userEvent.setup();
    serveSettings();
    await openSettings();
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument();

    await setNumber(user, 'Kana per day', '30');
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
  });

  it('saves the whole edited document, then shows a toast and a clean form', async () => {
    const user = userEvent.setup();
    const puts = serveSettings();
    await openSettings();

    await setNumber(user, 'Kana per day', '30');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('Settings saved')).toBeInTheDocument();
    expect(puts).toEqual([makeSettings({ new_limits: { kana: 30, kanji: 15, vocab: 20 } })]);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    });
    expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Kana per day' })).toHaveValue('30');
  });

  it('sends a changed slider, select and levels as the API expects them', async () => {
    const user = userEvent.setup();
    const puts = serveSettings();
    await openSettings();

    await user.click(screen.getByRole('radio', { name: /Pinned levels/ }));
    await user.click(screen.getByRole('checkbox', { name: 'N4' }));
    await user.selectOptions(
      screen.getByRole('combobox', { name: /A new study day starts at/ }),
      '6:00',
    );
    screen.getByRole('slider', { name: 'Target retention' }).focus();
    await user.keyboard('{ArrowRight}{ArrowRight}');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await screen.findByText('Settings saved');
    expect(puts).toEqual([
      makeSettings({
        new_card_policy: 'pinned_levels',
        active_levels: ['N5', 'N4'],
        rollover_hour: 6,
        target_retention: 0.92,
      }),
    ]);
  });

  it('shows the API rules as messages and sends nothing while a field is wrong', async () => {
    const user = userEvent.setup();
    const puts = serveSettings();
    await openSettings();

    await setNumber(user, 'Kana per day', '');
    await setNumber(user, 'Kanji per day', '');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    const message = 'Enter a whole number from 0 to 10,000.';
    expect(await screen.findAllByText(message)).toHaveLength(2);
    expect(puts).toEqual([]);
  });

  it('needs at least one level even when the policy does not use them', async () => {
    const user = userEvent.setup();
    const puts = serveSettings();
    await openSettings();
    await user.click(screen.getByRole('radio', { name: /Pinned levels/ }));
    await user.click(screen.getByRole('checkbox', { name: 'N5' }));
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('Pick at least one level.')).toBeInTheDocument();
    expect(puts).toEqual([]);
  });

  it('enables the levels and the mastery threshold only for the policies that use them', async () => {
    const user = userEvent.setup();
    serveSettings();
    await openSettings();
    const chip = () => screen.getByRole('checkbox', { name: 'N4' });
    const mastery = () => screen.getByRole('textbox', { name: /Mastery needed/ });

    expect(chip()).toBeDisabled();
    expect(mastery()).toBeDisabled();
    expect(screen.getByText('Only used by "Pinned levels".')).toBeInTheDocument();
    expect(screen.getByText('Only used by "Mastery unlock".')).toBeInTheDocument();

    await user.click(screen.getByRole('radio', { name: /Pinned levels/ }));
    expect(chip()).toBeEnabled();
    expect(mastery()).toBeDisabled();

    await user.click(screen.getByRole('radio', { name: /Mastery unlock/ }));
    expect(chip()).toBeDisabled();
    expect(mastery()).toBeEnabled();
  });

  it('still saves the values of fields the chosen policy does not use', async () => {
    const user = userEvent.setup();
    const puts = serveSettings(
      makeSettings({ active_levels: ['N5', 'N3'], mastery_threshold: 0.7 }),
    );
    await openSettings();
    await setNumber(user, 'Kana per day', '21');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    await screen.findByText('Settings saved');
    expect(puts).toEqual([
      makeSettings({
        new_limits: { kana: 21, kanji: 15, vocab: 20 },
        active_levels: ['N5', 'N3'],
        mastery_threshold: 0.7,
      }),
    ]);
  });

  it('puts a server 422 on the matching fields and the rest in an alert', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('/api/v1/settings', () => HttpResponse.json(makeSettings())),
      http.put('/api/v1/settings', () =>
        HttpResponse.json(
          {
            detail: [
              {
                loc: ['body', 'new_limits', 'kana'],
                msg: 'Input should be at most 10000',
                type: 'x',
              },
              { loc: ['body', 'surprise'], msg: 'Extra inputs are not permitted', type: 'y' },
            ],
          },
          { status: 422 },
        ),
      ),
    );
    await openSettings();
    await setNumber(user, 'Kana per day', '30');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('Input should be at most 10000')).toBeInTheDocument();
    const alert = screen.getByRole('alert');
    expect(within(alert).getByText("Couldn't save your settings")).toBeInTheDocument();
    expect(within(alert).getByText('surprise: Extra inputs are not permitted')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Kana per day' })).toHaveValue('30');
  });

  it('keeps the edits after a network failure and re-sends the identical request on Try again', async () => {
    const user = userEvent.setup();
    const bodies: Record<string, unknown>[] = [];
    let calls = 0;
    server.use(
      http.get('/api/v1/settings', () => HttpResponse.json(makeSettings())),
      http.put('/api/v1/settings', async ({ request }) => {
        bodies.push((await request.json()) as Record<string, unknown>);
        calls += 1;
        return calls === 1 ? HttpResponse.error() : HttpResponse.json(bodies[0]);
      }),
    );
    await openSettings();
    await setNumber(user, 'Kana per day', '30');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText("Couldn't save your settings")).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Kana per day' })).toHaveValue('30');
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();

    await user.click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Settings saved')).toBeInTheDocument();
    expect(bodies).toHaveLength(2);
    expect(bodies[1]).toEqual(bodies[0]);
    expect(screen.queryByText("Couldn't save your settings")).not.toBeInTheDocument();
  });

  it('refills the form with the recommended values without saving them', async () => {
    const user = userEvent.setup();
    const puts = serveSettings(
      makeSettings({
        new_card_policy: 'pinned_levels',
        new_limits: { kana: 50, kanji: 40, vocab: 30 },
        target_retention: 0.8,
        rollover_hour: 9,
        active_levels: ['N3'],
        mastery_threshold: 0.5,
      }),
    );
    await openSettings();
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();

    await user.click(screen.getByRole('button', { name: 'Reset to recommended values' }));

    expect(screen.getByRole('radio', { name: /Strict order/ })).toBeChecked();
    expect(screen.getByRole('textbox', { name: 'Kana per day' })).toHaveValue('20');
    expect(screen.getByRole('textbox', { name: 'Kanji per day' })).toHaveValue('15');
    expect(screen.getByRole('textbox', { name: 'Vocabulary per day' })).toHaveValue('20');
    expect(screen.getByRole('slider', { name: 'Target retention' })).toHaveAttribute(
      'aria-valuenow',
      '90',
    );
    expect(screen.getByRole('combobox', { name: /A new study day starts at/ })).toHaveValue('4');
    expect(screen.getByRole('checkbox', { name: 'N5' })).toBeChecked();
    expect(puts).toEqual([]);
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
  });

  it('marks the next card and the statistics stale after a save', async () => {
    const user = userEvent.setup();
    serveSettings();
    const { queryClient } = await openSettings();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    await setNumber(user, 'Kana per day', '30');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    await screen.findByText('Settings saved');
    const keys = invalidate.mock.calls.map((call) => call[0]?.queryKey);
    expect(keys).toEqual([
      ['review', 'next'],
      ['stats', 'summary'],
    ]);
  });

  it('explains a failed load and can try again', async () => {
    const user = userEvent.setup();
    let calls = 0;
    server.use(
      http.get('/api/v1/settings', () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json({ detail: 'boom' }, { status: 500 })
          : HttpResponse.json(makeSettings());
      }),
    );
    renderWithProviders(<SettingsPage />);
    expect(await screen.findByText("Couldn't load your settings")).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('button', { name: 'Save' })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (in `frontend/`): `npx vitest run src/features/settings`
Expected: FAIL (modules not found).

- [ ] **Step 3: Write the implementation**

Create `frontend/src/features/settings/settingsForm.ts`:

```typescript
import type { NewCardPolicyName, ReviewSettings, ReviewSettingsInput } from '../../api/endpoints';
import { ApiError } from '../../api/errors';

export const LEVELS = ['N5', 'N4', 'N3', 'N2', 'N1'] as const;
export type Level = (typeof LEVELS)[number];

/**
 * What the form edits. Retention and the mastery threshold are whole percentages here (the API
 * stores fractions); the limits and the threshold are `number | string` because a number input
 * holds an empty string while it is cleared.
 */
export interface SettingsFormValues {
  new_card_policy: NewCardPolicyName;
  new_limits: { kana: number | string; kanji: number | string; vocab: number | string };
  target_retention_percent: number;
  rollover_hour: number;
  active_levels: Level[];
  mastery_threshold_percent: number | string;
}

/**
 * The values a fresh install starts with. The API does not expose its defaults, so they are
 * repeated here; a test compares them with the defaults declared in the OpenAPI snapshot.
 */
export const RECOMMENDED_SETTINGS: ReviewSettings = {
  new_card_policy: 'strict_order',
  new_limits: { kana: 20, kanji: 15, vocab: 20 },
  target_retention: 0.9,
  rollover_hour: 4,
  active_levels: ['N5'],
  mastery_threshold: 0.8,
};

export const POLICIES: readonly { value: NewCardPolicyName; label: string; description: string }[] =
  [
    {
      value: 'strict_order',
      label: 'Strict order',
      description: 'Finish every card of a level before the next level starts.',
    },
    {
      value: 'mastery_unlock',
      label: 'Mastery unlock',
      description:
        'The next level also waits until enough of the current level is well known (in Review).',
    },
    {
      value: 'pinned_levels',
      label: 'Pinned levels',
      description: 'Only take new cards from the levels you pick below.',
    },
  ];

export const LIMIT_MAX = 10_000;
export const RETENTION_MIN_PERCENT = 70;
export const RETENTION_MAX_PERCENT = 99;

/** 0.905 becomes 90.5: a percentage without floating-point noise. */
function toPercent(fraction: number): number {
  return Number((fraction * 100).toFixed(2));
}

/** 90.5 becomes 0.905. */
function toFraction(percent: number): number {
  return Number((percent / 100).toFixed(4));
}

export function toFormValues(settings: ReviewSettings): SettingsFormValues {
  return {
    new_card_policy: settings.new_card_policy,
    new_limits: { ...settings.new_limits },
    target_retention_percent: toPercent(settings.target_retention),
    rollover_hour: settings.rollover_hour,
    active_levels: LEVELS.filter((level) => settings.active_levels.includes(level)),
    mastery_threshold_percent: toPercent(settings.mastery_threshold),
  };
}

/** The document to send: numbers as numbers, levels in study order, percentages as fractions. */
export function toRequest(values: SettingsFormValues): ReviewSettingsInput {
  return {
    new_card_policy: values.new_card_policy,
    new_limits: {
      kana: Number(values.new_limits.kana),
      kanji: Number(values.new_limits.kanji),
      vocab: Number(values.new_limits.vocab),
    },
    target_retention: toFraction(values.target_retention_percent),
    rollover_hour: values.rollover_hour,
    active_levels: LEVELS.filter((level) => values.active_levels.includes(level)),
    mastery_threshold: toFraction(Number(values.mastery_threshold_percent)),
  };
}

function isWholeNumber(value: number | string, min: number, max: number): boolean {
  if (typeof value === 'string' && value.trim() === '') return false;
  const number = Number(value);
  return Number.isInteger(number) && number >= min && number <= max;
}

const LIMIT_MESSAGE = `Enter a whole number from 0 to ${LIMIT_MAX.toLocaleString('en-US')}.`;

/** The API's rules, checked before anything is sent. Keys are form field paths. */
export function validateSettings(values: SettingsFormValues): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const type of ['kana', 'kanji', 'vocab'] as const) {
    if (!isWholeNumber(values.new_limits[type], 0, LIMIT_MAX)) {
      errors[`new_limits.${type}`] = LIMIT_MESSAGE;
    }
  }
  const retention = values.target_retention_percent;
  if (retention < RETENTION_MIN_PERCENT || retention > RETENTION_MAX_PERCENT) {
    errors.target_retention_percent = `Choose between ${RETENTION_MIN_PERCENT}% and ${RETENTION_MAX_PERCENT}%.`;
  }
  if (
    !Number.isInteger(values.rollover_hour) ||
    values.rollover_hour < 0 ||
    values.rollover_hour > 23
  ) {
    errors.rollover_hour = 'Choose an hour from 0 to 23.';
  }
  if (values.active_levels.length === 0) {
    errors.active_levels = 'Pick at least one level.';
  }
  const threshold = values.mastery_threshold_percent;
  const thresholdNumber = Number(threshold);
  if (
    (typeof threshold === 'string' && threshold.trim() === '') ||
    Number.isNaN(thresholdNumber) ||
    thresholdNumber < 0 ||
    thresholdNumber > 100
  ) {
    errors.mastery_threshold_percent = 'Enter a percentage from 0 to 100.';
  }
  return errors;
}

/** Where the server's field names live in the form. */
const SERVER_FIELDS: Readonly<Record<string, string>> = {
  new_card_policy: 'new_card_policy',
  kana: 'new_limits.kana',
  kanji: 'new_limits.kanji',
  vocab: 'new_limits.vocab',
  target_retention: 'target_retention_percent',
  rollover_hour: 'rollover_hour',
  active_levels: 'active_levels',
  mastery_threshold: 'mastery_threshold_percent',
};

export interface ServerErrors {
  /** Messages for fields the form has, keyed by form field path. */
  fields: Record<string, string>;
  /** Messages for anything the form cannot place, joined for one alert; null when none. */
  general: string | null;
}

/** Spread a 422's per-field messages over the form; whatever does not fit goes to `general`. */
export function placeServerErrors(error: ApiError): ServerErrors {
  const fields: Record<string, string> = {};
  const leftovers: string[] = [];
  for (const [name, message] of Object.entries(error.fieldErrors)) {
    const path = SERVER_FIELDS[name];
    if (path === undefined) leftovers.push(`${name}: ${message}`);
    else fields[path] = message;
  }
  if (Object.keys(fields).length === 0 && leftovers.length === 0) {
    leftovers.push('The server did not accept these settings.');
  }
  return { fields, general: leftovers.length === 0 ? null : leftovers.join(' ') };
}
```

Create `frontend/src/features/settings/PolicyField.tsx`:

```tsx
import { Group, Radio, Stack, Text } from '@mantine/core';

import type { NewCardPolicyName } from '../../api/endpoints';
import { POLICIES } from './settingsForm';

interface PolicyFieldProps {
  value: NewCardPolicyName;
  onChange: (value: NewCardPolicyName) => void;
  error?: string | undefined;
}

function isPolicy(value: string): value is NewCardPolicyName {
  return POLICIES.some((policy) => policy.value === value);
}

/** The three ways of choosing new cards, as radio cards with a one-line explanation each. */
export function PolicyField({ value, onChange, error }: PolicyFieldProps) {
  return (
    <Radio.Group
      value={value}
      onChange={(next) => {
        if (isPolicy(next)) onChange(next);
      }}
      label="How new cards are chosen"
      error={error}
    >
      <Stack gap="xs" mt="xs">
        {POLICIES.map((policy) => (
          <Radio.Card key={policy.value} value={policy.value} p="md" withBorder>
            <Group wrap="nowrap" align="flex-start">
              <Radio.Indicator />
              <div>
                <Text fw={500}>{policy.label}</Text>
                <Text size="sm" c="dimmed">
                  {policy.description}
                </Text>
              </div>
            </Group>
          </Radio.Card>
        ))}
      </Stack>
    </Radio.Group>
  );
}
```

Create `frontend/src/features/settings/SettingsPage.tsx`:

```tsx
import {
  Alert,
  Button,
  Chip,
  Group,
  Input,
  NativeSelect,
  NumberInput,
  Skeleton,
  Slider,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { useState } from 'react';

import type { ReviewSettings, ReviewSettingsInput } from '../../api/endpoints';
import { ApiError, messageFor } from '../../api/errors';
import { useSettings, useUpdateSettings } from '../../api/queries';
import { PolicyField } from './PolicyField';
import {
  LEVELS,
  LIMIT_MAX,
  RECOMMENDED_SETTINGS,
  RETENTION_MAX_PERCENT,
  RETENTION_MIN_PERCENT,
  placeServerErrors,
  toFormValues,
  toRequest,
  validateSettings,
  type Level,
  type SettingsFormValues,
} from './settingsForm';

const HOURS = Array.from({ length: 24 }, (_, hour) => ({
  value: String(hour),
  label: `${hour}:00`,
}));

function isLevel(value: string): value is Level {
  return LEVELS.some((level) => level === value);
}

/** The form, seeded once from `initial`: a background refetch must never replace what is typed. */
function SettingsForm({ initial }: { initial: ReviewSettings }) {
  const save = useUpdateSettings();
  const [general, setGeneral] = useState<{ message: string; retryable: boolean } | null>(null);
  const form = useForm<SettingsFormValues>({
    mode: 'controlled',
    initialValues: toFormValues(initial),
    validate: validateSettings,
  });
  const { mutate: sendSettings } = save;

  const submit = (request: ReviewSettingsInput) => {
    setGeneral(null);
    sendSettings(request, {
      onSuccess: (saved) => {
        const values = toFormValues(saved);
        form.setValues(values);
        form.setInitialValues(values);
        form.resetDirty(values);
        notifications.show({ message: 'Settings saved' });
      },
      onError: (error) => {
        if (error instanceof ApiError && error.status === 422) {
          const placed = placeServerErrors(error);
          form.setErrors(placed.fields);
          if (placed.general !== null) setGeneral({ message: placed.general, retryable: false });
          return;
        }
        setGeneral({ message: messageFor(error), retryable: true });
      },
    });
  };

  const values = form.getValues();
  const dirty = form.isDirty();
  const pinned = values.new_card_policy === 'pinned_levels';
  const mastery = values.new_card_policy === 'mastery_unlock';

  return (
    <form
      onSubmit={form.onSubmit((submitted) => {
        submit(toRequest(submitted));
      })}
      noValidate
    >
      <Stack gap="xl">
        <Stack gap="md">
          <Title order={3}>New cards</Title>
          <PolicyField
            value={values.new_card_policy}
            onChange={(policy) => {
              form.setFieldValue('new_card_policy', policy);
            }}
            error={
              typeof form.errors.new_card_policy === 'string'
                ? form.errors.new_card_policy
                : undefined
            }
          />
          <Group grow align="flex-start">
            <NumberInput
              label="Kana per day"
              min={0}
              max={LIMIT_MAX}
              allowDecimal={false}
              {...form.getInputProps('new_limits.kana')}
            />
            <NumberInput
              label="Kanji per day"
              min={0}
              max={LIMIT_MAX}
              allowDecimal={false}
              {...form.getInputProps('new_limits.kanji')}
            />
            <NumberInput
              label="Vocabulary per day"
              min={0}
              max={LIMIT_MAX}
              allowDecimal={false}
              {...form.getInputProps('new_limits.vocab')}
            />
          </Group>
          <Text size="sm" c="dimmed">
            The most new cards of each type per day. 0 means no limit.
          </Text>
        </Stack>

        <Stack gap="md">
          <Title order={3}>Levels</Title>
          <Input.Wrapper
            label="Levels to study"
            description={
              pinned ? 'New cards come only from these levels.' : 'Only used by "Pinned levels".'
            }
            error={
              typeof form.errors.active_levels === 'string' ? form.errors.active_levels : undefined
            }
          >
            <Chip.Group
              multiple
              value={values.active_levels}
              onChange={(next) => {
                form.setFieldValue('active_levels', next.filter(isLevel));
              }}
            >
              <Group gap="xs" mt="xs">
                {LEVELS.map((level) => (
                  <Chip key={level} value={level} disabled={!pinned}>
                    {level}
                  </Chip>
                ))}
              </Group>
            </Chip.Group>
          </Input.Wrapper>
          <NumberInput
            label="Mastery needed to unlock the next level"
            description={
              mastery
                ? 'Share of the current level that must be well known (in Review).'
                : 'Only used by "Mastery unlock".'
            }
            min={0}
            max={100}
            allowDecimal={false}
            suffix="%"
            disabled={!mastery}
            {...form.getInputProps('mastery_threshold_percent')}
          />
        </Stack>

        <Stack gap="md">
          <Title order={3}>Scheduling</Title>
          <Input.Wrapper
            label={`Target retention: ${String(values.target_retention_percent)}%`}
            description="How often you want to remember a card when it comes back. Higher means more reviews."
            error={
              typeof form.errors.target_retention_percent === 'string'
                ? form.errors.target_retention_percent
                : undefined
            }
          >
            <Slider
              mt="sm"
              min={RETENTION_MIN_PERCENT}
              max={RETENTION_MAX_PERCENT}
              step={1}
              value={values.target_retention_percent}
              onChange={(percent) => {
                form.setFieldValue('target_retention_percent', percent);
              }}
              label={(percent) => `${String(percent)}%`}
              thumbLabel="Target retention"
              marks={[
                { value: 70, label: '70%' },
                { value: 80, label: '80%' },
                { value: 90, label: '90%' },
                { value: 99, label: '99%' },
              ]}
            />
          </Input.Wrapper>
        </Stack>

        <Stack gap="md">
          <Title order={3}>Study day</Title>
          <NativeSelect
            label="A new study day starts at"
            description="In the server's timezone (the TZ setting). Daily limits reset then."
            data={HOURS}
            value={String(values.rollover_hour)}
            onChange={(event) => {
              form.setFieldValue('rollover_hour', Number(event.currentTarget.value));
            }}
            error={
              typeof form.errors.rollover_hour === 'string' ? form.errors.rollover_hour : undefined
            }
          />
        </Stack>

        {general !== null && (
          <Alert color="red" title="Couldn't save your settings">
            <Text size="sm">{general.message}</Text>
            {general.retryable && save.variables !== undefined && (
              <Button
                mt="sm"
                size="xs"
                disabled={save.isPending}
                onClick={() => {
                  if (save.variables !== undefined) submit(save.variables);
                }}
              >
                Try again
              </Button>
            )}
          </Alert>
        )}

        <Group>
          <Button type="submit" disabled={!dirty} loading={save.isPending}>
            Save
          </Button>
          <Button
            variant="subtle"
            onClick={() => {
              form.setValues(toFormValues(RECOMMENDED_SETTINGS));
            }}
          >
            Reset to recommended values
          </Button>
          {dirty && (
            <Text size="sm" c="dimmed">
              Unsaved changes
            </Text>
          )}
        </Group>
      </Stack>
    </form>
  );
}

/** How new cards are chosen, how many, and how sharp your memory should stay. */
export function SettingsPage() {
  const settings = useSettings();

  return (
    <Stack gap="lg" maw={720}>
      <Title order={2}>Settings</Title>
      {settings.isPending && <Skeleton height={320} />}
      {settings.isError && (
        <Alert color="red" title="Couldn't load your settings">
          <Text size="sm">{messageFor(settings.error)}</Text>
          <Button
            mt="sm"
            size="xs"
            onClick={() => {
              void settings.refetch();
            }}
          >
            Try again
          </Button>
        </Alert>
      )}
      {settings.data !== undefined && !settings.isError && <SettingsForm initial={settings.data} />}
    </Stack>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run (in `frontend/`): `npx vitest run src/features/settings`
Expected: PASS (2 files, 34 tests). Run `for i in $(seq 8); do npx vitest run src/features/settings || break; done`: every run must pass.

- [ ] **Step 5: Run the frontend gate**

Run (in `frontend/`): `npm run format:check && npm run lint && npm run build && npm run coverage`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/settings/settingsForm.ts frontend/src/features/settings/settingsForm.test.ts frontend/src/features/settings/PolicyField.tsx frontend/src/features/settings/SettingsPage.tsx frontend/src/features/settings/SettingsPage.test.tsx
git commit -m "feat: the settings screen with validation and server error placement" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 4: Navigation, routes and the link from the review screen

**Files:**
- Modify: `frontend/src/components/AppLayout.tsx`, `frontend/src/components/AppLayout.test.tsx`, `frontend/src/features/review/ReviewFinished.tsx`, `frontend/src/features/review/ReviewPage.test.tsx` (one assertion), `frontend/src/App.tsx`, `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: `StatsPage` (Task 2), `SettingsPage` (Task 3), the fixtures `makeStatsSummary`, `makeSettings` (Task 1).
- Produces: `Statistics` (`/stats`) and `Settings` (`/settings`) navigation links; lazy routes `stats` and `settings` under the existing `Suspense` inside `AppLayout`; a "Change your daily limits in Settings" link on the review screen's done-for-now state.

- [ ] **Step 1: Write the tests**

Replace `frontend/src/components/AppLayout.test.tsx` with:

```tsx
import { act, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { lazy } from 'react';
import { Route, Routes } from 'react-router';
import { describe, expect, it, vi } from 'vitest';

import { AuthContext, type AuthContextValue } from '../auth/authContext';
import { RealtimeContext } from '../realtime/realtimeContext';
import { renderWithProviders } from '../test/render';
import { AppLayout } from './AppLayout';

let releaseSlowPage: () => void = () => undefined;
const SlowPage = lazy(
  () =>
    new Promise<{ default: () => React.JSX.Element }>((resolve) => {
      releaseSlowPage = () => {
        resolve({ default: () => <p>Slow page loaded</p> });
      };
    }),
);

function renderLayout(logout = vi.fn(), initialEntries: string[] = ['/']) {
  const auth: AuthContextValue = {
    status: 'authenticated',
    sessionExpired: false,
    login: () => Promise.resolve(),
    logout,
    retry: () => {},
  };
  renderWithProviders(
    <AuthContext value={auth}>
      <RealtimeContext value={{ kind: 'connected' }}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<p>Home content</p>} />
            <Route path="build" element={<p>Build content page</p>} />
            <Route path="slow" element={<SlowPage />} />
          </Route>
        </Routes>
      </RealtimeContext>
    </AuthContext>,
    { initialEntries },
  );
  return logout;
}

describe('AppLayout', () => {
  it('frames the page with the wordmark, navigation and the connection state', () => {
    renderLayout();
    expect(screen.getByRole('heading', { name: /Bunshō/ })).toBeInTheDocument();
    expect(document.querySelector('span[lang="ja"]')).toHaveTextContent('文章');
    expect(screen.getByRole('link', { name: 'Home' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Study' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Statistics' })).toHaveAttribute('href', '/stats');
    expect(screen.getByRole('link', { name: 'Settings' })).toHaveAttribute('href', '/settings');
    expect(screen.getByRole('link', { name: 'Build content' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Live');
    expect(screen.getByText('Home content')).toBeInTheDocument();
  });

  it('navigates between pages', async () => {
    renderLayout();
    await userEvent.click(screen.getByRole('link', { name: 'Build content' }));
    expect(screen.getByText('Build content page')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: 'Home' }));
    expect(screen.getByText('Home content')).toBeInTheDocument();
  });

  it('logs out on request', async () => {
    const logout = renderLayout();
    await userEvent.click(screen.getByRole('button', { name: 'Log out' }));
    expect(logout).toHaveBeenCalledTimes(1);
  });

  it('says, in visible text, that logging out only affects this browser', () => {
    renderLayout();
    const note = screen.getByText(
      'Logging out only affects this browser: the server cannot end sessions yet.',
    );
    expect(note).toBeVisible();
    expect(note).toHaveAttribute('id');
    expect(screen.getByRole('button', { name: 'Log out' })).toHaveAccessibleDescription(
      note.textContent,
    );
    expect(screen.getByRole('button', { name: 'Log out' })).toHaveAttribute(
      'aria-describedby',
      note.id,
    );
  });

  it('has a theme toggle', () => {
    renderLayout();
    expect(screen.getByRole('radio', { name: 'Dark' })).toBeInTheDocument();
  });

  it('shows a loading indicator while a page is being fetched, then the page', async () => {
    renderLayout(vi.fn(), ['/slow']);
    expect(screen.getByRole('status', { name: 'Loading page' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Home' })).toBeInTheDocument();
    await act(async () => {
      releaseSlowPage();
      await Promise.resolve();
    });
    expect(await screen.findByText('Slow page loaded')).toBeInTheDocument();
    expect(screen.queryByRole('status', { name: 'Loading page' })).not.toBeInTheDocument();
  });
});
```

Replace `frontend/src/App.test.tsx` with:

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { App } from './App';
import { REFRESH_TOKEN_KEY, session } from './auth/session';
import { FakeSocket } from './test/fakeSocket';
import { makeKanaCard, makeNextCard, makeSettings, makeStatsSummary } from './test/fixtures';
import { server } from './test/server';

const TOKENS = { access_token: 'a2', refresh_token: 'r2', token_type: 'bearer', expires_in: 900 };
const SUMMARY = {
  built: true,
  kana: 208,
  kanji: 3088,
  vocab: 7734,
  unleveled_kanji: 979,
  kanji_by_level: { N5: 480, N4: 352, N3: 544, N2: 357, N1: 376 },
  vocab_by_level: { N5: 667, N4: 630, N3: 1647, N2: 1737, N1: 3053 },
  meta: {},
};

/** A FakeSocket that remembers every instance the app creates through the global WebSocket. */
class TrackedSocket extends FakeSocket {
  static instances: TrackedSocket[] = [];

  constructor(url: string) {
    super(url);
    TrackedSocket.instances.push(this);
  }
}

function rememberLogin() {
  window.localStorage.setItem(REFRESH_TOKEN_KEY, 'r1');
  server.use(
    http.post('/api/v1/auth/refresh', () => HttpResponse.json(TOKENS)),
    http.get('/api/v1/content/summary', () => HttpResponse.json(SUMMARY)),
    http.get('/api/v1/reviews/next', () => HttpResponse.json(makeNextCard(makeKanaCard()))),
    http.get('/api/v1/stats/summary', () => HttpResponse.json(makeStatsSummary())),
    http.get('/api/v1/settings', () => HttpResponse.json(makeSettings())),
    http.get('/api/v1/admin/config-check', () => HttpResponse.json({ ok: true, checks: [] })),
    http.get('/api/v1/admin/content/build', () =>
      HttpResponse.json({ detail: 'no build has run yet' }, { status: 404 }),
    ),
  );
}

function goTo(path: string) {
  window.history.pushState({}, '', path);
}

describe('App', () => {
  beforeEach(() => {
    session.clear();
    TrackedSocket.instances = [];
    vi.stubGlobal('WebSocket', TrackedSocket); // no real connection attempts from the live stream
    goTo('/');
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends a visitor without a login to the login page', async () => {
    render(<App />);
    expect(await screen.findByLabelText('Username')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/login');
  });

  it('opens straight on the home page for a remembered login', async () => {
    rememberLogin();
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Your content' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Bunshō/ })).toBeInTheDocument();
  });

  it('navigates to the build page and back', async () => {
    rememberLogin();
    render(<App />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('link', { name: 'Build content' }));
    expect(await screen.findByRole('heading', { name: 'Content' })).toBeInTheDocument();
    expect(window.location.pathname).toBe('/build');
    await user.click(screen.getByRole('link', { name: 'Home' }));
    expect(await screen.findByRole('heading', { name: 'Your content' })).toBeInTheDocument();
  });

  it('starts a study session from the dashboard and finds its way back', async () => {
    rememberLogin();
    render(<App />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('link', { name: 'Study now' }));
    expect(await screen.findByRole('heading', { name: 'Study' })).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Show answer' })).toBeInTheDocument();
    expect(window.location.pathname).toBe('/review');
    await user.click(screen.getByRole('link', { name: 'Home' }));
    expect(await screen.findByRole('heading', { name: 'Today' })).toBeInTheDocument();
  });

  it('opens the statistics and the settings from the navigation', async () => {
    rememberLogin();
    render(<App />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('link', { name: 'Statistics' }));
    expect(await screen.findByRole('heading', { name: 'Statistics' })).toBeInTheDocument();
    expect(window.location.pathname).toBe('/stats');
    await user.click(screen.getByRole('link', { name: 'Settings' }));
    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Save' })).toBeInTheDocument();
    expect(window.location.pathname).toBe('/settings');
  });

  it('serves a deep link to the settings after the login is restored', async () => {
    rememberLogin();
    goTo('/settings');
    render(<App />);
    expect(
      await screen.findByRole('button', { name: 'Reset to recommended values' }),
    ).toBeInTheDocument();
  });

  it('serves a deep link after the login is restored', async () => {
    rememberLogin();
    goTo('/build');
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Content' })).toBeInTheDocument();
  });

  it('answers an unknown address with a not-found page', async () => {
    rememberLogin();
    goTo('/nothing/here');
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument();
  });

  it('logs out and forgets the remembered login', async () => {
    rememberLogin();
    render(<App />);
    await userEvent.click(await screen.findByRole('button', { name: 'Log out' }));
    expect(await screen.findByLabelText('Username')).toBeInTheDocument();
    expect(window.localStorage.getItem(REFRESH_TOKEN_KEY)).toBeNull();
    await waitFor(() => {
      expect(window.location.pathname).toBe('/login');
    });
  });

  it('lands on the login page with a notice when the live stream loses its session', async () => {
    rememberLogin();
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Your content' })).toBeInTheDocument();
    await waitFor(() => {
      expect(TrackedSocket.instances).toHaveLength(1);
    });
    const socket = TrackedSocket.instances[0];
    if (socket === undefined) throw new Error('the live stream never connected');

    // From now on the server rejects the refresh token; the stream is told to go away (1008).
    server.use(
      http.post('/api/v1/auth/refresh', () =>
        HttpResponse.json({ detail: 'Invalid or expired refresh token' }, { status: 401 }),
      ),
    );
    socket.open();
    socket.serverClose(1008);

    expect(await screen.findByLabelText('Username')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/login');
    expect(window.localStorage.getItem(REFRESH_TOKEN_KEY)).toBeNull();
    expect(screen.getByText('Your session has expired. Please log in again.')).toBeInTheDocument();
    expect(await screen.findByText('Log in again to continue.')).toBeInTheDocument();
  });
});
```

In `frontend/src/features/review/ReviewPage.test.tsx`, in the test `shows the finished state with the next due time and a link back`, replace

```tsx
    expect(screen.getByRole('link', { name: 'Back to the dashboard' })).toHaveAttribute(
      'href',
      '/',
    );
  });
```

with

```tsx
    expect(screen.getByRole('link', { name: 'Back to the dashboard' })).toHaveAttribute(
      'href',
      '/',
    );
    expect(
      screen.getByRole('link', { name: 'Change your daily limits in Settings' }),
    ).toHaveAttribute('href', '/settings');
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (in `frontend/`): `npx vitest run src/components src/App.test.tsx src/features/review/ReviewPage.test.tsx`
Expected: FAIL (no `Statistics`/`Settings` links, no settings link on the done state, `/stats` and `/settings` unknown).

- [ ] **Step 3: Write the implementation**

Replace `frontend/src/components/AppLayout.tsx` with:

```tsx
import { AppShell, Burger, Button, Group, NavLink, Stack, Text, Title } from '@mantine/core';
import { useDisclosure, useId } from '@mantine/hooks';
import { Suspense } from 'react';
import { Link, Outlet, useLocation } from 'react-router';

import { useAuth } from '../auth/authContext';
import { ConnectionBadge } from '../realtime/ConnectionBadge';
import { ColorSchemeToggle } from './ColorSchemeToggle';
import { ErrorBoundary } from './ErrorBoundary';
import { PageLoader } from './PageLoader';

const NAVIGATION = [
  { to: '/', label: 'Home' },
  { to: '/review', label: 'Study' },
  { to: '/stats', label: 'Statistics' },
  { to: '/settings', label: 'Settings' },
  { to: '/build', label: 'Build content' },
] as const;

/** The frame around every logged-in page: header, navigation and the page itself. */
export function AppLayout() {
  const [opened, { toggle, close }] = useDisclosure(false);
  const { logout } = useAuth();
  const { pathname } = useLocation();
  const logoutNoteId = useId();

  return (
    <AppShell
      header={{ height: 56 }}
      navbar={{ width: 220, breakpoint: 'sm', collapsed: { mobile: !opened } }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger
              opened={opened}
              onClick={toggle}
              hiddenFrom="sm"
              size="sm"
              aria-label="Toggle navigation"
            />
            <Title order={3}>
              Bunshō <span lang="ja">文章</span>
            </Title>
          </Group>
          <Group gap="xs" wrap="nowrap">
            <ConnectionBadge />
            <ColorSchemeToggle />
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="md">
        <Stack justify="space-between" h="100%">
          <div>
            {NAVIGATION.map((item) => (
              <NavLink
                key={item.to}
                component={Link}
                to={item.to}
                label={item.label}
                active={pathname === item.to}
                onClick={close}
              />
            ))}
          </div>
          {/* In the navbar (not the header) so the notice is visible text in the burger drawer too. */}
          <Stack gap={4}>
            <Button variant="subtle" onClick={logout} aria-describedby={logoutNoteId}>
              Log out
            </Button>
            <Text id={logoutNoteId} size="xs" c="dimmed">
              Logging out only affects this browser: the server cannot end sessions yet.
            </Text>
          </Stack>
        </Stack>
      </AppShell.Navbar>
      <AppShell.Main>
        <ErrorBoundary key={pathname}>
          <Suspense fallback={<PageLoader />}>
            <Outlet />
          </Suspense>
        </ErrorBoundary>
      </AppShell.Main>
    </AppShell>
  );
}
```

Replace `frontend/src/features/review/ReviewFinished.tsx` with:

```tsx
import { Alert, Button, Stack, Text, Title } from '@mantine/core';
import { Link } from 'react-router';

import type { NextCard } from '../../api/endpoints';
import { formatDueTime } from './formatInterval';

/**
 * No card to study right now. The API cannot say whether the daily new-card limit is used up or
 * everything unlocked has been introduced, so the message names both.
 */
export function ReviewDone({ data }: { data: NextCard }) {
  return (
    <Stack align="center" gap="sm" py="xl" ta="center">
      <Title order={3}>You&apos;re done for now</Title>
      <Text c="dimmed" maw={460}>
        Nothing is due and no new cards are available today. The daily new-card limit may be used
        up, or every card that is unlocked has been introduced.
      </Text>
      {data.next_due_at !== null && <Text>Next card due {formatDueTime(data.next_due_at)}.</Text>}
      <Button component={Link} to="/" variant="light">
        Back to the dashboard
      </Button>
      <Button component={Link} to="/settings" variant="subtle" size="xs">
        Change your daily limits in Settings
      </Button>
    </Stack>
  );
}

/** The content has not been built yet, so there is nothing to study. */
export function ReviewNotBuilt() {
  return (
    <Alert color="blue" title="Nothing to study yet">
      <Text size="sm">The study content has not been built yet.</Text>
      <Button component={Link} to="/build" mt="sm" size="xs">
        Build your content
      </Button>
    </Alert>
  );
}
```

Replace `frontend/src/App.tsx` with:

```tsx
import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { QueryClientProvider } from '@tanstack/react-query';
import { lazy, useState } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router';

import { AuthProvider } from './auth/AuthProvider';
import { RequireAuth } from './auth/RequireAuth';
import { AppLayout } from './components/AppLayout';
import { LoginPage } from './features/login/LoginPage';
import { NotFoundPage } from './features/NotFoundPage';
import { createQueryClient } from './queryClient';
import { RealtimeProvider } from './realtime/RealtimeProvider';
import { theme } from './theme';

import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';

// The pages load on demand, so the first screen (login) does not carry the study or build code.
const HomePage = lazy(() =>
  import('./features/home/HomePage').then((module) => ({ default: module.HomePage })),
);
const ReviewPage = lazy(() =>
  import('./features/review/ReviewPage').then((module) => ({ default: module.ReviewPage })),
);
const StatsPage = lazy(() =>
  import('./features/stats/StatsPage').then((module) => ({ default: module.StatsPage })),
);
const SettingsPage = lazy(() =>
  import('./features/settings/SettingsPage').then((module) => ({ default: module.SettingsPage })),
);
const BuildPage = lazy(() =>
  import('./features/build/BuildPage').then((module) => ({ default: module.BuildPage })),
);

export function App() {
  const [queryClient] = useState(createQueryClient);

  return (
    <MantineProvider theme={theme} defaultColorScheme="auto">
      <Notifications position="top-right" />
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AuthProvider>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route element={<RequireAuth />}>
                <Route
                  element={
                    <RealtimeProvider>
                      <AppLayout />
                    </RealtimeProvider>
                  }
                >
                  <Route index element={<HomePage />} />
                  <Route path="review" element={<ReviewPage />} />
                  <Route path="stats" element={<StatsPage />} />
                  <Route path="settings" element={<SettingsPage />} />
                  <Route path="build" element={<BuildPage />} />
                  <Route path="*" element={<NotFoundPage />} />
                </Route>
              </Route>
            </Routes>
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </MantineProvider>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run (in `frontend/`): `npx vitest run`
Expected: PASS (31 files, 268 tests). Run `for i in $(seq 8); do npx vitest run src/features/settings src/features/stats src/App.test.tsx src/components src/api || break; done`: every run must pass.

- [ ] **Step 5: Run the frontend gate and check the bundle**

Run (in `frontend/`): `npm run format:check && npm run lint && npm run build && npm run coverage`
Expected: all green, and the build output shows separate `StatsPage` (about 411 kB, recharts) and `SettingsPage` (about 53 kB) chunks, the main `index` chunk still about 388 kB, and **no** "Some chunks are larger than 500 kB" warning. Do not raise `chunkSizeWarningLimit`. Report the chunk sizes.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/AppLayout.tsx frontend/src/components/AppLayout.test.tsx frontend/src/features/review/ReviewFinished.tsx frontend/src/features/review/ReviewPage.test.tsx frontend/src/App.tsx frontend/src/App.test.tsx
git commit -m "feat: Statistics and Settings navigation, lazy routes and a settings link when done" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 5: Documentation, whole-branch verification and review

**Files:**
- Modify: `README.md`, `CHANGELOG.md`, `TODO.md`, `docs/superpowers/specs/2026-09-21-bunsho-2b3-stats-settings-design.md` (implementation notes)

The docs files use CRLF line endings in the working tree: keep them (do not introduce mixed endings; check that the CR count equals the LF count afterwards).

- [ ] **Step 1: Update the README**

In the "Studying (review API)" section, in the paragraph that starts `**Web UI.**`, extend the list of pages: `` `/stats` for statistics and `/settings` for the review settings `` (keep the existing pages in the list).

Directly after the paragraph `**Studying in the browser.**` add:

````markdown
**Statistics and settings.** *Statistics* shows today's reviews and new cards, your 30-day retention, a chart of the last 30 days, the number of cards by state and your progress through each JLPT level. *Settings* holds every review setting in one form: how new cards are chosen (strict order, mastery unlock or pinned levels), the daily new-card limits (0 means unlimited), the levels used by *Pinned levels*, the mastery threshold used by *Mastery unlock*, your target retention and the hour a new study day starts (in the server's timezone). Nothing is saved until you press *Save*; the new settings apply from the next card. *Reset to recommended values* only refills the form.
````

- [ ] **Step 2: CHANGELOG, TODO and spec notes**

`CHANGELOG.md`, under `## [Unreleased]` → `### Added`, directly after the "Study screens" bullet:

```markdown
- Statistics and settings screens in the web UI. Statistics: today's reviews and new cards, 30-day
  retention, a 30-day chart (Mantine Charts, with the same numbers in an accessible table), cards by
  state and progress by JLPT level. Settings: one form for the new-card policy, daily limits, levels,
  mastery threshold, target retention and the study-day hour, with validation in the browser, the
  server's messages placed on the matching fields, and the new limits applied from the next card. The
  review screen's "done for now" state links to Settings. Adds the `@mantine/charts` and `recharts`
  dependencies (loaded only on the statistics page).
```

`TODO.md`:
- Replace the status paragraph at the top with: `Status: Plans 1A, 1B, 1C, 2A, 2B-1 and 2B-2 are merged. Plan 2B-3 (statistics and settings screens) is implemented on `feat/plan-2b3-stats-settings`; the first version of the UI is then complete. Design: the specs in `docs/superpowers/specs/`. Plans: `docs/superpowers/plans/`.` (keep the existing wrapping style).
- Under "Plan 2B-2 and later": tick the item "Statistics and settings screens (Plan 2B-3)" (`- [x] ... (Plan 2B-3)`) and the item about per-level progress on the dashboard by rewording it to say the per-level progress is on the statistics screen (keep it as an optional idea to also summarise it on the dashboard).
- Add these open items under the same heading (one each, short, in the file's style): "Ask before leaving the settings page with unsaved changes"; "Expose the review-setting defaults through the API so the form does not repeat them (`RECOMMENDED_SETTINGS` is checked against the OpenAPI snapshot)"; "Settings: show the server timezone and the next study-day rollover (needs an API field)"; "Statistics: a longer range than 30 days and a retention-by-day line need API changes"; "The statistics chunk is about 410 kB because of recharts: if it grows, consider a lighter chart"; "Browser end-to-end tests of the whole UI".

Append to the spec `docs/superpowers/specs/2026-09-21-bunsho-2b3-stats-settings-design.md` an "Implementation notes" section (the spec has none yet) listing: the number input clamps to its range on blur (so an empty field is the only invalid limit reachable by typing); toasts and alerts both use `role="alert"`; `SettingsForm` is seeded once and `useSettings` never refetches on focus or reconnect; percentages are converted with `toFixed` so a stored 0.905 is kept; after a save the form resets to the server's response; the recommended-values test reads `openapi.json` through `?raw`; the statistics chart is `aria-hidden` with a visually hidden table beside it; kana has no level rows in the per-level progress; the bundle sizes of the statistics and settings chunks.

- [ ] **Step 3: Whole-branch verification**

```bash
unset VIRTUAL_ENV
uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run bandit -c pyproject.toml -r src -q
uv run pytest --cov=src/bunsho -q
cd frontend && npm ci && npm run format:check && npm run lint && npm run build && npm run coverage && cd ..
uv run python scripts/export_openapi.py && (cd frontend && npm run gen:api)
git diff --exit-code -- frontend/src/api/schema.d.ts frontend/openapi.json
uv run python scripts/smoke_test.py
```
Expected: everything green; Python coverage at or above 90% (no backend change: 552 tests); frontend coverage at or above 80% (about 268 tests); the schema files unchanged; the smoke test ends `[smoke] PASS` (the Docker image builds the UI with the two new packages and serves it). Also confirm `git status` is clean.

- [ ] **Step 4: Whole-branch review (Sonnet)**

Dispatch one whole-branch review with `superpowers:requesting-code-review` on a **Sonnet** model (James: not Opus), against `main`, given the spec, this plan, "Refinements to the spec" and the ledger. Ask it to check specifically: the settings save flow (the whole document is sent, percentages converted without loss, nothing is sent while a field is invalid, a 422 lands on the right fields, a network failure keeps the edits and Try again re-sends the identical request, a stale response cannot overwrite typing, the cache and the review/statistics queries after a save); form accessibility (labels, descriptions tied to fields, disabled hints, the slider and select names, focus after errors); the policy-dependent fields (disabled but still saved); the statistics screen (numbers against the API fields, zero and null cases, the chart's accessible table, dark mode colours, level rows for kanji and vocabulary only); the two new dependencies (versions match `@mantine/core`, the chart code and CSS load only on the statistics route, no other route imports them, bundle sizes reported); lazy routes, navigation and the done-screen link; test quality (MSW only, no real timers, no vacuous assertions, flake risk in the form tests); and consistency between README, CHANGELOG, TODO, the spec notes and the code. Fix Critical and Important findings in one fix wave and re-review only that wave; record Minor findings in `TODO.md`.

- [ ] **Step 5: Push and prepare the PR**

```bash
git push
gh pr ready   # only when CI is green on ubuntu, windows and macOS, including the frontend and smoke jobs
```
Update the draft PR description (end with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`): what was built, the two new dependencies with their resolved versions, test counts and coverage (Python and frontend), the bundle sizes (main chunk unchanged, statistics and settings chunks), the smoke-test result, what could not be checked in a browser (the authenticated screens: the chart, the slider and policy cards, dark mode, the mobile layout: ask James to eyeball them), and that this completes the first version of the UI. James reviews and merges; do not merge.
