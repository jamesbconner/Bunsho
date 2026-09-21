# Bunshō Plan 2B-2: The Study Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let James study in the browser: a dashboard with what is due and new, and a flip-and-grade review screen with keyboard shortcuts and furigana, served by the existing app, with the routes split into on-demand chunks.

**Architecture:** No backend change. The frontend gains typed wrappers for `GET /reviews/next` and `POST /reviews/answer`, one shared `['review','next']` query (dashboard and review use the same cache entry), a pure `cardFaces` function that turns a card into its front and back, a native-`<ruby>` `Furigana` component, a `FlipMode` behind a small `ReviewMode` props contract, and a `ReviewPage` that owns fetching, timing and errors. Routes become `React.lazy` chunks under one `Suspense` fallback.

**Tech Stack:** Same as Plan 2B-1 (React 19, Vite 8, TypeScript 6.0.3, Mantine 9, React Router 8 declarative mode, TanStack Query 5, Vitest 5 + React Testing Library + MSW 2). No new dependency.

**Spec:** `docs/superpowers/specs/2026-09-20-bunsho-2b2-study-loop-design.md` (parents: `2026-09-20-bunsho-2a-review-engine-design.md`, `2026-09-20-bunsho-2b1-frontend-skeleton-design.md`). Read it before starting.

## Global Constraints

Every task's requirements include this section.

- **Latest stable versions of every library and tool** (James): this plan adds no dependency; if one is ever added, install with `@latest` and record the resolved version in the PR. The one known exception is unchanged from Plan 2B-1: TypeScript is pinned to 6.0.3 (with the npm `overrides` entry) and `@types/node` to the 24 line.
- Frontend: strict TypeScript (`strict`, `noUncheckedIndexedAccess`, `erasableSyntaxOnly`: no enums, no parameter properties, no namespaces; use `import type`); ESLint (flat config, `recommendedTypeChecked`, `react-hooks`, `react-refresh`) with zero errors and **no new `eslint-disable` comments**; Prettier (`singleQuote`, `printWidth: 100`, `trailingComma: all`) with `format:check` clean; coverage gate 80% (lines, functions, branches, statements).
- Hand-written API types are forbidden: every request/response type comes from `src/api/schema.d.ts` (generated from `frontend/openapi.json`). This plan does not change the backend, `frontend/openapi.json` or `schema.d.ts`.
- All UI text is English; every Japanese text run carries `lang="ja"`; the HTML root is `lang="en"`.
- Tokens (access or refresh) are never put in URLs, logs, query keys or the query cache. The refresh token is stored only under `localStorage` key `bunsho.refresh_token`. The furigana preference is stored only under `bunsho.show_furigana`; every storage access is wrapped in try/catch.
- `expected_last_review` is an opaque token: send it back exactly as received, never parse or reformat it.
- Live regions announce static text only (nothing that changes every second); the review screen has exactly one persistent status region.
- Port `8192` for the API (never `8000`).
- Commits: conventional commits, stage explicit paths only (never `git add .` / `-A`), trailer as its own paragraph: `git commit -m "<subject>" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"`. Never stage `.gitignore` (the repo-root one is user-owned), `.python-version`, `.superpowers/`. Never merge to `main`; James merges.
- Windows / Git Bash quirks: run `unset VIRTUAL_ENV` before `uv`; quote paths (`Bunshō` contains ō); set `PYTHONIOENCODING=utf-8` when printing Japanese; re-read files containing Japanese after writing them (the test files contain Japanese text). The repo-root `.gitignore` ignores any directory named `build/`, `lib/`, `env/`, `var/`, `parts/` or `downloads/`: this plan creates none, but check that `git status` shows every new file you expect before committing.
- Verification commands. Frontend (`frontend/`): `npm run format:check && npm run lint && npm run build && npm run coverage`. Backend (repo root, only in Task 6): `uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run bandit -c pyproject.toml -r src -q && uv run pytest -q`.

## Refinements to the spec

Decisions taken while building the verified prototype; the spec's body already reflects the first two.

1. **One "done for now" state.** `new_remaining` counts only cards that could be introduced right now, so "daily limit used up" and "everything unlocked is already introduced" are indistinguishable; the screen names both reasons in one message.
2. **`StudyPanel`** (not "tiles") is the dashboard component; the spec's task order 5 and 6 (dashboard/nav, then lazy routes) are one task here (Task 5) so each shared file (`App.tsx`, `AppLayout.tsx`, `HomePage.tsx`) is written once.
3. **The answer mutation stays pending until the next card has been fetched** (`onSuccess` awaits `invalidateQueries`), so the page never shows the card that was just graded; the screen treats `answer.isPending || next.isFetching` as "busy" (buttons disabled, keys ignored).
4. **After the flip, focus moves to the grade group (a `tabIndex=-1` `div`), not to the first grade button**: Space activates a button on key-up, so a key still held down from the flip could otherwise press "Again".
5. **`RubySegment.highlighted` and `Vocab.tags` are required fields** in the generated types (the API declares defaults as required), so test fixtures use the `segment()` helper and include `tags: []`.
6. The **status announcement** ("Card shown", "Answer shown", "Saving answer", "Nothing due right now") lives in the page, not the mode, so one region exists before its text changes.
7. Unit tests use the `data-highlighted` attribute, not CSS-module class names (Vitest does not process CSS modules).

## Verified prototype

All frontend code below was written and run in a scratch worktree with exactly the current dependencies: `tsc -b`, ESLint, Prettier, **204 tests in 27 files** (about 97.8% statement coverage), the production build (main chunk about 388 kB, no "larger than 500 kB" warning) were all green, and the review/home/component tests passed 8 runs in a row. The code is inlined verbatim; if a command disagrees, fix the disagreement minimally and report it, never weaken a check.

## File Structure

New (all under `frontend/src/`): `components/{Furigana.tsx,Furigana.module.css,Furigana.test.tsx,PageLoader.tsx}`, `features/review/{cardFaces.ts,cardFaces.test.ts,formatInterval.ts,formatInterval.test.ts,review.module.css,ReviewCard.tsx,GradeBar.tsx,useReviewShortcuts.ts,useFuriganaPreference.ts,useFuriganaPreference.test.ts,reviewMode.ts,FlipMode.tsx,FlipMode.test.tsx,ReviewFinished.tsx,ReviewPage.tsx,ReviewPage.test.tsx}`, `features/home/{StudyPanel.tsx,StudyPanel.test.tsx}`.

Modified: `api/endpoints.ts`, `api/endpoints.test.ts`, `api/queries.ts`, `api/queries.test.tsx`, `test/fixtures.ts`, `features/home/HomePage.tsx`, `features/home/HomePage.test.tsx`, `components/AppLayout.tsx`, `components/AppLayout.test.tsx`, `App.tsx`, `App.test.tsx`; and `README.md`, `CHANGELOG.md`, `TODO.md` plus the spec's implementation notes.

---

## Task 0: Branch and draft PR

**Files:** none.

- [ ] **Step 1: Confirm the docs PR (spec and this plan) is merged**

Run: `gh pr list --state all --limit 3`
Expected: the `docs/plan-2b2` PR shows `MERGED`. If it does not, stop and ask James (no stacked branches).

- [ ] **Step 2: Branch from a fresh main**

```bash
git checkout main && git pull
git checkout -b feat/plan-2b2-study-loop
```

- [ ] **Step 3: Draft PR after the first commit (Task 1)**

After Task 1's commit: `git push -u origin feat/plan-2b2-study-loop`, then `gh pr create --draft --title "Plan 2B-2: the study loop (dashboard and review)" --body "<summary>\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"`. CI then runs on every push.

---

## Task 1: Review endpoints, query hooks and fixtures

**Files:**
- Modify: `frontend/src/api/endpoints.ts`, `frontend/src/api/queries.ts`, `frontend/src/test/fixtures.ts`, `frontend/src/api/endpoints.test.ts`, `frontend/src/api/queries.test.tsx`

**Interfaces:**
- Consumes: `request()` from `api/client.ts`; generated types `NextCard`, `CardView`, `ReviewCounts`, `AnswerRequest`, `Grade`, `GradeIntervals`, `RubySegment` from `api/schema.d.ts`.
- Produces: `endpoints.nextReview()`, `endpoints.answerReview(answer)`; types `NextCard`, `CardView`, `ReviewCounts`, `AnswerRequest`, `Grade`, `GradeIntervals`, `RubySegment` (re-exported from `api/endpoints`); `queryKeys.reviewNext`; `useNextReview()`, `useAnswerReview()`; fixtures `segment(base, reading?, highlighted?)`, `makeKanaCard`, `makeKanjiCard`, `makeVocabCard`, `makeNextCard(card, overrides?)`.

- [ ] **Step 1: Write the fixtures and the tests**

Replace `frontend/src/test/fixtures.ts` with:

```typescript
import type { BuildStatus, CardView, NextCard, RubySegment } from '../api/endpoints';

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
```

Replace `frontend/src/api/endpoints.test.ts` with:

```typescript
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { session } from '../auth/session';
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
});
```

Replace `frontend/src/api/queries.test.tsx` with:

```tsx
import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { createTestQueryClient } from '../test/render';
import { makeBuildStatus, makeKanaCard, makeNextCard } from '../test/fixtures';
import { endpoints } from './endpoints';
import {
  BUILD_POLL_MS,
  buildJustFinished,
  pollInterval,
  queryKeys,
  useAnswerReview,
  useLatestBuild,
  useNextReview,
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

describe('useAnswerReview', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('writes the fresh counts into the cache and refetches the next card', async () => {
    const before = makeNextCard(makeKanaCard());
    const after = makeNextCard(null);
    const counts = { ...after.counts, due: { kana: 5, kanji: 0, vocab: 0 } };
    vi.spyOn(endpoints, 'answerReview').mockResolvedValue(counts);
    const fetchNext = vi.spyOn(endpoints, 'nextReview').mockResolvedValue(after);
    const queryClient = createTestQueryClient();
    queryClient.setQueryData(queryKeys.reviewNext, before);
    const next = renderHook(() => useNextReview(), { wrapper: wrapperFor(queryClient) });
    await waitFor(() => {
      expect(next.result.current.data).toEqual(after);
    });
    fetchNext.mockClear();
    const answer = renderHook(() => useAnswerReview(), { wrapper: wrapperFor(queryClient) });
    answer.result.current.mutate({
      item_id: 'kana:あ',
      direction: 'glyph_to_sound',
      grade: 3,
      expected_last_review: null,
    });
    await waitFor(() => {
      expect(answer.result.current.isSuccess).toBe(true);
    });
    expect(fetchNext).toHaveBeenCalledTimes(1);
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (in `frontend/`): `npx vitest run src/api`
Expected: FAIL (`endpoints.nextReview is not a function`, `useNextReview` is not exported, and similar).

- [ ] **Step 3: Write the implementation**

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

  /** Grade a card; the server answers with the fresh counts. */
  answerReview: (answer: AnswerRequest) =>
    request<ReviewCounts>('/reviews/answer', { method: 'POST', body: answer }),
};
```

Replace `frontend/src/api/queries.ts` with:

```typescript
import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';

import { endpoints, type BuildStatus, type NextCard } from './endpoints';

/** Query keys, shared by the hooks and by the code that updates the cache from the live stream. */
export const queryKeys = {
  contentSummary: ['content', 'summary'] as const,
  configCheck: ['admin', 'config-check'] as const,
  latestBuild: ['build', 'latest'] as const,
  reviewNext: ['review', 'next'] as const,
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
 * always asks the server (`staleTime: 0`); switching windows does not, so a card never changes
 * under the learner's hands.
 */
export function useNextReview() {
  return useQuery({
    queryKey: queryKeys.reviewNext,
    queryFn: endpoints.nextReview,
    staleTime: 0,
    refetchOnWindowFocus: false,
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run (in `frontend/`): `npx vitest run src/api`
Expected: PASS (5 files, 37 tests).

- [ ] **Step 5: Run the frontend gate**

Run (in `frontend/`): `npm run format:check && npm run lint && npm run build && npm run coverage`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/endpoints.ts frontend/src/api/endpoints.test.ts frontend/src/api/queries.ts frontend/src/api/queries.test.tsx frontend/src/test/fixtures.ts
git commit -m "feat: review endpoints, query hooks and card fixtures" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

Then open the draft PR (Task 0, Step 3).

---

## Task 2: Furigana, interval formatting and card faces

**Files:**
- Create: `frontend/src/components/Furigana.tsx`, `frontend/src/components/Furigana.module.css`, `frontend/src/components/Furigana.test.tsx`, `frontend/src/features/review/formatInterval.ts`, `frontend/src/features/review/formatInterval.test.ts`, `frontend/src/features/review/cardFaces.ts`, `frontend/src/features/review/cardFaces.test.ts`

**Interfaces:**
- Consumes: `CardView`, `RubySegment` (Task 1); fixtures from Task 1.
- Produces: `<Furigana segments={readonly RubySegment[]} />`; `formatInterval(seconds): string` and `formatDueTime(iso): string`; `cardFaces(card, { showFurigana, revealed }): { front: Face; back: Face }` with the exported types `Face`, `FaceLine`, `CardFaces`, `CardFaceOptions`.

- [ ] **Step 1: Write the tests**

Create `frontend/src/components/Furigana.test.tsx`:

```tsx
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { segment } from '../test/fixtures';
import { Furigana } from './Furigana';

describe('Furigana', () => {
  it('puts each reading in a ruby element over its base text', () => {
    const { container } = render(<Furigana segments={[segment('食', 'た'), segment('べる')]} />);
    const ruby = container.querySelector('ruby');
    expect(ruby).toHaveTextContent('食(た)');
    expect(ruby?.querySelector('rt')).toHaveTextContent('た');
    expect(container).toHaveTextContent('食(た)べる');
  });

  it('keeps the parentheses fallback for browsers without ruby support', () => {
    const { container } = render(<Furigana segments={[segment('日', 'ひ')]} />);
    expect(container.querySelectorAll('rp')).toHaveLength(2);
  });

  it('shows segments without a reading as plain text', () => {
    const { container } = render(
      <Furigana segments={[segment('を'), segment('。', ''), segment('ね')]} />,
    );
    expect(container.querySelector('ruby')).toBeNull();
    expect(container).toHaveTextContent('を。ね');
  });

  it('marks the whole run as Japanese and flags the highlighted segment', () => {
    const { container } = render(
      <Furigana segments={[segment('食べる', null, true), segment('よ')]} />,
    );
    expect(container.firstElementChild).toHaveAttribute('lang', 'ja');
    const spans = container.querySelectorAll('span span');
    expect(spans).toHaveLength(2);
    expect(spans[0]).toHaveAttribute('data-highlighted', 'true');
    expect(spans[1]).not.toHaveAttribute('data-highlighted');
  });
});
```

Create `frontend/src/features/review/formatInterval.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';

import { formatDueTime, formatInterval } from './formatInterval';

describe('formatInterval', () => {
  it.each([
    [0, '0 s'],
    [-5, '0 s'],
    [45, '45 s'],
    [60, '1 m'],
    [600, '10 m'],
    [3_600, '1 h'],
    [7_200, '2 h'],
    [86_400, '1 d'],
    [345_600, '4 d'],
    [2_592_000, '1 mo'],
    [7_776_000, '3 mo'],
    [31_536_000, '1 y'],
  ])('formats %i seconds as %s', (seconds, label) => {
    expect(formatInterval(seconds)).toBe(label);
  });
});

describe('formatDueTime', () => {
  it('formats an ISO instant with a date and a time', () => {
    const text = formatDueTime('2026-09-21T08:30:00Z');
    expect(text).toMatch(/2026/);
    expect(text).toMatch(/\d{1,2}:\d{2}/);
  });
});
```

Create `frontend/src/features/review/cardFaces.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';

import { makeKanaCard, makeKanjiCard, makeVocabCard, segment } from '../../test/fixtures';
import { cardFaces } from './cardFaces';

const OFF = { showFurigana: false, revealed: false };

describe('cardFaces: kana', () => {
  it('glyph to sound shows the character, then the romaji with script and group', () => {
    const { front, back } = cardFaces(makeKanaCard(), OFF);
    expect(front.main).toEqual({ text: 'あ', japanese: true, segments: null });
    expect(front.caption).toBe('Kana · Hiragana · New');
    expect(back.main).toEqual({ text: 'a', japanese: false, segments: null });
    expect(back.lines.map((line) => line.text)).toEqual(['Hiragana', 'a']);
  });

  it('sound to glyph swaps the sides', () => {
    const { front, back } = cardFaces(makeKanaCard({ direction: 'sound_to_glyph' }), OFF);
    expect(front.main.text).toBe('a');
    expect(back.main).toEqual({ text: 'あ', japanese: true, segments: null });
  });
});

describe('cardFaces: kanji', () => {
  it('kanji to meaning shows the meanings, with the readings underneath', () => {
    const { front, back } = cardFaces(makeKanjiCard(), OFF);
    expect(front.main.text).toBe('日');
    expect(front.caption).toBe('Kanji · N5');
    expect(back.main).toEqual({ text: 'day, sun', japanese: false, segments: null });
    expect(back.lines).toEqual([
      { label: 'On', text: 'ニチ、ジツ', japanese: true },
      { label: 'Kun', text: 'ひ、か', japanese: true },
    ]);
  });

  it('kanji to reading shows on and kun readings, with the meanings underneath', () => {
    const { back } = cardFaces(makeKanjiCard({ direction: 'kanji_to_reading' }), OFF);
    expect(back.main).toEqual({ text: 'ニチ、ジツ、ひ、か', japanese: true, segments: null });
    expect(back.lines).toEqual([{ label: 'Meanings', text: 'day, sun', japanese: false }]);
  });

  it('meaning to kanji asks with the meanings and answers with the kanji', () => {
    const { front, back } = cardFaces(makeKanjiCard({ direction: 'meaning_to_kanji' }), OFF);
    expect(front.main).toEqual({ text: 'day, sun', japanese: false, segments: null });
    expect(back.main).toEqual({ text: '日', japanese: true, segments: null });
  });

  it('leaves the level out for a kanji without one and skips empty reading lines', () => {
    const card = makeKanjiCard();
    const { front, back } = cardFaces(
      {
        ...card,
        kanji: card.kanji && { ...card.kanji, level: null, on_readings: [], kun_readings: ['ひ'] },
      },
      OFF,
    );
    expect(front.caption).toBe('Kanji');
    expect(back.lines).toEqual([{ label: 'Kun', text: 'ひ', japanese: true }]);
  });
});

describe('cardFaces: vocabulary', () => {
  it('recognition hides furigana on the front and shows it once flipped', () => {
    const front = cardFaces(makeVocabCard(), OFF).front;
    expect(front.main).toEqual({ text: '食べる', japanese: true, segments: null });
    expect(front.caption).toBe('Vocabulary · N5');
    const flipped = cardFaces(makeVocabCard(), { showFurigana: false, revealed: true }).front;
    expect(flipped.main.segments).toEqual([segment('食', 'た'), segment('べる')]);
  });

  it('recognition shows furigana on the front when the learner asks for it', () => {
    const { front } = cardFaces(makeVocabCard(), { showFurigana: true, revealed: false });
    expect(front.main.segments).not.toBeNull();
  });

  it('recognition answers with the meaning, reading, part of speech and the example sentence', () => {
    const { back } = cardFaces(makeVocabCard(), OFF);
    expect(back.main).toEqual({ text: 'to eat', japanese: false, segments: null });
    expect(back.lines).toEqual([
      { label: 'Reading', text: 'たべる', japanese: true },
      { label: 'Part of speech', text: 'verb, ichidan', japanese: false },
    ]);
    expect(back.sentence?.english).toBe('I eat breakfast every day.');
    expect(back.sentence?.segments).toHaveLength(5);
  });

  it('recall asks with the meaning and answers with the word and its furigana', () => {
    const { front, back } = cardFaces(makeVocabCard({ direction: 'recall' }), OFF);
    expect(front.main).toEqual({ text: 'to eat', japanese: false, segments: null });
    expect(front.lines).toEqual([
      { label: 'Part of speech', text: 'verb, ichidan', japanese: false },
    ]);
    expect(back.main.text).toBe('食べる');
    expect(back.main.segments).not.toBeNull();
    expect(back.lines).toEqual([{ label: 'Reading', text: 'たべる', japanese: true }]);
  });

  it('omits the example sentence and empty lines when the word has none', () => {
    const card = makeVocabCard();
    const { back } = cardFaces(
      { ...card, vocab: card.vocab && { ...card.vocab, sentence: null, part_of_speech: [] } },
      OFF,
    );
    expect(back.sentence).toBeNull();
    expect(back.lines).toEqual([{ label: 'Reading', text: 'たべる', japanese: true }]);
  });

  it('adds the additional definitions when there are some', () => {
    const card = makeVocabCard();
    const { back } = cardFaces(
      { ...card, vocab: card.vocab && { ...card.vocab, additional_definitions: 'to live on' } },
      OFF,
    );
    expect(back.lines).toContainEqual({ label: 'More', text: 'to live on', japanese: false });
  });
});

describe('cardFaces: new cards', () => {
  it('tags the front of an unseen card and leaves a seen card alone', () => {
    expect(cardFaces(makeKanaCard({ is_new: true }), OFF).front.caption).toBe(
      'Kana · Hiragana · New',
    );
    expect(cardFaces(makeKanaCard({ is_new: false }), OFF).front.caption).toBe('Kana · Hiragana');
  });

  it('tags a placeholder front too, without a leading separator', () => {
    const { front } = cardFaces(makeKanaCard({ kana: null, is_new: true }), OFF);
    expect(front.caption).toBe('New');
  });
});

describe('cardFaces: bad data', () => {
  it('shows a placeholder when the content of the card is missing', () => {
    const { front } = cardFaces(makeKanaCard({ kana: null }), OFF);
    expect(front.main.text).toBe('This card cannot be shown');
  });

  it('shows a placeholder for a direction that does not fit the type', () => {
    const { front } = cardFaces(makeVocabCard({ direction: 'glyph_to_sound' }), OFF);
    expect(front.main.text).toBe('This card cannot be shown');
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (in `frontend/`): `npx vitest run src/components/Furigana.test.tsx src/features/review`
Expected: FAIL (modules not found).

- [ ] **Step 3: Write the implementation**

Create `frontend/src/components/Furigana.tsx`:

```tsx
import type { RubySegment } from '../api/endpoints';
import classes from './Furigana.module.css';

/**
 * Japanese text with its readings above the kanji, from the API's ruby segments. Native
 * `<ruby>` with `<rp>` fallbacks, so browsers without ruby support show "kanji(reading)".
 * A highlighted segment (the word an example sentence is about) is emphasised.
 */
export function Furigana({ segments }: { segments: readonly RubySegment[] }) {
  return (
    <span lang="ja" className={classes.text}>
      {segments.map((segment, index) => {
        const highlighted = segment.highlighted === true;
        const key = `${index}:${segment.base}`;
        if (segment.reading === null || segment.reading === undefined || segment.reading === '') {
          return (
            <span
              key={key}
              className={highlighted ? classes.highlight : undefined}
              data-highlighted={highlighted ? 'true' : undefined}
            >
              {segment.base}
            </span>
          );
        }
        return (
          <ruby
            key={key}
            className={highlighted ? classes.highlight : undefined}
            data-highlighted={highlighted ? 'true' : undefined}
          >
            {segment.base}
            <rp>(</rp>
            <rt>{segment.reading}</rt>
            <rp>)</rp>
          </ruby>
        );
      })}
    </span>
  );
}
```

Create `frontend/src/components/Furigana.module.css`:

```css
.text {
  /* Room for the readings above the line, so lines of ruby text do not touch. */
  line-height: 2;
}

.text rt {
  font-size: 0.5em;
  font-weight: 400;
  color: var(--mantine-color-dimmed);
}

.highlight {
  font-weight: 700;
}
```

Create `frontend/src/features/review/formatInterval.ts`:

```typescript
const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
const MONTH = 30 * DAY;
const YEAR = 365 * DAY;

/** A projected interval in seconds as a short label for a grade button: "10 m", "4 d", "2 mo". */
export function formatInterval(seconds: number): string {
  const value = Math.max(0, seconds);
  if (value < MINUTE) return `${Math.round(value)} s`;
  if (value < HOUR) return `${Math.round(value / MINUTE)} m`;
  if (value < DAY) return `${Math.round(value / HOUR)} h`;
  if (value < MONTH) return `${Math.round(value / DAY)} d`;
  if (value < YEAR) return `${Math.round(value / MONTH)} mo`;
  return `${Math.round(value / YEAR)} y`;
}

/** When something is next due, in the reader's locale: "Sep 21, 2026, 8:30 AM". */
export function formatDueTime(iso: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(iso),
  );
}
```

Create `frontend/src/features/review/cardFaces.ts`:

```typescript
import type { CardView, RubySegment } from '../../api/endpoints';

/** One labelled line under the main text of a card face ("Reading", "Meaning"). */
export interface FaceLine {
  label: string;
  text: string;
  japanese: boolean;
}

/** What one side of a card shows. Pure data: `ReviewCard` turns it into markup. */
export interface Face {
  /** A small line above the main text, such as "Vocabulary · N5". */
  caption: string | null;
  /** The large text. With `segments` it is drawn as Japanese with furigana. */
  main: { text: string; japanese: boolean; segments: readonly RubySegment[] | null };
  lines: FaceLine[];
  /** An example sentence with furigana and its English. */
  sentence: { segments: readonly RubySegment[]; english: string } | null;
}

export interface CardFaces {
  front: Face;
  back: Face;
}

export interface CardFaceOptions {
  /** The learner turned furigana on for the front of the card. */
  showFurigana: boolean;
  /** The card has been flipped: readings are shown regardless of the switch. */
  revealed: boolean;
}

const SCRIPTS = { hira: 'Hiragana', kata: 'Katakana' } as const;
const LEVELS = { 1: 'N1', 2: 'N2', 3: 'N3', 4: 'N4', 5: 'N5' } as const;

function face(
  main: Face['main'],
  extras: { caption?: string; lines?: (FaceLine | null)[]; sentence?: Face['sentence'] } = {},
): Face {
  return {
    caption: extras.caption ?? null,
    main,
    lines: (extras.lines ?? []).filter((line): line is FaceLine => line !== null),
    sentence: extras.sentence ?? null,
  };
}

function plain(text: string): Face['main'] {
  return { text, japanese: false, segments: null };
}

function japanese(text: string, segments: readonly RubySegment[] | null = null): Face['main'] {
  return { text, japanese: true, segments };
}

function line(label: string, text: string, isJapanese = false): FaceLine | null {
  return text === '' ? null : { label, text, japanese: isJapanese };
}

function caption(kind: string, detail: string | null): string {
  return detail === null ? kind : `${kind} · ${detail}`;
}

const UNSUPPORTED: CardFaces = {
  front: face(plain('This card cannot be shown')),
  back: face(plain('Reload the page to continue.')),
};

function kanaFaces(card: CardView): CardFaces | null {
  const kana = card.kana;
  if (kana === null || kana === undefined) return null;
  const script = SCRIPTS[kana.script];
  const details = [line('Script', script), line('Group', kana.group)];
  const glyph = japanese(kana.char);
  const sound = plain(kana.romaji);
  if (card.direction === 'glyph_to_sound') {
    return {
      front: face(glyph, { caption: caption('Kana', script) }),
      back: face(sound, { lines: details }),
    };
  }
  return {
    front: face(sound, { caption: caption('Kana', script) }),
    back: face(glyph, { lines: details }),
  };
}

function kanjiFaces(card: CardView): CardFaces | null {
  const kanji = card.kanji;
  if (kanji === null || kanji === undefined) return null;
  const meanings = (kanji.meanings ?? []).join(', ');
  const on = (kanji.on_readings ?? []).join('、');
  const kun = (kanji.kun_readings ?? []).join('、');
  const level = kanji.level === null ? null : LEVELS[kanji.level];
  const captionText = caption('Kanji', level);
  const readings = [line('On', on, true), line('Kun', kun, true)];
  switch (card.direction) {
    case 'kanji_to_meaning':
      return {
        front: face(japanese(kanji.char), { caption: captionText }),
        back: face(plain(meanings), { lines: readings }),
      };
    case 'kanji_to_reading':
      return {
        front: face(japanese(kanji.char), { caption: captionText }),
        back: face(japanese([on, kun].filter((text) => text !== '').join('、')), {
          lines: [line('Meanings', meanings)],
        }),
      };
    case 'meaning_to_kanji':
      return {
        front: face(plain(meanings), { caption: captionText }),
        back: face(japanese(kanji.char), { lines: readings }),
      };
    default:
      return null;
  }
}

function vocabFaces(card: CardView, options: CardFaceOptions): CardFaces | null {
  const vocab = card.vocab;
  if (vocab === null || vocab === undefined) return null;
  const captionText = caption('Vocabulary', LEVELS[vocab.level]);
  const partOfSpeech = line('Part of speech', (vocab.part_of_speech ?? []).join(', '));
  const sentence =
    vocab.sentence === null || vocab.sentence === undefined
      ? null
      : { segments: vocab.sentence.segments, english: vocab.sentence.english };
  if (card.direction === 'recognition') {
    const withReadings = options.showFurigana || options.revealed;
    return {
      front: face(japanese(vocab.expression, withReadings ? vocab.reading_segments : null), {
        caption: captionText,
      }),
      back: face(plain(vocab.meaning), {
        lines: [
          line('Reading', vocab.reading, true),
          partOfSpeech,
          line('More', vocab.additional_definitions ?? ''),
        ],
        sentence,
      }),
    };
  }
  if (card.direction === 'recall') {
    return {
      front: face(plain(vocab.meaning), { caption: captionText, lines: [partOfSpeech] }),
      back: face(japanese(vocab.expression, vocab.reading_segments), {
        lines: [line('Reading', vocab.reading, true)],
        sentence,
      }),
    };
  }
  return null;
}

/** Mark the front of a card the learner has not seen before. */
function withNewTag(faces: CardFaces, isNew: boolean): CardFaces {
  if (!isNew) return faces;
  const caption = [faces.front.caption, 'New'].filter((part) => part !== null).join(' · ');
  return { ...faces, front: { ...faces.front, caption } };
}

function facesFor(card: CardView, options: CardFaceOptions): CardFaces {
  switch (card.item_type) {
    case 'kana':
      return kanaFaces(card) ?? UNSUPPORTED;
    case 'kanji':
      return kanjiFaces(card) ?? UNSUPPORTED;
    case 'vocab':
      return vocabFaces(card, options) ?? UNSUPPORTED;
  }
}

/**
 * The front and back of a card for its type and direction. Furigana is left off the front of
 * cards that test a word's reading or meaning unless the learner switched it on; after the flip
 * the readings are shown. An unseen card carries a "New" tag. A card whose content is missing gets
 * a harmless placeholder so a bad row never breaks the page.
 */
export function cardFaces(card: CardView, options: CardFaceOptions): CardFaces {
  return withNewTag(facesFor(card, options), card.is_new);
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run (in `frontend/`): `npx vitest run src/components/Furigana.test.tsx src/features/review`
Expected: PASS (3 files).

- [ ] **Step 5: Run the frontend gate**

Run (in `frontend/`): `npm run format:check && npm run lint && npm run build && npm run coverage`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/Furigana.tsx frontend/src/components/Furigana.module.css frontend/src/components/Furigana.test.tsx frontend/src/features/review/formatInterval.ts frontend/src/features/review/formatInterval.test.ts frontend/src/features/review/cardFaces.ts frontend/src/features/review/cardFaces.test.ts
git commit -m "feat: furigana component, interval formatting and card faces" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 3: The flip-and-grade mode

**Files:**
- Create: `frontend/src/features/review/review.module.css`, `ReviewCard.tsx`, `GradeBar.tsx`, `useReviewShortcuts.ts`, `useFuriganaPreference.ts`, `useFuriganaPreference.test.ts`, `reviewMode.ts`, `FlipMode.tsx`, `FlipMode.test.tsx` (all under `frontend/src/features/review/`)

**Interfaces:**
- Consumes: `cardFaces`, `formatInterval`, `Furigana` (Task 2); `CardView`, `Grade`, `GradeIntervals` (Task 1).
- Produces: `ReviewModeProps { card, showFurigana, pending, onReveal, onGrade }`; `<FlipMode {...ReviewModeProps} />` (mount it with a new `key` per card); `useFuriganaPreference(): [boolean, (value: boolean) => void]` and `FURIGANA_KEY`; `useReviewShortcuts({ revealed, pending, onFlip, onGrade })`; `<ReviewCard face answer? />`; `<GradeBar intervals disabled onGrade groupRef />`. Everything inside a mode that must receive keys sits under an element with the `data-review-controls` attribute (the shortcut hook only reacts to keys pressed on the page body or inside such an element).

- [ ] **Step 1: Write the tests**

Create `frontend/src/features/review/useFuriganaPreference.test.ts`:

```typescript
import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { FURIGANA_KEY, useFuriganaPreference } from './useFuriganaPreference';

describe('useFuriganaPreference', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('is off by default', () => {
    const { result } = renderHook(() => useFuriganaPreference());
    expect(result.current[0]).toBe(false);
  });

  it('remembers the choice in this browser', () => {
    const first = renderHook(() => useFuriganaPreference());
    act(() => {
      first.result.current[1](true);
    });
    expect(first.result.current[0]).toBe(true);
    expect(window.localStorage.getItem(FURIGANA_KEY)).toBe('true');

    const second = renderHook(() => useFuriganaPreference());
    expect(second.result.current[0]).toBe(true);
  });

  it('still works for this visit when storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    const { result } = renderHook(() => useFuriganaPreference());
    expect(result.current[0]).toBe(false);
    act(() => {
      result.current[1](true);
    });
    expect(result.current[0]).toBe(true);
  });
});
```

Create `frontend/src/features/review/FlipMode.test.tsx`:

```tsx
import { fireEvent, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { makeKanaCard, makeVocabCard } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { FlipMode } from './FlipMode';

function renderMode(overrides: Partial<Parameters<typeof FlipMode>[0]> = {}) {
  const onGrade = vi.fn();
  const onReveal = vi.fn();
  const view = renderWithProviders(
    <>
      <input aria-label="Notes" />
      <FlipMode
        card={makeKanaCard()}
        showFurigana={false}
        pending={false}
        onReveal={onReveal}
        onGrade={onGrade}
        {...overrides}
      />
    </>,
  );
  return { onGrade, onReveal, ...view };
}

describe('FlipMode', () => {
  it('shows the front with a focused "Show answer" button and hides the answer', () => {
    renderMode();
    expect(screen.getByText('あ')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Show answer' })).toHaveFocus();
    expect(screen.queryByRole('group', { name: 'Grade your answer' })).not.toBeInTheDocument();
    expect(screen.queryByText('Hiragana')).not.toBeInTheDocument();
  });

  it('flips on click, shows the answer and moves focus to the grade group', async () => {
    const user = userEvent.setup();
    const { onReveal } = renderMode();
    await user.click(screen.getByRole('button', { name: 'Show answer' }));
    expect(onReveal).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Hiragana')).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Grade your answer' })).toHaveFocus();
    expect(screen.queryByRole('button', { name: 'Show answer' })).not.toBeInTheDocument();
  });

  it.each([[' '], ['{Enter}']])('flips with the %j key', async (key) => {
    const user = userEvent.setup();
    const { onReveal } = renderMode();
    await user.keyboard(key);
    expect(onReveal).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('group', { name: 'Grade your answer' })).toBeInTheDocument();
  });

  it('labels each grade with its key and projected interval', async () => {
    const user = userEvent.setup();
    renderMode();
    await user.keyboard(' ');
    for (const name of ['Again · 1 m', 'Hard · 10 m', 'Good · 1 d', 'Easy · 4 d']) {
      expect(screen.getByRole('button', { name })).toBeEnabled();
    }
  });

  it.each([
    ['1', 1],
    ['2', 2],
    ['3', 3],
    ['4', 4],
  ])('grades with the %s key once flipped', async (key, grade) => {
    const user = userEvent.setup();
    const { onGrade } = renderMode();
    await user.keyboard(' ');
    await user.keyboard(key);
    expect(onGrade).toHaveBeenCalledExactlyOnceWith(grade);
  });

  it('grades with a click on a button', async () => {
    const user = userEvent.setup();
    const { onGrade } = renderMode();
    await user.keyboard(' ');
    await user.click(screen.getByRole('button', { name: /^Hard/ }));
    expect(onGrade).toHaveBeenCalledExactlyOnceWith(2);
  });

  it('ignores grade keys before the card is flipped', async () => {
    const user = userEvent.setup();
    const { onGrade } = renderMode();
    await user.keyboard('3');
    expect(onGrade).not.toHaveBeenCalled();
    expect(screen.queryByRole('group', { name: 'Grade your answer' })).not.toBeInTheDocument();
  });

  it('ignores keys with a modifier held', async () => {
    const user = userEvent.setup();
    const { onGrade } = renderMode();
    await user.keyboard(' ');
    await user.keyboard('{Control>}3{/Control}');
    await user.keyboard('{Meta>}3{/Meta}');
    await user.keyboard('{Alt>}3{/Alt}');
    expect(onGrade).not.toHaveBeenCalled();
  });

  it('ignores a key that is being held down (auto-repeat)', async () => {
    const user = userEvent.setup();
    const { onGrade } = renderMode();
    await user.keyboard(' ');
    fireEvent.keyDown(document.body, { key: '3', repeat: true });
    expect(onGrade).not.toHaveBeenCalled();
  });

  it('ignores keys while an input method is composing', async () => {
    const user = userEvent.setup();
    const { onGrade } = renderMode();
    await user.keyboard(' ');
    fireEvent.keyDown(document.body, { key: '3', isComposing: true });
    expect(onGrade).not.toHaveBeenCalled();
  });

  it('leaves keys alone when a text field has focus', async () => {
    const user = userEvent.setup();
    const { onGrade, onReveal } = renderMode();
    await user.click(screen.getByRole('textbox', { name: 'Notes' }));
    await user.keyboard(' 3{Enter}');
    expect(onReveal).not.toHaveBeenCalled();
    expect(onGrade).not.toHaveBeenCalled();
  });

  it('ignores keys and disables the buttons while an answer is pending', async () => {
    const user = userEvent.setup();
    const onGrade = vi.fn();
    function Harness() {
      const [pending, setPending] = useState(false);
      return (
        <div data-review-controls>
          <button
            type="button"
            onClick={() => {
              setPending((value) => !value);
            }}
          >
            Toggle pending
          </button>
          <FlipMode
            card={makeKanaCard()}
            showFurigana={false}
            pending={pending}
            onReveal={vi.fn()}
            onGrade={onGrade}
          />
        </div>
      );
    }
    renderWithProviders(<Harness />);
    await user.keyboard(' ');
    await user.click(screen.getByRole('button', { name: 'Toggle pending' }));
    expect(screen.getByRole('button', { name: /^Good/ })).toBeDisabled();
    await user.keyboard('3');
    expect(onGrade).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: 'Toggle pending' }));
    await user.keyboard('3');
    expect(onGrade).toHaveBeenCalledExactlyOnceWith(3);
  });

  it('shows the readings on the front of a vocabulary card only when asked, or after the flip', async () => {
    const user = userEvent.setup();
    const card = makeVocabCard();
    const { container, unmount } = renderMode({ card });
    expect(container.querySelector('ruby')).toBeNull();
    await user.keyboard(' ');
    expect(container.querySelector('ruby')).not.toBeNull();
    unmount();

    const shown = renderMode({ card, showFurigana: true });
    expect(shown.container.querySelector('ruby')).not.toBeNull();
    expect(screen.queryByText('to eat')).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (in `frontend/`): `npx vitest run src/features/review/FlipMode.test.tsx src/features/review/useFuriganaPreference.test.ts`
Expected: FAIL (modules not found).

- [ ] **Step 3: Write the implementation**

Create `frontend/src/features/review/review.module.css`:

```css
/* The study surface: large, calm, centred. Colours come from Mantine variables so light and dark
   mode both work. */

.card {
  max-width: 40rem;
  margin-inline: auto;
  padding-block: var(--mantine-spacing-lg);
  text-align: center;
}

.caption {
  margin-bottom: var(--mantine-spacing-xs);
  font-size: var(--mantine-font-size-xs);
  letter-spacing: 0.04em;
  color: var(--mantine-color-dimmed);
}

.mainJapanese {
  font-size: clamp(2.5rem, 12vw, 5rem);
  font-weight: 500;
  line-height: 1.6;
}

.mainLatin {
  font-size: clamp(1.5rem, 6vw, 2.25rem);
  line-height: 1.4;
}

.lines {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: var(--mantine-spacing-xs) var(--mantine-spacing-md);
  margin: var(--mantine-spacing-md) auto 0;
  max-width: 28rem;
  text-align: start;
}

.lines dt {
  color: var(--mantine-color-dimmed);
  font-size: var(--mantine-font-size-sm);
}

.lines dd {
  margin: 0;
}

.sentence {
  margin-top: var(--mantine-spacing-md);
  font-size: 1.25rem;
  line-height: 2.2;
}

.english {
  color: var(--mantine-color-dimmed);
  font-size: var(--mantine-font-size-sm);
}

.answer {
  margin-top: var(--mantine-spacing-lg);
  padding-top: var(--mantine-spacing-lg);
  border-top: 1px solid var(--mantine-color-default-border);
}

@media (prefers-reduced-motion: no-preference) {
  .answer {
    animation: reveal 150ms ease-out;
  }
}

@keyframes reveal {
  from {
    opacity: 0;
    transform: translateY(4px);
  }

  to {
    opacity: 1;
    transform: none;
  }
}

.key {
  margin-inline-end: var(--mantine-spacing-xs);
  font-family: var(--mantine-font-family-monospace);
  font-size: var(--mantine-font-size-xs);
  opacity: 0.7;
}

.grades:focus {
  outline: none;
}
```

Create `frontend/src/features/review/ReviewCard.tsx`:

```tsx
import { Furigana } from '../../components/Furigana';
import type { Face } from './cardFaces';
import classes from './review.module.css';

/** One side of a card: an optional caption, the main text, labelled lines and the example. */
export function ReviewCard({ face, answer = false }: { face: Face; answer?: boolean }) {
  const { caption, main, lines, sentence } = face;
  return (
    <section className={answer ? `${classes.card} ${classes.answer}` : classes.card}>
      {caption !== null && <div className={classes.caption}>{caption}</div>}
      <div className={main.japanese ? classes.mainJapanese : classes.mainLatin}>
        {main.segments !== null ? (
          <Furigana segments={main.segments} />
        ) : main.japanese ? (
          <span lang="ja">{main.text}</span>
        ) : (
          main.text
        )}
      </div>
      {lines.length > 0 && (
        <dl className={classes.lines}>
          {lines.map((line) => (
            <div key={line.label} style={{ display: 'contents' }}>
              <dt>{line.label}</dt>
              <dd lang={line.japanese ? 'ja' : undefined}>{line.text}</dd>
            </div>
          ))}
        </dl>
      )}
      {sentence !== null && (
        <div className={classes.sentence}>
          <Furigana segments={sentence.segments} />
          <div className={classes.english}>{sentence.english}</div>
        </div>
      )}
    </section>
  );
}
```

Create `frontend/src/features/review/GradeBar.tsx`:

```tsx
import { Button, SimpleGrid } from '@mantine/core';
import type { Ref } from 'react';

import type { Grade, GradeIntervals } from '../../api/endpoints';
import { formatInterval } from './formatInterval';
import classes from './review.module.css';

interface GradeChoice {
  grade: Grade;
  label: string;
  key: string;
  interval: keyof GradeIntervals;
}

const GRADES: readonly GradeChoice[] = [
  { grade: 1, label: 'Again', key: '1', interval: 'again' },
  { grade: 2, label: 'Hard', key: '2', interval: 'hard' },
  { grade: 3, label: 'Good', key: '3', interval: 'good' },
  { grade: 4, label: 'Easy', key: '4', interval: 'easy' },
];

interface GradeBarProps {
  intervals: GradeIntervals;
  disabled: boolean;
  onGrade: (grade: Grade) => void;
  /**
   * The group itself takes focus after the flip. It is not a button, so a key still held down
   * from the flip cannot press a grade.
   */
  groupRef: Ref<HTMLDivElement>;
}

/** The four grade buttons with their keys and the projected next interval of each. */
export function GradeBar({ intervals, disabled, onGrade, groupRef }: GradeBarProps) {
  return (
    <div
      ref={groupRef}
      role="group"
      aria-label="Grade your answer"
      tabIndex={-1}
      className={classes.grades}
      data-review-controls
    >
      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="xs">
        {GRADES.map(({ grade, label, key, interval }) => (
          <Button
            key={grade}
            variant={grade === 3 ? 'filled' : 'light'}
            color={grade === 1 ? 'red' : undefined}
            size="md"
            disabled={disabled}
            aria-keyshortcuts={key}
            onClick={() => {
              onGrade(grade);
            }}
          >
            <span className={classes.key} aria-hidden="true">
              {key}
            </span>
            {label} · {formatInterval(intervals[interval])}
          </Button>
        ))}
      </SimpleGrid>
    </div>
  );
}
```

Create `frontend/src/features/review/useReviewShortcuts.ts`:

```typescript
import { useEffect } from 'react';

import type { Grade } from '../../api/endpoints';

const GRADE_KEYS: Readonly<Record<string, Grade>> = { '1': 1, '2': 2, '3': 3, '4': 4 };

/**
 * Whether a key press belongs to the review: it happened on the page itself or inside the review
 * controls, not in a text field, a link, or the header switch (which keep their own keys).
 */
function isForReview(target: EventTarget | null): boolean {
  if (target === document.body || target === document.documentElement) return true;
  return target instanceof Element && target.closest('[data-review-controls]') !== null;
}

interface Shortcuts {
  revealed: boolean;
  pending: boolean;
  onFlip: () => void;
  onGrade: (grade: Grade) => void;
}

/**
 * Space or Enter flips the card; 1 to 4 grade it once it is flipped. Ignored with a modifier key,
 * while an input method is composing, for auto-repeated keys (holding a key must not grade
 * several cards) and while an answer is being saved.
 */
export function useReviewShortcuts({ revealed, pending, onFlip, onGrade }: Shortcuts): void {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.repeat || event.isComposing) return;
      if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
      if (event.defaultPrevented || pending || !isForReview(event.target)) return;

      if (event.key === ' ' || event.key === 'Enter') {
        if (!revealed) {
          event.preventDefault();
          onFlip();
        }
        return;
      }
      const grade = GRADE_KEYS[event.key];
      if (grade !== undefined && revealed) {
        event.preventDefault();
        onGrade(grade);
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [revealed, pending, onFlip, onGrade]);
}
```

Create `frontend/src/features/review/useFuriganaPreference.ts`:

```typescript
import { useCallback, useState } from 'react';

/** Where the "show furigana on the front" choice is remembered: this browser only. */
export const FURIGANA_KEY = 'bunsho.show_furigana';

function read(): boolean {
  try {
    return window.localStorage.getItem(FURIGANA_KEY) === 'true';
  } catch {
    return false;
  }
}

/** The furigana switch and its setter. Blocked storage means "not remembered", never an error. */
export function useFuriganaPreference(): [boolean, (value: boolean) => void] {
  const [value, setValue] = useState(read);
  const update = useCallback((next: boolean) => {
    setValue(next);
    try {
      window.localStorage.setItem(FURIGANA_KEY, String(next));
    } catch {
      // Not remembered; the switch still works for this visit.
    }
  }, []);
  return [value, update];
}
```

Create `frontend/src/features/review/reviewMode.ts`:

```typescript
import type { CardView, Grade } from '../../api/endpoints';

/**
 * What a way of answering a card (flip and self-grade today; typed answer or multiple choice
 * later) receives. A mode shows the card, decides when it is answered, and reports a grade; the
 * page owns fetching, timing and errors.
 */
export interface ReviewModeProps {
  card: CardView;
  showFurigana: boolean;
  /** An answer is being saved (or the next card is loading): ignore input. */
  pending: boolean;
  /** The learner has seen the answer (used for the screen-reader announcement). */
  onReveal: () => void;
  onGrade: (grade: Grade) => void;
}
```

Create `frontend/src/features/review/FlipMode.tsx`:

```tsx
import { Button } from '@mantine/core';
import { useCallback, useEffect, useRef, useState } from 'react';

import { cardFaces } from './cardFaces';
import { GradeBar } from './GradeBar';
import { ReviewCard } from './ReviewCard';
import type { ReviewModeProps } from './reviewMode';
import { useReviewShortcuts } from './useReviewShortcuts';

/** Flip the card, then grade yourself. Mount it with a new `key` for every card. */
export function FlipMode({ card, showFurigana, pending, onReveal, onGrade }: ReviewModeProps) {
  const [revealed, setRevealed] = useState(false);
  const flipRef = useRef<HTMLButtonElement>(null);
  const gradesRef = useRef<HTMLDivElement>(null);

  const flip = useCallback(() => {
    setRevealed(true);
    onReveal();
  }, [onReveal]);

  useReviewShortcuts({ revealed, pending, onFlip: flip, onGrade });

  useEffect(() => {
    flipRef.current?.focus();
  }, []);
  useEffect(() => {
    if (revealed) gradesRef.current?.focus();
  }, [revealed]);

  const faces = cardFaces(card, { showFurigana, revealed });

  return (
    <div data-review-controls>
      <ReviewCard face={faces.front} />
      {revealed ? (
        <>
          <ReviewCard face={faces.back} answer />
          <GradeBar
            intervals={card.intervals}
            disabled={pending}
            onGrade={onGrade}
            groupRef={gradesRef}
          />
        </>
      ) : (
        <Button ref={flipRef} fullWidth size="md" onClick={flip} aria-keyshortcuts="Space Enter">
          Show answer
        </Button>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run (in `frontend/`): `npx vitest run src/features/review`
Expected: PASS (4 files). Run the same command 10 times in a row (`for i in $(seq 10); do npx vitest run src/features/review || break; done`): every run must pass.

- [ ] **Step 5: Run the frontend gate**

Run (in `frontend/`): `npm run format:check && npm run lint && npm run build && npm run coverage`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/review/review.module.css frontend/src/features/review/ReviewCard.tsx frontend/src/features/review/GradeBar.tsx frontend/src/features/review/useReviewShortcuts.ts frontend/src/features/review/useFuriganaPreference.ts frontend/src/features/review/useFuriganaPreference.test.ts frontend/src/features/review/reviewMode.ts frontend/src/features/review/FlipMode.tsx frontend/src/features/review/FlipMode.test.tsx
git commit -m "feat: flip-and-grade review mode with keyboard shortcuts" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 4: The review page

**Files:**
- Create: `frontend/src/features/review/ReviewFinished.tsx`, `frontend/src/features/review/ReviewPage.tsx`, `frontend/src/features/review/ReviewPage.test.tsx`

**Interfaces:**
- Consumes: `useNextReview`, `useAnswerReview` (Task 1); `FlipMode`, `useFuriganaPreference`, `formatDueTime` (Tasks 2-3); `ApiError`, `messageFor` (existing, `api/errors.ts`); Mantine `notifications`.
- Produces: `<ReviewPage />` (no props; route `/review`), `<ReviewDone data={NextCard} />`, `<ReviewNotBuilt />`.

- [ ] **Step 1: Write the tests**

Create `frontend/src/features/review/ReviewPage.test.tsx`:

```tsx
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Route, Routes } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { NextCard } from '../../api/endpoints';
import { session } from '../../auth/session';
import { makeKanaCard, makeKanjiCard, makeNextCard, makeVocabCard } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { FURIGANA_KEY } from './useFuriganaPreference';
import { ReviewPage } from './ReviewPage';

const COUNTS = {
  due: { kana: 0, kanji: 0, vocab: 0 },
  new_remaining: { kana: 0, kanji: 0, vocab: 0 },
};

/** Serve `GET /reviews/next` from a queue: every accepted answer moves on to the next entry. */
function serveReviews(queue: NextCard[], answerStatus = 200) {
  const posted: Record<string, unknown>[] = [];
  let index = 0;
  server.use(
    http.get('/api/v1/reviews/next', () =>
      HttpResponse.json(queue[Math.min(index, queue.length - 1)]),
    ),
    http.post('/api/v1/reviews/answer', async ({ request }) => {
      posted.push((await request.json()) as Record<string, unknown>);
      if (answerStatus !== 200) {
        // A 409 means the card was answered elsewhere, so the server has moved on.
        if (answerStatus === 409) index += 1;
        return HttpResponse.json({ detail: 'stale' }, { status: answerStatus });
      }
      index += 1;
      return HttpResponse.json(COUNTS);
    }),
  );
  return { posted };
}

function renderReview() {
  return renderWithProviders(
    <Routes>
      <Route path="/" element={<p>Dashboard</p>} />
      <Route path="/review" element={<ReviewPage />} />
      <Route path="/build" element={<p>Build page</p>} />
    </Routes>,
    { initialEntries: ['/review'] },
  );
}

describe('ReviewPage', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  afterEach(() => {
    vi.useRealTimers();
    window.localStorage.clear();
  });

  it('shows the first card and the counts, then the next card after a grade', async () => {
    const user = userEvent.setup();
    const first = makeNextCard(makeKanaCard(), {
      counts: { ...COUNTS, due: { kana: 3, kanji: 2, vocab: 0 } },
    });
    const second = makeNextCard(makeKanjiCard());
    const { posted } = serveReviews([first, second]);
    renderReview();

    expect(await screen.findByText('あ')).toBeInTheDocument();
    expect(screen.getByText('5 due · 0 new available')).toBeInTheDocument();

    await user.keyboard(' ');
    await user.keyboard('3');

    expect(await screen.findByText('日')).toBeInTheDocument();
    expect(posted).toHaveLength(1);
    expect(posted[0]).toMatchObject({
      item_id: 'kana:あ',
      direction: 'glyph_to_sound',
      grade: 3,
      expected_last_review: null,
    });
  });

  it('sends the opaque expected_last_review exactly as received', async () => {
    const user = userEvent.setup();
    const token = '2026-09-19T09:30:00.123456+00:00';
    const { posted } = serveReviews([
      makeNextCard(makeVocabCard({ expected_last_review: token })),
      makeNextCard(null),
    ]);
    renderReview();
    await screen.findByRole('button', { name: 'Show answer' });
    await user.keyboard(' ');
    await user.click(screen.getByRole('button', { name: /^Easy/ }));
    await screen.findByText("You're done for now");
    expect(posted[0]).toMatchObject({ expected_last_review: token, grade: 4 });
  });

  it('measures how long the card was on screen and keeps it within the API limit', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-09-20T10:00:00Z'));
    const user = userEvent.setup();
    const { posted } = serveReviews([
      makeNextCard(makeKanaCard()),
      makeNextCard(
        makeKanaCard({ item_id: 'kana:い', expected_last_review: '2026-09-20T10:00:06Z' }),
      ),
      makeNextCard(null),
    ]);
    renderReview();
    await screen.findByRole('button', { name: 'Show answer' });

    vi.setSystemTime(new Date('2026-09-20T10:00:05.500Z'));
    await user.keyboard(' ');
    await user.keyboard('2');
    await waitFor(() => {
      expect(posted).toHaveLength(1);
    });
    expect(posted[0]?.duration_ms).toBe(5500);

    await screen.findByRole('button', { name: 'Show answer' });
    vi.setSystemTime(new Date('2026-09-20T13:00:00Z'));
    await user.keyboard(' ');
    await user.keyboard('3');
    await waitFor(() => {
      expect(posted).toHaveLength(2);
    });
    expect(posted[1]?.duration_ms).toBe(3_600_000);
  });

  it('sends one grade only, however many keys are pressed while it is being saved', async () => {
    const user = userEvent.setup();
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const posted: unknown[] = [];
    server.use(
      http.get('/api/v1/reviews/next', () => HttpResponse.json(makeNextCard(makeKanaCard()))),
      http.post('/api/v1/reviews/answer', async ({ request }) => {
        posted.push(await request.json());
        await gate;
        return HttpResponse.json(COUNTS);
      }),
    );
    renderReview();
    await screen.findByRole('button', { name: 'Show answer' });
    await user.keyboard(' ');
    await user.keyboard('3');
    await user.keyboard('3');
    await user.keyboard('1');
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^Good/ })).toBeDisabled();
    });
    expect(posted).toHaveLength(1);
    release();
  });

  it('loads the next card with a notice when the card changed elsewhere (409)', async () => {
    const user = userEvent.setup();
    const stale = makeNextCard(makeKanaCard());
    const fresh = makeNextCard(makeKanjiCard());
    serveReviews([stale, fresh], 409);
    renderReview();
    await screen.findByText('あ');
    await user.keyboard(' ');
    await user.keyboard('3');

    expect(
      await screen.findByText('That card changed elsewhere: loading the next one.'),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('日')).toBeInTheDocument();
    });
    expect(screen.queryByText("Couldn't save your answer")).not.toBeInTheDocument();
  });

  it('keeps the card and offers a retry when the answer could not be saved', async () => {
    const user = userEvent.setup();
    let calls = 0;
    server.use(
      http.get('/api/v1/reviews/next', () => HttpResponse.json(makeNextCard(makeKanaCard()))),
      http.post('/api/v1/reviews/answer', () => {
        calls += 1;
        return calls === 1 ? HttpResponse.error() : HttpResponse.json(COUNTS);
      }),
    );
    renderReview();
    await screen.findByText('あ');
    await user.keyboard(' ');
    await user.keyboard('3');

    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText("Couldn't save your answer")).toBeInTheDocument();
    expect(screen.getByText('あ')).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Grade your answer' })).toBeInTheDocument();

    await user.click(within(alert).getByRole('button', { name: 'Try again' }));
    await waitFor(() => {
      expect(calls).toBe(2);
    });
    await waitFor(() => {
      expect(screen.queryByText("Couldn't save your answer")).not.toBeInTheDocument();
    });
  });

  it('sends the person to the Build screen when the content is not built (503)', async () => {
    server.use(
      http.get('/api/v1/reviews/next', () =>
        HttpResponse.json({ detail: 'content is not built' }, { status: 503 }),
      ),
    );
    renderReview();
    expect(await screen.findByText('Nothing to study yet')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Build your content' })).toHaveAttribute(
      'href',
      '/build',
    );
  });

  it('explains a failed load and can try again', async () => {
    const user = userEvent.setup();
    let calls = 0;
    server.use(
      http.get('/api/v1/reviews/next', () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json({ detail: 'boom' }, { status: 500 })
          : HttpResponse.json(makeNextCard(makeKanaCard()));
      }),
    );
    renderReview();
    expect(await screen.findByText("Couldn't load the next card")).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('あ')).toBeInTheDocument();
  });

  it('shows the finished state with the next due time and a link back', async () => {
    serveReviews([makeNextCard(null, { next_due_at: '2026-09-21T08:30:00Z' })]);
    renderReview();
    expect(await screen.findByText("You're done for now")).toBeInTheDocument();
    expect(screen.getByText(/Next card due .*2026/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to the dashboard' })).toHaveAttribute(
      'href',
      '/',
    );
  });

  it('leaves out the next due time when nothing is scheduled', async () => {
    serveReviews([makeNextCard(null)]);
    renderReview();
    expect(await screen.findByText("You're done for now")).toBeInTheDocument();
    expect(screen.queryByText(/Next card due/)).not.toBeInTheDocument();
  });

  it('remembers the furigana switch and shows readings on the front when it is on', async () => {
    const user = userEvent.setup();
    serveReviews([makeNextCard(makeVocabCard())]);
    const { container } = renderReview();
    await screen.findByRole('button', { name: 'Show answer' });
    expect(container.querySelector('ruby')).toBeNull();

    await user.click(screen.getByRole('switch', { name: 'Show furigana' }));
    expect(container.querySelector('ruby')).not.toBeNull();
    expect(window.localStorage.getItem(FURIGANA_KEY)).toBe('true');
  });

  it('announces the state through one persistent status region', async () => {
    const user = userEvent.setup();
    serveReviews([makeNextCard(makeKanaCard()), makeNextCard(null)]);
    renderReview();
    const status = screen.getByRole('status');
    expect(status).toBeEmptyDOMElement();

    await waitFor(() => {
      expect(status).toHaveTextContent('Card shown');
    });
    await user.keyboard(' ');
    expect(status).toHaveTextContent('Answer shown');
    expect(screen.getByRole('status')).toBe(status);
    await user.keyboard('3');
    await waitFor(() => {
      expect(status).toHaveTextContent('Nothing due right now');
    });
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (in `frontend/`): `npx vitest run src/features/review/ReviewPage.test.tsx`
Expected: FAIL (`./ReviewPage` not found).

- [ ] **Step 3: Write the implementation**

Create `frontend/src/features/review/ReviewFinished.tsx`:

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

Create `frontend/src/features/review/ReviewPage.tsx`:

```tsx
import {
  Alert,
  Button,
  Group,
  Skeleton,
  Stack,
  Switch,
  Text,
  Title,
  VisuallyHidden,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useRef, useState } from 'react';

import type { CardView, Grade, ReviewCounts } from '../../api/endpoints';
import { ApiError, messageFor } from '../../api/errors';
import { useAnswerReview, useNextReview } from '../../api/queries';
import { FlipMode } from './FlipMode';
import { useFuriganaPreference } from './useFuriganaPreference';
import { ReviewDone, ReviewNotBuilt } from './ReviewFinished';

/** The API accepts a duration up to one hour. */
const MAX_DURATION_MS = 3_600_000;

/** A different card, or the same card after another review: a new key remounts the mode. */
function cardKey(card: CardView): string {
  return `${card.item_id}|${card.direction}|${card.expected_last_review ?? 'new'}`;
}

function isStale(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409;
}

function isNotBuilt(error: unknown): boolean {
  return error instanceof ApiError && error.status === 503;
}

function total(counts: ReviewCounts['due']): number {
  return counts.kana + counts.kanji + counts.vocab;
}

/** The sentence a screen reader hears. Static text only: nothing here changes while it is read. */
function announcement(state: {
  hasData: boolean;
  card: CardView | null;
  saving: boolean;
  revealed: boolean;
}): string {
  if (!state.hasData) return '';
  if (state.card === null) return 'Nothing due right now';
  if (state.saving) return 'Saving answer';
  return state.revealed ? 'Answer shown' : 'Card shown';
}

/** The study session: one card at a time, flip, grade, next. */
export function ReviewPage() {
  const next = useNextReview();
  const answer = useAnswerReview();
  const [showFurigana, setShowFurigana] = useFuriganaPreference();
  const [revealedKey, setRevealedKey] = useState<string | null>(null);
  const shownAt = useRef(0);

  const { refetch } = next;
  const { mutate: sendAnswer, reset: resetAnswer } = answer;

  const data = next.data;
  const card = data?.card ?? null;
  const key = card === null ? null : cardKey(card);

  // The clock for `duration_ms` starts when a card is put on screen.
  useEffect(() => {
    shownAt.current = Date.now();
  }, [key]);

  const reveal = useCallback(() => {
    setRevealedKey(key);
  }, [key]);

  const grade = useCallback(
    (value: Grade) => {
      if (card === null) return;
      const duration = Math.min(Math.max(Date.now() - shownAt.current, 0), MAX_DURATION_MS);
      sendAnswer(
        {
          item_id: card.item_id,
          direction: card.direction,
          grade: value,
          expected_last_review: card.expected_last_review,
          duration_ms: duration,
        },
        {
          onError: (error) => {
            if (!isStale(error)) return;
            // The card changed elsewhere (another tab or device): drop it and load what is next.
            notifications.show({ message: 'That card changed elsewhere: loading the next one.' });
            void refetch().finally(resetAnswer);
          },
        },
      );
    },
    [card, sendAnswer, refetch, resetAnswer],
  );

  const busy = answer.isPending || next.isFetching;
  const answerFailed = answer.isError && !isStale(answer.error);

  let body;
  if (next.isPending) {
    body = <Skeleton height={240} />;
  } else if (next.isError) {
    body = isNotBuilt(next.error) ? (
      <ReviewNotBuilt />
    ) : (
      <Alert color="red" title="Couldn't load the next card">
        <Text size="sm">{messageFor(next.error)}</Text>
        <Button
          mt="sm"
          size="xs"
          onClick={() => {
            void refetch();
          }}
        >
          Try again
        </Button>
      </Alert>
    );
  } else if (card === null) {
    body = <ReviewDone data={next.data} />;
  } else {
    body = (
      <Stack gap="md">
        <FlipMode
          key={key}
          card={card}
          showFurigana={showFurigana}
          pending={busy}
          onReveal={reveal}
          onGrade={grade}
        />
        {answerFailed && (
          <Alert color="red" title="Couldn't save your answer">
            <Text size="sm">{messageFor(answer.error)}</Text>
            <Button
              mt="sm"
              size="xs"
              disabled={busy}
              onClick={() => {
                if (answer.variables !== undefined) sendAnswer(answer.variables);
              }}
            >
              Try again
            </Button>
          </Alert>
        )}
      </Stack>
    );
  }

  return (
    <Stack gap="md" maw={720} mx="auto">
      <Group justify="space-between" align="center">
        <Title order={2}>Study</Title>
        <Switch
          label="Show furigana"
          checked={showFurigana}
          onChange={(event) => {
            setShowFurigana(event.currentTarget.checked);
          }}
        />
      </Group>
      {data !== undefined && (
        <Text size="sm" c="dimmed">
          {total(data.counts.due)} due · {total(data.counts.new_remaining)} new available
        </Text>
      )}
      <VisuallyHidden role="status" aria-live="polite" aria-atomic>
        {announcement({
          hasData: data !== undefined && !next.isError,
          card,
          saving: answer.isPending,
          revealed: key !== null && revealedKey === key,
        })}
      </VisuallyHidden>
      {body}
    </Stack>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run (in `frontend/`): `npx vitest run src/features/review`
Expected: PASS (5 files). Run `for i in $(seq 10); do npx vitest run src/features/review || break; done`: every run must pass (the duration test fakes only `Date`; the others use real timers with MSW).

- [ ] **Step 5: Run the frontend gate**

Run (in `frontend/`): `npm run format:check && npm run lint && npm run build && npm run coverage`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/review/ReviewFinished.tsx frontend/src/features/review/ReviewPage.tsx frontend/src/features/review/ReviewPage.test.tsx
git commit -m "feat: the review page with grading, timing and error handling" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 5: Dashboard, Study link and lazy routes

**Files:**
- Create: `frontend/src/features/home/StudyPanel.tsx`, `frontend/src/features/home/StudyPanel.test.tsx`, `frontend/src/components/PageLoader.tsx`
- Modify: `frontend/src/features/home/HomePage.tsx`, `frontend/src/features/home/HomePage.test.tsx`, `frontend/src/components/AppLayout.tsx`, `frontend/src/components/AppLayout.test.tsx`, `frontend/src/App.tsx`, `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: `useNextReview` (Task 1), `formatDueTime` (Task 2), `ReviewPage` (Task 4).
- Produces: `<StudyPanel />`; `<PageLoader />` (a `role="status"` loader named "Loading page"); a `Study` navigation link to `/review`; the routes `/`, `/review`, `/build` loaded with `React.lazy` under a `Suspense` inside `AppLayout` (so the shell stays on screen while a page loads and a failed chunk is caught by the existing `ErrorBoundary`).

- [ ] **Step 1: Write the tests**

Create `frontend/src/features/home/StudyPanel.test.tsx`:

```tsx
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it } from 'vitest';

import { session } from '../../auth/session';
import { makeKanaCard, makeNextCard } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { StudyPanel } from './StudyPanel';

function renderPanel() {
  return renderWithProviders(
    <Routes>
      <Route index element={<StudyPanel />} />
      <Route path="review" element={<p>Review page</p>} />
    </Routes>,
  );
}

describe('StudyPanel', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  it('shows what is due and what is new for each type, with a way to start', async () => {
    const user = userEvent.setup();
    const payload = makeNextCard(makeKanaCard(), {
      counts: {
        due: { kana: 4, kanji: 12, vocab: 30 },
        new_remaining: { kana: 20, kanji: 15, vocab: 0 },
      },
    });
    server.use(http.get('/api/v1/reviews/next', () => HttpResponse.json(payload)));
    renderPanel();

    expect(await screen.findByRole('heading', { name: 'Today' })).toBeInTheDocument();
    const kanji = screen.getByText('Kanji').closest('div');
    expect(kanji).not.toBeNull();
    expect(within(kanji as HTMLElement).getByText('12 due')).toBeInTheDocument();
    expect(within(kanji as HTMLElement).getByText('15 new available')).toBeInTheDocument();
    expect(screen.getByText('30 due')).toBeInTheDocument();

    await user.click(screen.getByRole('link', { name: 'Study now' }));
    expect(screen.getByText('Review page')).toBeInTheDocument();
  });

  it('says nothing is due, with the next due time, instead of offering to study', async () => {
    server.use(
      http.get('/api/v1/reviews/next', () =>
        HttpResponse.json(makeNextCard(null, { next_due_at: '2026-09-21T08:30:00Z' })),
      ),
    );
    renderPanel();
    expect(
      await screen.findByText(/Nothing due right now\. Next card due .*2026/),
    ).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Study now' })).not.toBeInTheDocument();
  });

  it('says nothing is due without a time when nothing is scheduled', async () => {
    server.use(http.get('/api/v1/reviews/next', () => HttpResponse.json(makeNextCard(null))));
    renderPanel();
    expect(await screen.findByText('Nothing due right now.')).toBeInTheDocument();
  });

  it('explains a failed load and can try again', async () => {
    const user = userEvent.setup();
    let calls = 0;
    server.use(
      http.get('/api/v1/reviews/next', () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json({ detail: 'boom' }, { status: 500 })
          : HttpResponse.json(makeNextCard(makeKanaCard()));
      }),
    );
    renderPanel();
    expect(await screen.findByText("Couldn't load your study queue")).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('link', { name: 'Study now' })).toBeInTheDocument();
  });
});
```

Replace `frontend/src/features/home/HomePage.test.tsx` with:

```tsx
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it } from 'vitest';

import { session } from '../../auth/session';
import { makeKanaCard, makeNextCard } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { HomePage } from './HomePage';

const BUILT = {
  built: true,
  kana: 208,
  kanji: 3088,
  vocab: 7734,
  unleveled_kanji: 979,
  kanji_by_level: { N5: 480, N4: 352, N3: 544, N2: 357, N1: 376 },
  vocab_by_level: { N5: 667, N4: 630, N3: 1647, N2: 1737, N1: 3053 },
  meta: {},
};

function renderHome() {
  return renderWithProviders(
    <Routes>
      <Route index element={<HomePage />} />
      <Route path="build" element={<p>Build page</p>} />
    </Routes>,
  );
}

describe('HomePage', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
    server.use(
      http.get('/api/v1/reviews/next', () => HttpResponse.json(makeNextCard(makeKanaCard()))),
    );
  });

  it('shows the totals and the per-level table of built content', async () => {
    server.use(http.get('/api/v1/content/summary', () => HttpResponse.json(BUILT)));
    renderHome();
    expect(await screen.findByRole('heading', { name: 'Your content' })).toBeInTheDocument();
    expect(screen.getByText('208')).toBeInTheDocument();
    expect(screen.getByText('3,088')).toBeInTheDocument();
    expect(screen.getByText('7,734')).toBeInTheDocument();
    expect(screen.getByText('979 not in the JLPT vocabulary')).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Items per JLPT level' });
    const n5 = within(table).getByRole('row', { name: /N5/ });
    expect(within(n5).getByText('667')).toBeInTheDocument();
    expect(within(n5).getByText('480')).toBeInTheDocument();
  });

  it('invites a first-time user to build the content', async () => {
    server.use(
      http.get('/api/v1/content/summary', () =>
        HttpResponse.json({
          ...BUILT,
          built: false,
          kana: 0,
          kanji: 0,
          vocab: 0,
          unleveled_kanji: 0,
          kanji_by_level: {},
          vocab_by_level: {},
        }),
      ),
    );
    renderHome();
    expect(await screen.findByText('Welcome to Bunshō')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: 'Build your content' }));
    expect(screen.getByText('Build page')).toBeInTheDocument();
  });

  it('says what went wrong and lets the user try again', async () => {
    server.use(
      http.get('/api/v1/content/summary', () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    );
    renderHome();
    expect(await screen.findByText("Couldn't load the content summary")).toBeInTheDocument();
    expect(screen.getByText(/server had a problem/i)).toBeInTheDocument();

    server.use(http.get('/api/v1/content/summary', () => HttpResponse.json(BUILT)));
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('heading', { name: 'Your content' })).toBeInTheDocument();
  });

  it('puts the study queue above the content when content is built', async () => {
    server.use(http.get('/api/v1/content/summary', () => HttpResponse.json(BUILT)));
    renderHome();
    expect(await screen.findByRole('link', { name: 'Study now' })).toBeInTheDocument();
    const headings = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual(['Today', 'Your content']);
  });

  it('does not show the study queue before anything is built', async () => {
    server.use(
      http.get('/api/v1/content/summary', () =>
        HttpResponse.json({ ...BUILT, built: false, kana: 0, kanji: 0, vocab: 0 }),
      ),
    );
    renderHome();
    expect(await screen.findByText('Welcome to Bunshō')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Study now' })).not.toBeInTheDocument();
  });
});
```

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
import { makeKanaCard, makeNextCard } from './test/fixtures';
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

- [ ] **Step 2: Run the tests to verify they fail**

Run (in `frontend/`): `npx vitest run src/features/home src/components src/App.test.tsx`
Expected: FAIL (`./StudyPanel` not found, no `Study` link, no `Loading page` status).

- [ ] **Step 3: Write the implementation**

Create `frontend/src/features/home/StudyPanel.tsx`:

```tsx
import { Alert, Button, Paper, SimpleGrid, Skeleton, Stack, Text, Title } from '@mantine/core';
import { Link } from 'react-router';

import { messageFor } from '../../api/errors';
import { useNextReview } from '../../api/queries';
import { formatDueTime } from '../review/formatInterval';

const TYPES = [
  { key: 'kana', label: 'Kana' },
  { key: 'kanji', label: 'Kanji' },
  { key: 'vocab', label: 'Vocabulary' },
] as const;

/** What is waiting to be studied, and the way in. */
export function StudyPanel() {
  const next = useNextReview();

  if (next.isPending) return <Skeleton height={168} />;
  if (next.isError) {
    return (
      <Alert color="red" title="Couldn't load your study queue">
        <Text size="sm">{messageFor(next.error)}</Text>
        <Button
          mt="sm"
          size="xs"
          onClick={() => {
            void next.refetch();
          }}
        >
          Try again
        </Button>
      </Alert>
    );
  }

  const { card, counts, next_due_at: nextDueAt } = next.data;
  return (
    <Stack gap="sm">
      <Title order={2}>Today</Title>
      <SimpleGrid cols={{ base: 1, sm: 3 }}>
        {TYPES.map(({ key, label }) => (
          <Paper key={key} withBorder p="md">
            <Text size="sm" c="dimmed">
              {label}
            </Text>
            <Text fz={28} fw={600}>
              {counts.due[key]} due
            </Text>
            <Text size="xs" c="dimmed">
              {counts.new_remaining[key]} new available
            </Text>
          </Paper>
        ))}
      </SimpleGrid>
      {card !== null ? (
        <Button component={Link} to="/review" size="md">
          Study now
        </Button>
      ) : (
        <Text c="dimmed">
          Nothing due right now
          {nextDueAt !== null ? `. Next card due ${formatDueTime(nextDueAt)}` : ''}.
        </Text>
      )}
    </Stack>
  );
}
```

Create `frontend/src/components/PageLoader.tsx`:

```tsx
import { Center, Loader } from '@mantine/core';

/** Shown while a page's code is being fetched (the pages load on demand). */
export function PageLoader() {
  return (
    <Center py="xl">
      <Loader role="status" aria-label="Loading page" />
    </Center>
  );
}
```

Replace `frontend/src/features/home/HomePage.tsx` with:

```tsx
import {
  Alert,
  Button,
  Paper,
  SimpleGrid,
  Skeleton,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { Link } from 'react-router';

import { messageFor } from '../../api/errors';
import { useContentSummary } from '../../api/queries';
import { formatCount } from '../build/format';
import { StudyPanel } from './StudyPanel';

const LEVELS = ['N5', 'N4', 'N3', 'N2', 'N1'] as const;

function Stat({ label, value, note }: { label: string; value: number; note?: string }) {
  return (
    <Paper withBorder p="md">
      <Text size="sm" c="dimmed">
        {label}
      </Text>
      <Text fz={28} fw={600}>
        {formatCount(value)}
      </Text>
      {note !== undefined && (
        <Text size="xs" c="dimmed">
          {note}
        </Text>
      )}
    </Paper>
  );
}

/** What has been built so far, or an invitation to build it. */
export function HomePage() {
  const summary = useContentSummary();

  if (summary.isPending) {
    return (
      <Stack>
        <Skeleton height={32} width={220} />
        <Skeleton height={112} />
      </Stack>
    );
  }
  if (summary.isError) {
    return (
      <Alert color="red" title="Couldn't load the content summary">
        <Text size="sm">{messageFor(summary.error)}</Text>
        <Button
          mt="sm"
          size="xs"
          onClick={() => {
            void summary.refetch();
          }}
        >
          Try again
        </Button>
      </Alert>
    );
  }

  const data = summary.data;
  if (!data.built) {
    return (
      <Alert color="blue" title="Welcome to Bunshō">
        <Text size="sm">
          There is no study content yet. Build it once from the vocabulary deck and it will be here.
        </Text>
        <Button component={Link} to="/build" mt="sm" size="xs">
          Build your content
        </Button>
      </Alert>
    );
  }

  return (
    <Stack gap="md">
      <StudyPanel />
      <Title order={2}>Your content</Title>
      <SimpleGrid cols={{ base: 1, sm: 3 }}>
        <Stat label="Kana" value={data.kana} />
        <Stat
          label="Kanji"
          value={data.kanji}
          note={`${formatCount(data.unleveled_kanji)} not in the JLPT vocabulary`}
        />
        <Stat label="Vocabulary" value={data.vocab} />
      </SimpleGrid>
      <Table withTableBorder aria-label="Items per JLPT level">
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Level</Table.Th>
            <Table.Th ta="right">Vocabulary</Table.Th>
            <Table.Th ta="right">Kanji</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {LEVELS.map((level) => (
            <Table.Tr key={level}>
              <Table.Td>{level}</Table.Td>
              <Table.Td ta="right">{formatCount(data.vocab_by_level[level] ?? 0)}</Table.Td>
              <Table.Td ta="right">{formatCount(data.kanji_by_level[level] ?? 0)}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Stack>
  );
}
```

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
Expected: PASS (27 files, 204 tests).

- [ ] **Step 5: Run the frontend gate and check the bundle**

Run (in `frontend/`): `npm run format:check && npm run lint && npm run build && npm run coverage`
Expected: all green, and the build output shows separate chunks for `HomePage`, `ReviewPage` and `BuildPage` (plus shared chunks) with **no** "Some chunks are larger than 500 kB" warning (the main chunk is about 388 kB). Do not raise `chunkSizeWarningLimit`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/home/StudyPanel.tsx frontend/src/features/home/StudyPanel.test.tsx frontend/src/features/home/HomePage.tsx frontend/src/features/home/HomePage.test.tsx frontend/src/components/PageLoader.tsx frontend/src/components/AppLayout.tsx frontend/src/components/AppLayout.test.tsx frontend/src/App.tsx frontend/src/App.test.tsx
git commit -m "feat: study dashboard, Study link and lazy-loaded routes" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 6: Documentation, whole-branch verification and review

**Files:**
- Modify: `README.md`, `CHANGELOG.md`, `TODO.md`, `docs/superpowers/specs/2026-09-20-bunsho-2b2-study-loop-design.md` (implementation notes)

The docs files use CRLF line endings in the working tree: keep them (do not introduce mixed endings).

- [ ] **Step 1: Update the README**

In the "Studying (review API)" section, in the paragraph that starts `**Web UI.**`, replace `the pages are `/` for Home, `/build` for the content build and `/login`` with `the pages are `/` for the dashboard and content summary, `/review` for the study session, `/build` for the content build and `/login``.

Directly after that paragraph add:

````markdown
**Studying in the browser.** Open the dashboard (`/`) and press *Study now*, or use the *Study* link. The review shows one card at a time: press Space or Enter (or *Show answer*) to flip it, then grade yourself with the buttons or the keys `1` Again, `2` Hard, `3` Good, `4` Easy (each button shows when the card would come back). Furigana is hidden on the front of cards that test a word's reading or meaning and shown once you flip the card; the *Show furigana* switch also shows it on the front (remembered in this browser only). There is no undo, because every grade is written to the append-only review log.
````

- [ ] **Step 2: CHANGELOG, TODO and spec notes**

`CHANGELOG.md`, under `## [Unreleased]` → `### Added`, directly after the existing "Web UI" bullet:

```markdown
- Study screens in the web UI: a dashboard on the Home page (what is due and what is new, per type,
  and a *Study now* button) and a flip-and-grade review with keyboard shortcuts (Space or Enter to
  flip, 1 to 4 to grade), the projected interval on every grade button, furigana on the answer side
  (and on the front with a switch), and a finished state with the next due time. The pages are
  loaded on demand, so the first screen no longer carries the study and build code.
```

`TODO.md`:
- Replace the status paragraph at the top with: `Status: Plans 1A, 1B, 1C, 2A and 2B-1 are merged. Plan 2B-2 (the study loop: dashboard and review) is implemented on `feat/plan-2b2-study-loop`; Plan 2B-3 (statistics and settings screens) is next. Design: the specs in `docs/superpowers/specs/`. Plans: `docs/superpowers/plans/`.` (keep the existing wrapping style).
- Under "Plan 2B-2 and later": replace the item "Dashboard, flip-and-grade review with keyboard shortcuts and furigana, statistics and settings screens (Plan 2B-2)" with `- [x] Dashboard and flip-and-grade review with keyboard shortcuts and furigana (Plan 2B-2)` and add `- [ ] Statistics and settings screens (Plan 2B-3)`; tick the code-splitting item (`- [x] Code-split the routes ... (lazy routes, Plan 2B-2)`).
- Add these open items under the same heading (one each, in the file's style): "`GET /reviews/next` cannot say why no card is offered (daily limit used up vs everything introduced): add a reason field and use it in the finished state"; "Typed-answer and multiple-choice review modes plug into the `ReviewMode` contract (`features/review/reviewMode.ts`)"; "Undo of a grade and study-ahead need API support (the review log is append-only, `next` has no look-ahead)"; "Check Japanese font rendering in real browsers (Hiragino, Yu Gothic, Noto) and self-host Noto Sans JP if the system stack looks poor"; "Per-level progress on the dashboard (with the statistics screen, Plan 2B-3)".

Append to the spec `docs/superpowers/specs/2026-09-20-bunsho-2b2-study-loop-design.md` an "Implementation notes" section (the spec has none yet) listing: the single "done for now" state and why (the API cannot distinguish the two causes); the answer mutation stays pending until the next card is fetched so a graded card is never shown again; after the flip focus goes to the grade group, not the first button (a held Space would press it); the shortcut scope rule (keys count on the page body or inside an element marked `data-review-controls`, so text fields, links and the header switch keep their own keys); the dashboard numbers come from `next` (`due` and `new_remaining`); the screen-reader status text ("Card shown", "Answer shown", "Saving answer", "Nothing due right now") is static; fixtures need `segment()` because the generated types make `highlighted` and `tags` required.

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
Expected: everything green; Python coverage at or above 90% (no backend change: 552 tests); frontend coverage at or above 80%; the schema files unchanged; the smoke test ends `[smoke] PASS` (the Docker image builds the UI with the lazy chunks and serves it). Also confirm `git status` is clean.

- [ ] **Step 4: Whole-branch review (Sonnet)**

Dispatch one whole-branch review with `superpowers:requesting-code-review` on a **Sonnet** model (James: not Opus), against `main`, given the spec, this plan, "Refinements to the spec" and the ledger. Ask it to check specifically: keyboard handling and focus (repeat, IME, modifiers, text fields, links, held-key hazards, focus after flip and after the next card); live-region hygiene (one persistent region, static text, no doubled announcements with alerts); the answer flow (`expected_last_review` sent untouched, `duration_ms` measurement and clamp, no double grade while pending, 409 handling, retry after a network failure re-sends the identical request, no card shown twice after a grade); cache correctness (`['review','next']` shared by the dashboard and the review, counts written after a grade, nothing sensitive in keys); the lazy routes (Suspense placement, chunk-load failure caught by the ErrorBoundary, the shell stays visible); typography and `lang="ja"` coverage; accessibility basics; test quality (no real network, fake timers only for `Date`); and consistency between README, CHANGELOG, TODO, the spec notes and the code. Fix Critical and Important findings in one fix wave and re-review only that wave; record Minor findings in `TODO.md`.

- [ ] **Step 5: Push and prepare the PR**

```bash
git push
gh pr ready   # only when CI is green on ubuntu, windows and macOS, including the frontend and smoke jobs
```
Update the draft PR description (end with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`): what was built, that no dependency was added, test counts and coverage (Python and frontend), the bundle sizes before and after (main chunk from about 540 kB to about 388 kB), the smoke-test result, what could not be checked in a browser (the authenticated screens: card typography, shortcuts, the mobile layout: ask James to eyeball them), and what Plan 2B-3 builds on. James reviews and merges; do not merge.
