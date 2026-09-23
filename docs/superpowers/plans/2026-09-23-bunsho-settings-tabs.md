# Settings Tabs and a System Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the Settings form into three Mantine tabs (Learning path, Pace, Reviewing), add a System tab that takes over the Build page and shows server and content status, and release it as 1.2.0.

**Architecture:** A controlled Mantine `Tabs` whose value lives in the `?tab=` search parameter. One `useForm` in a `SettingsTabs` shell feeds three form-tab components and a Save bar; the System panel sits outside the `<form>` and is lazy-loaded and unmounted when hidden. A pure field-path → tab table drives an error mark on tabs and a jump to the first tab with an error. `/build` becomes a redirect.

**Tech Stack:** React 19, TypeScript (strict), Mantine 9 (`@mantine/core` Tabs, `@mantine/form`), react-router 8, TanStack Query, ofetch, Vitest + Testing Library + MSW.

**Spec:** `docs/superpowers/specs/2026-09-23-bunsho-settings-tabs-design.md`

All commands run from `D:\Documents\Code\Bunshō\frontend` unless stated. Use the Bash tool (Git Bash).

## Global Constraints

- Mantine `Tabs` (`Tabs.List`, `Tabs.Tab`, `Tabs.Panel`) for the tab UI; no hand-rolled tab strip and no hand-written `role="tab*"` / `aria-controls` attributes.
- Tab values are exactly `learning`, `pace`, `reviewing`, `system`; labels are "Learning path", "Pace", "Reviewing", "System".
- One `useForm`, one Save; the `<form>` wraps only the three settings panels and the Save bar; the System panel is outside it.
- Save and Reset are not rendered on System.
- The reset button label is "Reset all tabs to recommended values".
- Tab selection changes use `replace: true` (Back must leave Settings, not step through tabs).
- Unknown or missing `?tab=` falls back to `learning`.
- `/build` redirects (replace) to `/settings?tab=system`; the "Build content" nav item is removed.
- The three first-run buttons ("Build your content") link to `/settings?tab=system`.
- A colour is never the only signal: an errored tab also carries visually hidden text " (has errors)".
- MSW runs with `onUnhandledRequest: 'error'`: every test that opens the System tab must serve `GET /api/v1/health`, `/content/summary`, `/admin/config-check` and `/admin/content/build`.
- No backend change. Version 1.1.2 → 1.2.0 in seven places (Task 10).
- Code style: match the surrounding files (Prettier via `npm run format`, ESLint via `npm run lint`, strict TypeScript). Commit messages end with `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.

## Review Focus

Inputs and conditions the spec implies that no plain happy-path test would exercise, most likely first:

1. **A 503 from `/health` that is not the API's JSON** (a reverse proxy's HTML error page): must show the block's error alert with a retry, never a fabricated status. Pinned in Task 3 and Task 4.
2. **A server 422 on a field whose control shows no error** (the three review-mode selects had no `error` prop): the tab is marked and jumped to, so the message must be visible on the field. Pinned in Task 8.
3. **A garbage `?tab=`** (`?tab=`, `?tab=admin`, `?tab=pace&tab=system`): default tab, or the first value, never a blank page. Pinned in Task 2.
4. **The System tab closed and reopened while a build runs**: the progress card must come back from the live build state, not vanish. Pinned in Task 8.
5. **An edit made on a tab, the form saved from another tab, then Reset**: Reset refills every tab and clears every tab's error mark. Pinned in Task 8.

---

### Task 1: Tab names, the field → tab table and error helpers

**Files:**
- Modify: `frontend/src/features/settings/settingsForm.ts` (add exports; keep everything else)
- Test: `frontend/src/features/settings/settingsForm.test.ts`

**Interfaces:**
- Produces (all exported from `settingsForm.ts`):
  - `type SettingsTab = 'learning' | 'pace' | 'reviewing' | 'system'`
  - `type FormTab = Exclude<SettingsTab, 'system'>`
  - `const SETTINGS_TABS: readonly { value: SettingsTab; label: string }[]` (tab order)
  - `const DEFAULT_TAB: SettingsTab` (`'learning'`)
  - `isSettingsTab(value: string | null | undefined): value is SettingsTab`
  - `const TAB_OF_FIELD: Readonly<Record<keyof SettingsFormValues, FormTab>>`
  - `tabOfField(path: string): FormTab`
  - `tabsWithErrors(errors: Readonly<Record<string, unknown>>): ReadonlySet<FormTab>`
  - `firstTabWithErrors(errors: Readonly<Record<string, unknown>>): FormTab | null`
  - `firstErrorPathIn(errors: Readonly<Record<string, unknown>>, tab: FormTab): string | null`
  - `type SettingsFormApi = UseFormReturnType<SettingsFormValues>`

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/features/settings/settingsForm.test.ts` (add the new names to its existing import from `./settingsForm`, and `toFormValues`/`RECOMMENDED_SETTINGS` are already imported there or add them):

```ts
describe('settings tabs', () => {
  it('lists the tabs in display order with their labels', () => {
    expect(SETTINGS_TABS.map((tab) => tab.value)).toEqual([
      'learning',
      'pace',
      'reviewing',
      'system',
    ]);
    expect(SETTINGS_TABS.map((tab) => tab.label)).toEqual([
      'Learning path',
      'Pace',
      'Reviewing',
      'System',
    ]);
    expect(DEFAULT_TAB).toBe('learning');
  });

  it.each([
    ['learning', true],
    ['system', true],
    ['admin', false],
    ['', false],
    [null, false],
    [undefined, false],
  ])('isSettingsTab(%j) is %s', (value, expected) => {
    expect(isSettingsTab(value)).toBe(expected);
  });

  it('places every field of the form on a tab', () => {
    for (const field of Object.keys(toFormValues(RECOMMENDED_SETTINGS))) {
      expect(Object.hasOwn(TAB_OF_FIELD, field), field).toBe(true);
    }
  });

  it.each([
    ['new_card_policy', 'learning'],
    ['active_levels', 'learning'],
    ['mastery_threshold_percent', 'learning'],
    ['type_enabled.kana', 'learning'],
    ['kana_gate', 'learning'],
    ['kana_gate.threshold_percent', 'learning'],
    ['new_limits', 'pace'],
    ['new_limits.kana', 'pace'],
    ['rollover_hour', 'pace'],
    ['target_retention_percent', 'pace'],
    ['kana_mode', 'reviewing'],
    ['vocab_mode', 'reviewing'],
    ['not_a_field', 'learning'],
    ['', 'learning'],
  ])('puts %s on the %s tab', (path, tab) => {
    expect(tabOfField(path)).toBe(tab);
  });

  it('finds the tabs that hold an error, whatever the nesting', () => {
    expect([...tabsWithErrors({})]).toEqual([]);
    expect([
      ...tabsWithErrors({ 'new_limits.kana': 'Too big', kana_gate: 'Needs kana' }),
    ]).toEqual(expect.arrayContaining(['pace', 'learning']));
    expect(tabsWithErrors({ kana_mode: 'Bad' }).has('reviewing')).toBe(true);
  });

  it('ignores an entry that holds no message', () => {
    expect([...tabsWithErrors({ rollover_hour: null, kana_mode: undefined, x: false, y: '' })]).toEqual(
      [],
    );
  });

  it('picks the first tab in tab order, not in key order', () => {
    expect(firstTabWithErrors({})).toBeNull();
    expect(firstTabWithErrors({ kana_mode: 'Bad', rollover_hour: 'Bad' })).toBe('pace');
    expect(firstTabWithErrors({ kana_mode: 'Bad', new_card_policy: 'Bad' })).toBe('learning');
  });

  it('picks the first errored field of a tab', () => {
    const errors = { kana_mode: 'Bad', rollover_hour: 'Bad', 'new_limits.kanji': 'Bad' };
    expect(firstErrorPathIn(errors, 'pace')).toBe('rollover_hour');
    expect(firstErrorPathIn(errors, 'reviewing')).toBe('kana_mode');
    expect(firstErrorPathIn(errors, 'learning')).toBeNull();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/features/settings/settingsForm.test.ts`
Expected: FAIL (the new names are not exported).

- [ ] **Step 3: Implement**

Add near the top of `settingsForm.ts` (after the existing imports, adding `import type { UseFormReturnType } from '@mantine/form';`):

```ts
export type SettingsFormApi = UseFormReturnType<SettingsFormValues>;
```

Append at the end of `settingsForm.ts`:

```ts
export type SettingsTab = 'learning' | 'pace' | 'reviewing' | 'system';
/** A tab that edits the settings form (System does not). */
export type FormTab = Exclude<SettingsTab, 'system'>;

export const SETTINGS_TABS: readonly { value: SettingsTab; label: string }[] = [
  { value: 'learning', label: 'Learning path' },
  { value: 'pace', label: 'Pace' },
  { value: 'reviewing', label: 'Reviewing' },
  { value: 'system', label: 'System' },
];

export const DEFAULT_TAB: SettingsTab = 'learning';

export function isSettingsTab(value: string | null | undefined): value is SettingsTab {
  return SETTINGS_TABS.some((tab) => tab.value === value);
}

/** Which tab each top-level form field lives on; a new field will not compile until placed. */
export const TAB_OF_FIELD: Readonly<Record<keyof SettingsFormValues, FormTab>> = {
  new_card_policy: 'learning',
  active_levels: 'learning',
  mastery_threshold_percent: 'learning',
  type_enabled: 'learning',
  kana_gate: 'learning',
  new_limits: 'pace',
  rollover_hour: 'pace',
  target_retention_percent: 'pace',
  kana_mode: 'reviewing',
  kanji_mode: 'reviewing',
  vocab_mode: 'reviewing',
};

const FORM_TABS: readonly FormTab[] = ['learning', 'pace', 'reviewing'];

/** The tab of a form field path (`new_limits.kana`); an unknown path counts as the first tab. */
export function tabOfField(path: string): FormTab {
  const root = path.split('.')[0] ?? '';
  return Object.hasOwn(TAB_OF_FIELD, root) ? TAB_OF_FIELD[root as keyof SettingsFormValues] : 'learning';
}

function hasMessage(value: unknown): boolean {
  return value !== null && value !== undefined && value !== false && value !== '';
}

/** The tabs holding at least one error (form errors are keyed by field path). */
export function tabsWithErrors(errors: Readonly<Record<string, unknown>>): ReadonlySet<FormTab> {
  const tabs = new Set<FormTab>();
  for (const [path, message] of Object.entries(errors)) {
    if (hasMessage(message)) tabs.add(tabOfField(path));
  }
  return tabs;
}

/** The first tab, in display order, that holds an error; null when there is none. */
export function firstTabWithErrors(errors: Readonly<Record<string, unknown>>): FormTab | null {
  const tabs = tabsWithErrors(errors);
  return FORM_TABS.find((tab) => tabs.has(tab)) ?? null;
}

/** The first errored field path on `tab`, in the order the errors were recorded. */
export function firstErrorPathIn(
  errors: Readonly<Record<string, unknown>>,
  tab: FormTab,
): string | null {
  for (const [path, message] of Object.entries(errors)) {
    if (hasMessage(message) && tabOfField(path) === tab) return path;
  }
  return null;
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run src/features/settings/settingsForm.test.ts && npx tsc -b`
Expected: PASS, no type errors.

- [ ] **Step 5: Commit**

```bash
npm run format -- src/features/settings/settingsForm.ts src/features/settings/settingsForm.test.ts
git add src/features/settings/settingsForm.ts src/features/settings/settingsForm.test.ts
git commit -m "feat(settings): add the tab names and the field to tab table" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: The `?tab=` hook

**Files:**
- Create: `frontend/src/features/settings/useSettingsTab.ts`
- Test: `frontend/src/features/settings/useSettingsTab.test.tsx`

**Interfaces:**
- Consumes: `DEFAULT_TAB`, `isSettingsTab`, `SettingsTab` from `./settingsForm` (Task 1).
- Produces: `useSettingsTab(): readonly [SettingsTab, (tab: string | null) => void]`. The setter ignores anything that is not a known tab and replaces the history entry.

- [ ] **Step 1: Write the failing test**

`useSettingsTab.test.tsx`:

```tsx
import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter, useLocation, useNavigationType } from 'react-router';
import { describe, expect, it } from 'vitest';

import { useSettingsTab } from './useSettingsTab';

function setup(initial: string) {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={[initial]}>{children}</MemoryRouter>
  );
  return renderHook(
    () => ({
      tab: useSettingsTab(),
      location: useLocation(),
      navigationType: useNavigationType(),
    }),
    { wrapper },
  );
}

describe('useSettingsTab', () => {
  it.each([
    ['/settings', 'learning'],
    ['/settings?tab=pace', 'pace'],
    ['/settings?tab=system', 'system'],
    ['/settings?tab=', 'learning'],
    ['/settings?tab=admin', 'learning'],
    ['/settings?tab=PACE', 'learning'],
    ['/settings?tab=pace&tab=system', 'pace'],
    ['/settings?other=1', 'learning'],
  ])('reads %s as the %s tab', (url, expected) => {
    const { result } = setup(url);
    expect(result.current.tab[0]).toBe(expected);
  });

  it('writes the tab to the URL, replacing the history entry', () => {
    const { result } = setup('/settings');
    act(() => {
      result.current.tab[1]('reviewing');
    });
    expect(result.current.tab[0]).toBe('reviewing');
    expect(result.current.location.search).toBe('?tab=reviewing');
    expect(result.current.navigationType).toBe('REPLACE');
  });

  it('ignores a value that is not a tab', () => {
    const { result } = setup('/settings?tab=pace');
    act(() => {
      result.current.tab[1]('nonsense');
      result.current.tab[1](null);
    });
    expect(result.current.tab[0]).toBe('pace');
    expect(result.current.location.search).toBe('?tab=pace');
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/features/settings/useSettingsTab.test.tsx`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

`useSettingsTab.ts`:

```ts
import { useCallback } from 'react';
import { useSearchParams } from 'react-router';

import { DEFAULT_TAB, isSettingsTab, type SettingsTab } from './settingsForm';

/**
 * The selected Settings tab, kept in the `?tab=` search parameter so it survives a reload and can
 * be linked to. A missing or unknown value is the default tab. The setter takes Mantine's
 * `string | null` and ignores anything that is not a tab; it replaces the history entry so Back
 * leaves Settings instead of stepping through tabs.
 */
export function useSettingsTab(): readonly [SettingsTab, (tab: string | null) => void] {
  const [params, setParams] = useSearchParams();
  const raw = params.get('tab');
  const tab = isSettingsTab(raw) ? raw : DEFAULT_TAB;
  const setTab = useCallback(
    (next: string | null) => {
      if (isSettingsTab(next)) setParams({ tab: next }, { replace: true });
    },
    [setParams],
  );
  return [tab, setTab] as const;
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run src/features/settings/useSettingsTab.test.tsx`
Expected: PASS (all rows).

- [ ] **Step 5: Commit**

```bash
npm run format -- src/features/settings/useSettingsTab.ts src/features/settings/useSettingsTab.test.tsx
git add src/features/settings/useSettingsTab.ts src/features/settings/useSettingsTab.test.tsx
git commit -m "feat(settings): keep the selected tab in the URL" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: A `/health` client that treats 503 as data

**Files:**
- Modify: `frontend/src/api/http.ts` (add `rawRequestAllowing`)
- Modify: `frontend/src/api/endpoints.ts` (add `HealthResponse` type and `endpoints.health`)
- Modify: `frontend/src/api/queries.ts` (add `queryKeys.health`, `useHealth`)
- Test: `frontend/src/api/health.test.ts`

**Interfaces:**
- Produces:
  - `rawRequestAllowing<T>(path: string, statuses: readonly number[], isBody: (data: unknown) => data is T): Promise<T>` in `http.ts`. Returns the parsed body of a 2xx, or of an error response whose status is listed in `statuses` and whose body passes `isBody`; anything else throws the normalized `ApiError` / `NetworkError`.
  - `type HealthResponse = Schemas['HealthResponse']` and `endpoints.health(): Promise<HealthResponse>`.
  - `useHealth()` (a `useQuery` over `queryKeys.health`).

- [ ] **Step 1: Write the failing tests**

`api/health.test.ts`:

```ts
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { server } from '../test/server';
import { endpoints } from './endpoints';
import { ApiError, NetworkError } from './errors';

const OK_BODY = {
  status: 'ok',
  version: '1.2.0',
  components: { database: { status: 'ok', detail: 'reachable', latency_ms: 1.5 } },
};
const ERROR_BODY = {
  status: 'error',
  version: '1.2.0',
  components: { content: { status: 'error', detail: 'content.db is missing', latency_ms: 0.2 } },
};

describe('endpoints.health', () => {
  it('returns the body of a healthy answer', async () => {
    server.use(http.get('/api/v1/health', () => HttpResponse.json(OK_BODY)));
    await expect(endpoints.health()).resolves.toEqual(OK_BODY);
  });

  it('returns the body of a 503 as data, so a failing component can be shown', async () => {
    server.use(http.get('/api/v1/health', () => HttpResponse.json(ERROR_BODY, { status: 503 })));
    await expect(endpoints.health()).resolves.toEqual(ERROR_BODY);
  });

  it('does not treat a proxy error page (503, not JSON) as a health report', async () => {
    server.use(
      http.get('/api/v1/health', () =>
        HttpResponse.text('<html>Service Unavailable</html>', {
          status: 503,
          headers: { 'Content-Type': 'text/html' },
        }),
      ),
    );
    const failure = await endpoints.health().catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).status).toBe(503);
  });

  it('does not treat a 503 JSON body of the wrong shape as a health report', async () => {
    server.use(
      http.get('/api/v1/health', () => HttpResponse.json({ detail: 'busy' }, { status: 503 })),
    );
    await expect(endpoints.health()).rejects.toBeInstanceOf(ApiError);
  });

  it('still fails on other error statuses', async () => {
    server.use(http.get('/api/v1/health', () => HttpResponse.json(ERROR_BODY, { status: 500 })));
    await expect(endpoints.health()).rejects.toMatchObject({ status: 500 });
  });

  it('reports an unreachable server as a network error', async () => {
    server.use(http.get('/api/v1/health', () => HttpResponse.error()));
    await expect(endpoints.health()).rejects.toBeInstanceOf(NetworkError);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/api/health.test.ts`
Expected: FAIL (`endpoints.health is not a function`).

- [ ] **Step 3: Implement**

In `api/http.ts` change the import line to `import { FetchError, ofetch } from 'ofetch';` and append:

```ts
/**
 * Like `rawRequest`, but an error response with one of `statuses` whose body passes `isBody` is
 * returned as data. `GET /health` answers 503 with its full report when a dependency is down; that
 * report is what the caller wants. A body that fails `isBody` (a proxy's HTML error page, say) is
 * still an error.
 */
export async function rawRequestAllowing<T>(
  path: string,
  statuses: readonly number[],
  isBody: (data: unknown) => data is T,
): Promise<T> {
  try {
    return await ofetch<T>(apiUrl(path), { retry: 0 });
  } catch (error) {
    if (
      error instanceof FetchError &&
      error.response !== undefined &&
      statuses.includes(error.response.status)
    ) {
      const data: unknown = error.data;
      if (isBody(data)) return data;
    }
    throw toClientError(error);
  }
}
```

In `api/endpoints.ts`: change the http import to `import { rawRequestAllowing } from './http';` (next to the `client` import), add `export type HealthResponse = Schemas['HealthResponse'];` with the other type exports, and above the `endpoints` object:

```ts
function isHealthResponse(data: unknown): data is HealthResponse {
  if (typeof data !== 'object' || data === null) return false;
  const candidate = data as Record<string, unknown>;
  return (
    typeof candidate.status === 'string' &&
    typeof candidate.version === 'string' &&
    typeof candidate.components === 'object' &&
    candidate.components !== null
  );
}
```

and inside `endpoints` (first entry):

```ts
  /** Component health and the version. Unauthenticated; a 503 still carries the full report. */
  health: () => rawRequestAllowing<HealthResponse>('/health', [503], isHealthResponse),
```

In `api/queries.ts` add `health: ['health'] as const,` to `queryKeys` and:

```ts
export function useHealth() {
  return useQuery({ queryKey: queryKeys.health, queryFn: endpoints.health });
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run src/api && npx tsc -b`
Expected: PASS (the existing api tests too).

- [ ] **Step 5: Commit**

```bash
npm run format -- src/api
git add src/api
git commit -m "feat(api): add a health client that reads a 503 report as data" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: The Server and Content status blocks

**Files:**
- Create: `frontend/src/features/settings/ServerStatus.tsx`, `frontend/src/features/settings/ContentStatus.tsx`
- Test: `frontend/src/features/settings/ServerStatus.test.tsx`, `frontend/src/features/settings/ContentStatus.test.tsx`

**Interfaces:**
- Consumes: `useHealth`, `useContentSummary` (Task 3 / existing), `messageFor`, `formatCount` from `../build/format`.
- Produces: `ServerStatus()` and `ContentStatus()`, each a `Paper component="section"` with an `aria-label` ("Server", "Content") so tests and screen readers can address them as regions.

- [ ] **Step 1: Write the failing tests**

`ServerStatus.test.tsx`:

```tsx
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { ServerStatus } from './ServerStatus';

const REPORT = {
  status: 'degraded',
  version: '1.2.0',
  components: {
    database: { status: 'ok', detail: 'progress.db reachable', latency_ms: 1.2 },
    content: { status: 'degraded', detail: 'content.db is older than the deck', latency_ms: 0.4 },
  },
};

describe('ServerStatus', () => {
  it('shows the version, the overall state and every component', async () => {
    server.use(http.get('/api/v1/health', () => HttpResponse.json(REPORT)));
    renderWithProviders(<ServerStatus />);
    const region = await screen.findByRole('region', { name: 'Server' });
    expect(await within(region).findByText('Version 1.2.0')).toBeInTheDocument();
    expect(within(region).getAllByText('Degraded')).toHaveLength(2); // overall + the content component
    expect(within(region).getByText('progress.db reachable')).toBeInTheDocument();
    expect(within(region).getByText('content.db is older than the deck')).toBeInTheDocument();
  });

  it('shows a failing component from a 503 report instead of hiding it', async () => {
    const report = {
      ...REPORT,
      status: 'error',
      components: { content: { status: 'error', detail: 'content.db is missing', latency_ms: 0 } },
    };
    server.use(http.get('/api/v1/health', () => HttpResponse.json(report, { status: 503 })));
    renderWithProviders(<ServerStatus />);
    expect(await screen.findByText('content.db is missing')).toBeInTheDocument();
    expect(screen.getAllByText('Problem')).toHaveLength(2); // overall + the content component
  });

  it('explains a failed check and can try again', async () => {
    let calls = 0;
    server.use(
      http.get('/api/v1/health', () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.text('<html>bad gateway</html>', { status: 503 })
          : HttpResponse.json(REPORT);
      }),
    );
    renderWithProviders(<ServerStatus />);
    expect(await screen.findByText("Couldn't check the server")).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Version 1.2.0')).toBeInTheDocument();
  });
});
```

`ContentStatus.test.tsx`:

```tsx
import { screen, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { session } from '../../auth/session';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { ContentStatus } from './ContentStatus';

function serveSummary(built: boolean) {
  server.use(
    http.get('/api/v1/content/summary', () =>
      HttpResponse.json({
        built,
        kana: built ? 208 : 0,
        kanji: built ? 3088 : 0,
        vocab: built ? 7734 : 0,
        unleveled_kanji: 0,
        kanji_by_level: {},
        vocab_by_level: {},
        meta: {},
      }),
    ),
  );
}

describe('ContentStatus', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  it('shows the counts of built content', async () => {
    serveSummary(true);
    renderWithProviders(<ContentStatus />);
    const region = await screen.findByRole('region', { name: 'Content' });
    expect(await within(region).findByText('Built')).toBeInTheDocument();
    expect(within(region).getByText('208')).toBeInTheDocument();
    expect(within(region).getByText('3,088')).toBeInTheDocument();
    expect(within(region).getByText('7,734')).toBeInTheDocument();
  });

  it('says so when nothing is built yet, without counts', async () => {
    serveSummary(false);
    renderWithProviders(<ContentStatus />);
    const region = await screen.findByRole('region', { name: 'Content' });
    expect(await within(region).findByText('Not built')).toBeInTheDocument();
    expect(within(region).queryByText('Kanji')).not.toBeInTheDocument();
  });

  it('explains a failed load and can try again', async () => {
    server.use(http.get('/api/v1/content/summary', () => HttpResponse.error()));
    renderWithProviders(<ContentStatus />);
    expect(await screen.findByText("Couldn't load the content status")).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/features/settings/ServerStatus.test.tsx src/features/settings/ContentStatus.test.tsx`
Expected: FAIL (modules not found).

- [ ] **Step 3: Implement**

`ServerStatus.tsx`:

```tsx
import { Alert, Badge, Button, Group, Paper, Skeleton, Stack, Text, Title } from '@mantine/core';

import { messageFor } from '../../api/errors';
import { useHealth } from '../../api/queries';

const STATUS_COLOR = { ok: 'green', degraded: 'yellow', error: 'red' } as const;
const STATUS_LABEL = { ok: 'OK', degraded: 'Degraded', error: 'Problem' } as const;

/** The service's version and what its own health check says about each dependency. */
export function ServerStatus() {
  const health = useHealth();

  if (health.isPending) return <Skeleton height={112} />;
  if (health.isError) {
    return (
      <Alert color="red" title="Couldn't check the server">
        <Text size="sm">{messageFor(health.error)}</Text>
        <Button
          mt="sm"
          size="xs"
          onClick={() => {
            void health.refetch();
          }}
        >
          Try again
        </Button>
      </Alert>
    );
  }

  const { status, version, components } = health.data;
  return (
    <Paper component="section" aria-label="Server" withBorder p="md">
      <Group justify="space-between" mb="xs">
        <Title order={3}>Server</Title>
        <Group gap="xs">
          <Text size="sm" c="dimmed">
            Version {version}
          </Text>
          <Badge color={STATUS_COLOR[status]} variant="light">
            {STATUS_LABEL[status]}
          </Badge>
        </Group>
      </Group>
      <Stack gap={6}>
        {Object.entries(components).map(([name, component]) => (
          <Group key={name} gap="xs" wrap="nowrap" align="flex-start">
            <Badge color={STATUS_COLOR[component.status]} variant="light" w={88}>
              {STATUS_LABEL[component.status]}
            </Badge>
            <Text size="sm" fw={500}>
              {name}
            </Text>
            <Text size="sm" c="dimmed">
              {component.detail}
            </Text>
          </Group>
        ))}
      </Stack>
    </Paper>
  );
}
```

`ContentStatus.tsx`:

```tsx
import { Alert, Badge, Button, Group, Paper, Skeleton, Stack, Text, Title } from '@mantine/core';

import { messageFor } from '../../api/errors';
import { useContentSummary } from '../../api/queries';
import { formatCount } from '../build/format';

/** Whether the study content is built, and how much of each kind there is. */
export function ContentStatus() {
  const summary = useContentSummary();

  if (summary.isPending) return <Skeleton height={80} />;
  if (summary.isError) {
    return (
      <Alert color="red" title="Couldn't load the content status">
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

  const { built, kana, kanji, vocab } = summary.data;
  return (
    <Paper component="section" aria-label="Content" withBorder p="md">
      <Group justify="space-between" mb={built ? 'xs' : 0}>
        <Title order={3}>Content</Title>
        <Badge color={built ? 'green' : 'gray'} variant="light">
          {built ? 'Built' : 'Not built'}
        </Badge>
      </Group>
      {built && (
        <Group gap="xl">
          {[
            ['Kana', kana],
            ['Kanji', kanji],
            ['Vocabulary', vocab],
          ].map(([label, count]) => (
            <Stack key={label} gap={0}>
              <Text size="xs" c="dimmed">
                {label}
              </Text>
              <Text fw={600}>{formatCount(Number(count))}</Text>
            </Stack>
          ))}
        </Group>
      )}
    </Paper>
  );
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run src/features/settings/ServerStatus.test.tsx src/features/settings/ContentStatus.test.tsx && npx tsc -b`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
npm run format -- src/features/settings
git add src/features/settings/ServerStatus.tsx src/features/settings/ServerStatus.test.tsx src/features/settings/ContentStatus.tsx src/features/settings/ContentStatus.test.tsx
git commit -m "feat(settings): add the server and content status blocks" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Turn the Build page into a `BuildPanel`

**Files:**
- Rename: `frontend/src/features/build/BuildPage.tsx` → `BuildPanel.tsx`; `BuildPage.test.tsx` → `BuildPanel.test.tsx` (use `git mv`)
- Modify: both renamed files; `frontend/src/features/build/EnvironmentChecks.tsx`
- Modify: `frontend/src/App.tsx` (keep the app building: point the old `build` route at `BuildPanel` for now)

**Interfaces:**
- Consumes: nothing new.
- Produces: `BuildPanel()` (same behaviour as `BuildPage` minus the page title, the environment checks and the first-run notice; it carries its own `<Title order={3}>Build</Title>`). `EnvironmentChecks` becomes a labelled region (`aria-label="Environment"`) with an `h3`.

- [ ] **Step 1: Rename and adjust the tests first**

```bash
git mv src/features/build/BuildPage.tsx src/features/build/BuildPanel.tsx
git mv src/features/build/BuildPage.test.tsx src/features/build/BuildPanel.test.tsx
sed -i 's/BuildPage/BuildPanel/g' src/features/build/BuildPanel.test.tsx
```

In `BuildPanel.test.tsx`:
- In `it('welcomes a first run and starts the first build without asking')`: rename it to `starts the first build without asking`, and delete the line `expect(await screen.findByText('First run')).toBeInTheDocument();` (the notice moves to the System tab, Task 6).
- Delete the whole `it('shows what the server found in the environment, problems included')` test (it moves to `SystemTab.test.tsx` in Task 6).
- Add this test at the end of the `describe`:

```tsx
  it('has its own Build heading and does not repeat the environment checks', async () => {
    serve();
    renderWithProviders(<BuildPanel />);
    expect(await screen.findByRole('heading', { name: 'Build' })).toBeInTheDocument();
    expect(screen.queryByText('Environment')).not.toBeInTheDocument();
  });
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/features/build/BuildPanel.test.tsx`
Expected: FAIL (`BuildPanel` is not exported yet).

- [ ] **Step 3: Implement**

In `BuildPanel.tsx`: rename `export function BuildPage()` to `export function BuildPanel()`; update its doc comment to `/** Start a content build (or a dry run) and follow it live. */` (unchanged text is fine); remove the imports of `Alert` and `EnvironmentChecks`; replace `<Title order={2}>Content</Title>` with `<Title order={3}>Build</Title>`; delete the `{!alreadyBuilt && summary.isSuccess && (<Alert …>…</Alert>)}` block and the `<EnvironmentChecks />` line. `alreadyBuilt` and `summary` stay (the button label and the rebuild confirmation use them).

In `EnvironmentChecks.tsx`: change the block's `<Paper withBorder p="md">` to `<Paper component="section" aria-label="Environment" withBorder p="md">` and `<Title order={4} mb="xs">` to `<Title order={3} mb="xs">`.

In `App.tsx` (temporary, replaced in Task 9): change the lazy import to load `BuildPanel` from `./features/build/BuildPanel` and rename the constant/element accordingly:

```tsx
const BuildPage = lazy(() =>
  import('./features/build/BuildPanel').then((module) => ({ default: module.BuildPanel })),
);
```

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run src/features/build src/App.test.tsx && npx tsc -b`
Expected: PASS except `App.test.tsx`'s build-page tests, which still find the heading "Content"; they are rewritten in Task 9. If they fail only on that heading, that is expected: note the failing test names and continue (they are fixed in Task 9). Do not weaken them here.

- [ ] **Step 5: Commit**

```bash
npm run format -- src/features/build src/App.tsx
git add -A src/features/build src/App.tsx
git commit -m "refactor(build): turn the Build page into a BuildPanel" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: The System tab body

**Files:**
- Create: `frontend/src/features/settings/SystemTab.tsx`
- Test: `frontend/src/features/settings/SystemTab.test.tsx`

**Interfaces:**
- Consumes: `ServerStatus`, `ContentStatus` (Task 4), `EnvironmentChecks`, `BuildPanel` (Task 5), `useContentSummary`.
- Produces: `SystemTab()`: first-run notice (when nothing is built), then Server, Content, Environment, Build.

- [ ] **Step 1: Write the failing tests**

`SystemTab.test.tsx`:

```tsx
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { session } from '../../auth/session';
import { makeBuildStatus } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { SystemTab } from './SystemTab';

const BUILD = '/api/v1/admin/content/build';

function serve({ built = true }: { built?: boolean } = {}) {
  const posted: unknown[] = [];
  server.use(
    http.get('/api/v1/health', () =>
      HttpResponse.json({
        status: 'ok',
        version: '1.2.0',
        components: { database: { status: 'ok', detail: 'reachable', latency_ms: 1 } },
      }),
    ),
    http.get('/api/v1/content/summary', () =>
      HttpResponse.json({
        built,
        kana: built ? 208 : 0,
        kanji: 0,
        vocab: 0,
        unleveled_kanji: 0,
        kanji_by_level: {},
        vocab_by_level: {},
        meta: {},
      }),
    ),
    http.get('/api/v1/admin/config-check', () =>
      HttpResponse.json({
        ok: false,
        checks: [
          { name: 'deck_present', ok: false, detail: 'deck not found' },
          { name: 'jamdict_available', ok: true, detail: 'jamdict-data-fix' },
        ],
      }),
    ),
    http.get(BUILD, () => HttpResponse.json({ detail: 'no build has run yet' }, { status: 404 })),
    http.post(BUILD, async ({ request }) => {
      posted.push(await request.json());
      return HttpResponse.json(makeBuildStatus(), { status: 202 });
    }),
  );
  return posted;
}

describe('SystemTab', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  it('shows the server, content, environment and build blocks in that order', async () => {
    serve();
    renderWithProviders(<SystemTab />);
    await screen.findByRole('region', { name: 'Server' });
    const headings = screen
      .getAllByRole('heading', { level: 3 })
      .map((heading) => heading.textContent);
    expect(headings).toEqual(['Server', 'Content', 'Environment', 'Build']);
  });

  it('shows what the server found in the environment, problems included', async () => {
    serve();
    renderWithProviders(<SystemTab />);
    const region = await screen.findByRole('region', { name: 'Environment' });
    expect(await within(region).findByText('deck not found')).toBeInTheDocument();
    expect(within(region).getByText('Vocabulary deck')).toBeInTheDocument();
    expect(within(region).getByText('Problem')).toBeInTheDocument();
    expect(within(region).getByText('OK')).toBeInTheDocument();
  });

  it('welcomes a first run at the top, before the other blocks', async () => {
    serve({ built: false });
    renderWithProviders(<SystemTab />);
    const notice = await screen.findByText('First run');
    const server_ = await screen.findByRole('region', { name: 'Server' });
    expect(
      notice.compareDocumentPosition(server_) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('does not show the first-run notice once content is built', async () => {
    serve({ built: true });
    renderWithProviders(<SystemTab />);
    await screen.findByText('Built');
    expect(screen.queryByText('First run')).not.toBeInTheDocument();
  });

  it('starts a build from the tab', async () => {
    const posted = serve({ built: false });
    renderWithProviders(<SystemTab />);
    await userEvent.click(await screen.findByRole('button', { name: 'Build content' }));
    await waitFor(() => {
      expect(posted).toEqual([{ dry_run: false }]);
    });
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/features/settings/SystemTab.test.tsx`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

`SystemTab.tsx`:

```tsx
import { Alert, Stack } from '@mantine/core';

import { useContentSummary } from '../../api/queries';
import { BuildPanel } from '../build/BuildPanel';
import { EnvironmentChecks } from '../build/EnvironmentChecks';
import { ContentStatus } from './ContentStatus';
import { ServerStatus } from './ServerStatus';

/** Shown until the first build: the study content does not exist yet. */
function FirstRunNotice() {
  const summary = useContentSummary();
  if (!summary.isSuccess || summary.data.built) return null;
  return (
    <Alert color="blue" title="First run">
      The study content has not been built yet. Build it once from the vocabulary deck; it takes
      about half a minute.
    </Alert>
  );
}

/** Service status and the content build. Not part of the settings form. */
export function SystemTab() {
  return (
    <Stack gap="lg">
      <FirstRunNotice />
      <ServerStatus />
      <ContentStatus />
      <EnvironmentChecks />
      <BuildPanel />
    </Stack>
  );
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run src/features/settings/SystemTab.test.tsx && npx tsc -b`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
npm run format -- src/features/settings
git add src/features/settings/SystemTab.tsx src/features/settings/SystemTab.test.tsx
git commit -m "feat(settings): add the System tab body" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: Split the form into tab components and the `SettingsTabs` shell

Behaviour is **unchanged** in this task (the same controls, the same validation, the same saves); only where they live changes. The existing tests keep their assertions and gain an `openTab` step.

**Files:**
- Create: `frontend/src/features/settings/fieldAria.ts`, `LearningPathTab.tsx`, `PaceTab.tsx`, `ReviewingTab.tsx`, `SaveBar.tsx`, `SettingsTabs.tsx`, `settingsTestUtils.tsx`
- Modify: `frontend/src/features/settings/SettingsPage.tsx` (shell only), `SettingsPage.test.tsx`
- Modify: `docs/superpowers/specs/2026-09-23-bunsho-settings-tabs-design.md` (one paragraph, Step 6)

**Interfaces:**
- Consumes: Task 1 exports (`SETTINGS_TABS`, `SettingsFormApi`, …), `useSettingsTab` (Task 2), `SystemTab` (Task 6), and everything the old `SettingsPage.tsx` imported.
- Produces:
  - `groupAria(id: string, hasError: boolean)` in `fieldAria.ts`.
  - `LearningPathTab`, `PaceTab`, `ReviewingTab`: `({ form }: { form: SettingsFormApi }) => JSX.Element`.
  - `SaveBar({ dirty, saving, general, onRetry, onReset })`.
  - `SettingsTabs({ initial }: { initial: ReviewSettings })`.
  - Test utils: `serveSettings(initial?)`, `openSettings(initialEntries?)`, `openTab(user, name)`, `setNumber(user, name, value)`.

- [ ] **Step 1: Create the small shared pieces**

`fieldAria.ts` (moved verbatim from `SettingsPage.tsx`):

```ts
/** The ids of a `Input.Wrapper`'s label, description and (when shown) error, for a group's aria. */
export function groupAria(id: string, hasError: boolean) {
  return {
    role: 'group',
    'aria-labelledby': `${id}-label`,
    'aria-describedby': hasError ? `${id}-error ${id}-description` : `${id}-description`,
  };
}
```

`SaveBar.tsx`:

```tsx
import { Alert, Button, Group, Text } from '@mantine/core';

interface SaveBarProps {
  dirty: boolean;
  saving: boolean;
  /** A save problem that belongs to no field; `retryable` shows "Try again". */
  general: { message: string; retryable: boolean } | null;
  onRetry: () => void;
  onReset: () => void;
}

/** Save, Reset and the save problem; shown under the three settings tabs, not under System. */
export function SaveBar({ dirty, saving, general, onRetry, onReset }: SaveBarProps) {
  return (
    <>
      {general !== null && (
        <Alert color="red" title="Couldn't save your settings" mt="xl">
          <Text size="sm">{general.message}</Text>
          {general.retryable && (
            <Button mt="sm" size="xs" disabled={saving} onClick={onRetry}>
              Try again
            </Button>
          )}
        </Alert>
      )}
      <Group mt="xl">
        <Button type="submit" disabled={!dirty} loading={saving}>
          Save
        </Button>
        <Button variant="subtle" onClick={onReset}>
          Reset to recommended values
        </Button>
        {dirty && (
          <Text size="sm" c="dimmed">
            Unsaved changes
          </Text>
        )}
      </Group>
    </>
  );
}
```

(The label changes to "Reset all tabs to recommended values" in Task 8 with its own test.)

- [ ] **Step 2: Create the three tab components**

`LearningPathTab.tsx` (the old "New cards" section without the limits, plus "Kana first" and "Levels", moved as is):

```tsx
import { Chip, Group, Input, NumberInput, Stack, Switch, Text, Title } from '@mantine/core';
import { useId } from 'react';

import { groupAria } from './fieldAria';
import { PolicyField } from './PolicyField';
import { LEVELS, type Level, type SettingsFormApi } from './settingsForm';

type SwitchPath =
  | 'type_enabled.kana'
  | 'type_enabled.kanji'
  | 'type_enabled.vocab'
  | 'kana_gate.kanji'
  | 'kana_gate.vocab';

function isLevel(value: string): value is Level {
  return LEVELS.some((level) => level === value);
}

/** What to learn, and in what order: the policy, the type switches, the Kana first gate, levels. */
export function LearningPathTab({ form }: { form: SettingsFormApi }) {
  const levelsId = useId();
  const gateId = useId();
  const values = form.getValues();

  /** Set a switch and drop the kana-gate message, so a fixed problem stops being shown. */
  const setSwitch = (path: SwitchPath, checked: boolean) => {
    form.setFieldValue(path, checked);
    form.clearFieldError('kana_gate');
  };

  const pinned = values.new_card_policy === 'pinned_levels';
  const mastery = values.new_card_policy === 'mastery_unlock';
  const levelsError =
    typeof form.errors.active_levels === 'string' ? form.errors.active_levels : undefined;
  const gate = values.kana_gate;
  const gateError = typeof form.errors.kana_gate === 'string' ? form.errors.kana_gate : undefined;
  const thresholdError =
    typeof form.errors['kana_gate.threshold_percent'] === 'string'
      ? form.errors['kana_gate.threshold_percent']
      : undefined;
  // A hidden threshold that is invalid must still be shown, or Save would fail with no clue why.
  const showThreshold = gate.kanji || gate.vocab || thresholdError !== undefined;
  const kanaOff = !values.type_enabled.kana;

  return (
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
        <Stack gap="xs">
          <Switch
            label="Introduce new kana"
            checked={values.type_enabled.kana}
            onChange={(event) => {
              setSwitch('type_enabled.kana', event.currentTarget.checked);
            }}
          />
          <Switch
            label="Introduce new kanji"
            checked={values.type_enabled.kanji}
            onChange={(event) => {
              setSwitch('type_enabled.kanji', event.currentTarget.checked);
            }}
          />
          <Switch
            label="Introduce new vocabulary"
            checked={values.type_enabled.vocab}
            onChange={(event) => {
              setSwitch('type_enabled.vocab', event.currentTarget.checked);
            }}
          />
          <Text size="sm" c="dimmed">
            A type that is switched off introduces no new cards. Cards you already started stay due,
            so no progress is lost.
          </Text>
        </Stack>
      </Stack>

      <Stack gap="md">
        <Title order={3}>Kana first</Title>
        <Input.Wrapper
          id={gateId}
          label="Start kanji and vocabulary after kana"
          description="Hold them back until enough kana is learned. Your scheduled reviews are never held back."
          error={gateError}
          {...groupAria(gateId, gateError !== undefined)}
        >
          <Stack gap="xs" mt="xs">
            <Switch
              label="Wait for kana before starting kanji"
              checked={gate.kanji}
              disabled={kanaOff && !gate.kanji}
              onChange={(event) => {
                setSwitch('kana_gate.kanji', event.currentTarget.checked);
              }}
            />
            <Switch
              label="Wait for kana before starting vocabulary"
              checked={gate.vocab}
              disabled={kanaOff && !gate.vocab}
              onChange={(event) => {
                setSwitch('kana_gate.vocab', event.currentTarget.checked);
              }}
            />
            {kanaOff && (
              <Text size="sm" c="dimmed">
                Turn on new kana above to use this.
              </Text>
            )}
          </Stack>
        </Input.Wrapper>
        {showThreshold && (
          <NumberInput
            label="Kana needed before they start"
            description="Share of all kana cards (both directions, hiragana and katakana) that must be well known (in Review). If it drops below this later, new kanji and vocabulary pause until it recovers."
            min={0}
            max={100}
            allowDecimal={false}
            suffix="%"
            {...form.getInputProps('kana_gate.threshold_percent')}
          />
        )}
      </Stack>

      <Stack gap="md">
        <Title order={3}>Levels</Title>
        <Input.Wrapper
          id={levelsId}
          label="Levels to study"
          description={
            pinned ? 'New cards come only from these levels.' : 'Only used by "Pinned levels".'
          }
          error={levelsError}
          {...groupAria(levelsId, levelsError !== undefined)}
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
    </Stack>
  );
}
```

`PaceTab.tsx`:

```tsx
import { Group, Input, NativeSelect, NumberInput, Slider, Stack, Text, Title } from '@mantine/core';
import { useId } from 'react';

import { groupAria } from './fieldAria';
import {
  LIMIT_MAX,
  RETENTION_MAX_PERCENT,
  RETENTION_MIN_PERCENT,
  type SettingsFormApi,
} from './settingsForm';

const HOURS = Array.from({ length: 24 }, (_, hour) => ({
  value: String(hour),
  label: `${hour}:00`,
}));

/** How much and how often: daily new-card limits, when the study day starts, target retention. */
export function PaceTab({ form }: { form: SettingsFormApi }) {
  const retentionId = useId();
  const values = form.getValues();
  const retentionError =
    typeof form.errors.target_retention_percent === 'string'
      ? form.errors.target_retention_percent
      : undefined;

  return (
    <Stack gap="xl">
      <Stack gap="md">
        <Title order={3}>Daily limits</Title>
        <Group grow align="flex-start">
          <NumberInput
            label="Kana per day"
            min={0}
            max={LIMIT_MAX}
            allowDecimal={false}
            disabled={!values.type_enabled.kana}
            {...form.getInputProps('new_limits.kana')}
          />
          <NumberInput
            label="Kanji per day"
            min={0}
            max={LIMIT_MAX}
            allowDecimal={false}
            disabled={!values.type_enabled.kanji}
            {...form.getInputProps('new_limits.kanji')}
          />
          <NumberInput
            label="Vocabulary per day"
            min={0}
            max={LIMIT_MAX}
            allowDecimal={false}
            disabled={!values.type_enabled.vocab}
            {...form.getInputProps('new_limits.vocab')}
          />
        </Group>
        <Text size="sm" c="dimmed">
          The most new cards of each type per day. 0 means no limit.
        </Text>
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

      <Stack gap="md">
        <Title order={3}>Scheduling</Title>
        <Input.Wrapper
          id={retentionId}
          label={`Target retention: ${String(values.target_retention_percent)}%`}
          description="How often you want to remember a card when it comes back. Higher means more reviews."
          error={retentionError}
          {...groupAria(retentionId, retentionError !== undefined)}
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
            thumbValueText={`${String(values.target_retention_percent)}%`}
            marks={[
              { value: 70, label: '70%' },
              { value: 80, label: '80%' },
              { value: 90, label: '90%' },
              { value: 99, label: '99%' },
            ]}
          />
        </Input.Wrapper>
      </Stack>
    </Stack>
  );
}
```

`ReviewingTab.tsx`:

```tsx
import { NativeSelect, Stack, Title } from '@mantine/core';

import { REVIEW_MODES, type SettingsFormApi, type SettingsFormValues } from './settingsForm';

const REVIEW_MODE_OPTIONS = REVIEW_MODES.map((mode) => ({ value: mode.value, label: mode.label }));

/** How you answer: the review mode of each card type. */
export function ReviewingTab({ form }: { form: SettingsFormApi }) {
  const values = form.getValues();
  const select = (
    field: 'kana_mode' | 'kanji_mode' | 'vocab_mode',
    label: string,
  ) => (
    <NativeSelect
      label={label}
      data={REVIEW_MODE_OPTIONS}
      value={values[field]}
      onChange={(event) => {
        form.setFieldValue(field, event.currentTarget.value as SettingsFormValues[typeof field]);
      }}
    />
  );

  return (
    <Stack gap="md">
      <Title order={3}>How you answer</Title>
      {select('kana_mode', 'Kana review mode')}
      {select('kanji_mode', 'Kanji review mode')}
      {select('vocab_mode', 'Vocabulary review mode')}
    </Stack>
  );
}
```

- [ ] **Step 3: Create the shell and slim `SettingsPage.tsx`**

`SettingsTabs.tsx`:

```tsx
import { Skeleton, Tabs } from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { lazy, Suspense, useState } from 'react';

import type { ReviewSettings, ReviewSettingsInput } from '../../api/endpoints';
import { ApiError, messageFor } from '../../api/errors';
import { useUpdateSettings } from '../../api/queries';
import { LearningPathTab } from './LearningPathTab';
import { PaceTab } from './PaceTab';
import { ReviewingTab } from './ReviewingTab';
import { SaveBar } from './SaveBar';
import {
  RECOMMENDED_SETTINGS,
  SETTINGS_TABS,
  isSettingsDirty,
  placeServerErrors,
  toFormValues,
  toRequest,
  validateSettings,
  type SettingsFormValues,
} from './settingsForm';
import { useSettingsTab } from './useSettingsTab';

// The System tab carries the build UI; load it only when somebody opens it.
const SystemTab = lazy(() =>
  import('./SystemTab').then((module) => ({ default: module.SystemTab })),
);

/** The tabs and the one settings form, seeded once from `initial`: a refetch never replaces edits. */
export function SettingsTabs({ initial }: { initial: ReviewSettings }) {
  const save = useUpdateSettings();
  const [tab, setTab] = useSettingsTab();
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

  const dirty = isSettingsDirty(form.getValues(), form.getInitialValues());

  return (
    <Tabs value={tab} onChange={setTab} keepMounted={false}>
      <Tabs.List aria-label="Settings sections">
        {SETTINGS_TABS.map(({ value, label }) => (
          <Tabs.Tab key={value} value={value}>
            {label}
          </Tabs.Tab>
        ))}
      </Tabs.List>

      <form
        onSubmit={form.onSubmit((submitted) => {
          submit(toRequest(submitted));
        })}
        noValidate
      >
        <Tabs.Panel value="learning" pt="md" keepMounted>
          <LearningPathTab form={form} />
        </Tabs.Panel>
        <Tabs.Panel value="pace" pt="md" keepMounted>
          <PaceTab form={form} />
        </Tabs.Panel>
        <Tabs.Panel value="reviewing" pt="md" keepMounted>
          <ReviewingTab form={form} />
        </Tabs.Panel>
        {tab !== 'system' && (
          <SaveBar
            dirty={dirty}
            saving={save.isPending}
            general={general}
            onRetry={() => {
              if (save.variables !== undefined) submit(save.variables);
            }}
            onReset={() => {
              form.setValues(toFormValues(RECOMMENDED_SETTINGS));
            }}
          />
        )}
      </form>

      <Tabs.Panel value="system" pt="md">
        <Suspense fallback={<Skeleton height={240} />}>
          <SystemTab />
        </Suspense>
      </Tabs.Panel>
    </Tabs>
  );
}
```

Replace the whole of `SettingsPage.tsx` with:

```tsx
import { Alert, Button, Skeleton, Stack, Text, Title } from '@mantine/core';

import { messageFor } from '../../api/errors';
import { useSettings } from '../../api/queries';
import { SettingsTabs } from './SettingsTabs';

/** How new cards are chosen and gated, how many, how you answer, and the service's status. */
export function SettingsPage() {
  const settings = useSettings();

  return (
    <Stack gap="lg" maw={720}>
      <Title order={2}>Settings</Title>
      {settings.isPending && <Skeleton height={320} />}
      {settings.isError && settings.data === undefined && (
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
      {settings.data !== undefined && <SettingsTabs initial={settings.data} />}
    </Stack>
  );
}
```

- [ ] **Step 4: Extract the test utilities**

Create `settingsTestUtils.tsx` (moved from the top of `SettingsPage.test.tsx`, with `openSettings` taking an entry list and a new `openTab`):

```tsx
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import type { InitialEntry } from 'react-router';

import type { ReviewSettings } from '../../api/endpoints';
import { makeSettings } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { SettingsPage } from './SettingsPage';

export type User = ReturnType<typeof userEvent.setup>;

/** Serve the settings and record every PUT body; the server echoes the document it was sent. */
export function serveSettings(initial: ReviewSettings = makeSettings()) {
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

export async function openSettings(initialEntries: InitialEntry[] = ['/settings']) {
  const view = renderWithProviders(<SettingsPage />, { initialEntries });
  await screen.findByRole('button', { name: 'Save' });
  return view;
}

/** Click the named tab ("Pace"); the accessible name may gain " (has errors)". */
export async function openTab(user: User, name: string) {
  await user.click(screen.getByRole('tab', { name: new RegExp(`^${name}`) }));
}

export async function setNumber(user: User, name: string, value: string) {
  const input = screen.getByRole('textbox', { name });
  await user.clear(input);
  if (value !== '') await user.type(input, value);
}
```

In `SettingsPage.test.tsx`: delete the local `serveSettings`, `openSettings`, `setNumber` definitions and their now-unused imports, and add `import { openSettings, openTab, serveSettings, setNumber } from './settingsTestUtils';`.

- [ ] **Step 5: Run the old tests unchanged, then add `openTab`**

Run: `npx vitest run src/features/settings/SettingsPage.test.tsx`
Expected: FAIL for exactly the tests that touch a control that is not on the default (Learning path) tab. **First failing test decides the rest:** confirm how Testing Library sees a hidden (inactive) panel. If `getByRole` skips its controls (expected, since inactive panels are hidden), every failure is fixable with `await openTab(user, '<tab>')` before the first query of that tab's control. If some role queries still find controls in a hidden panel, keep the `openTab` calls anyway (they make the tests describe what a person does) and note it in the commit message.

Where each control lives (use this to decide which `openTab` a test needs; a test that touches several tabs opens each before reading that tab's control; `user` is `userEvent.setup()`, create it where a test lacks one):

| Tab | Controls |
|---|---|
| Learning path | policy radios; "Introduce new kana/kanji/vocabulary"; "Wait for kana before starting kanji/vocabulary"; "Kana needed before they start"; level checkboxes N5–N1; "Mastery needed…" |
| Pace | "Kana per day", "Kanji per day", "Vocabulary per day"; "A new study day starts at"; the "Target retention" slider |
| Reviewing | "Kana review mode", "Kanji review mode", "Vocabulary review mode" |

Save, Reset and "Try again" are on every settings tab. Do not change any assertion; only add the `openTab` calls. Where a `beforeEach`-style helper renders and immediately asserts on a Pace or Reviewing control, open the tab right after `openSettings()`.

Run until green: `npx vitest run src/features/settings`
Expected: PASS (every pre-existing settings test, plus the new files from Tasks 1–6).

- [ ] **Step 6: Correct the spec's `keepMounted` wording**

Mantine's `keepMounted` is a root prop and a per-panel prop that can force a panel to stay mounted. The plan sets the root to `false` and the three form panels to `keepMounted`, so the System panel is the one that unmounts. In `docs/superpowers/specs/2026-09-23-bunsho-settings-tabs-design.md`, in the "Using Mantine Tabs" snippet change `<Tabs value={tab} onChange={setTab}>` to `<Tabs value={tab} onChange={setTab} keepMounted={false}>`, add `keepMounted` to the three settings `Tabs.Panel` lines, and remove `keepMounted={false}` from the System panel line. In the bullets, replace the two `keepMounted` bullets with:

```
- **Root `keepMounted={false}`, and `keepMounted` on the three settings panels.** The settings panels
  stay mounted (Mantine's default `activity` mode hides them and pauses their effects), so field
  state, error placement and the `aria-describedby` wiring of the group controls do not depend on
  which tab is showing. The System panel inherits the root value and unmounts when hidden, so its
  health, content-summary, config-check and build-status queries run only while System is open.
```

- [ ] **Step 7: Verify and commit**

Run: `npx tsc -b && npm run lint && npx vitest run src/features/settings`
Expected: no type or lint errors; PASS.

```bash
npm run format -- src/features/settings
git add src/features/settings ../docs/superpowers/specs/2026-09-23-bunsho-settings-tabs-design.md
git commit -m "refactor(settings): split the form into three Mantine tabs" -m "One form and one Save; the System panel sits outside the form. Behaviour is unchanged; the tests now open the tab that holds the control they use." -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 8: Error marks, the jump, the cross-tab hint and the reset label

**Files:**
- Modify: `frontend/src/features/settings/SettingsTabs.tsx`, `SaveBar.tsx`, `PaceTab.tsx`, `ReviewingTab.tsx`
- Modify: `frontend/src/features/settings/SettingsPage.test.tsx`, `frontend/src/App.test.tsx` (reset label)
- Test: `frontend/src/features/settings/SettingsTabs.test.tsx` (new)

**Interfaces:**
- Consumes: `tabsWithErrors`, `firstTabWithErrors`, `firstErrorPathIn` (Task 1); `form.getInputNode(path)` from `@mantine/form`; the test utils (Task 7).
- Produces: a red tab with a dot and hidden text " (has errors)" for a tab holding an error; on a failed Save or a placed 422, the tab switches to the first errored tab and focuses its first errored field when that field is an input the form tracks; the reset button reads "Reset all tabs to recommended values"; a disabled daily limit reads "Switched off in Learning path."; the three review-mode selects show their error.

- [ ] **Step 1: Write the failing tests**

`SettingsTabs.test.tsx`:

```tsx
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { useLocation } from 'react-router';
import { beforeEach, describe, expect, it } from 'vitest';

import { session } from '../../auth/session';
import { makeBuildStatus, makeSettings } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { SettingsPage } from './SettingsPage';
import { openSettings, openTab, serveSettings, setNumber } from './settingsTestUtils';

function tabNamed(name: string | RegExp) {
  return screen.getByRole('tab', { name });
}

/** Serve the System tab's reads and count how often each is asked. */
function serveSystem(latest: unknown = null) {
  const calls = { health: 0, summary: 0, checks: 0, build: 0 };
  server.use(
    http.get('/api/v1/health', () => {
      calls.health += 1;
      return HttpResponse.json({ status: 'ok', version: '1.2.0', components: {} });
    }),
    http.get('/api/v1/content/summary', () => {
      calls.summary += 1;
      return HttpResponse.json({
        built: true,
        kana: 1,
        kanji: 1,
        vocab: 1,
        unleveled_kanji: 0,
        kanji_by_level: {},
        vocab_by_level: {},
        meta: {},
      });
    }),
    http.get('/api/v1/admin/config-check', () => {
      calls.checks += 1;
      return HttpResponse.json({ ok: true, checks: [] });
    }),
    http.get('/api/v1/admin/content/build', () => {
      calls.build += 1;
      return latest === null
        ? HttpResponse.json({ detail: 'no build has run yet' }, { status: 404 })
        : HttpResponse.json(latest);
    }),
  );
  return calls;
}

function LocationProbe() {
  return <output data-testid="location">{useLocation().search}</output>;
}

describe('Settings tabs', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  it('shows four tabs with Learning path selected by default', async () => {
    serveSettings();
    await openSettings();
    expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual([
      'Learning path',
      'Pace',
      'Reviewing',
      'System',
    ]);
    expect(tabNamed('Learning path')).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tablist', { name: 'Settings sections' })).toBeInTheDocument();
  });

  it('selects the tab named in the URL, and falls back on an unknown one', async () => {
    serveSettings();
    await openSettings(['/settings?tab=pace']);
    expect(tabNamed('Pace')).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('textbox', { name: 'Kana per day' })).toBeInTheDocument();
  });

  it('opens Learning path for a tab name it does not know', async () => {
    serveSettings();
    await openSettings(['/settings?tab=admin']);
    expect(tabNamed('Learning path')).toHaveAttribute('aria-selected', 'true');
  });

  it('writes the chosen tab to the URL', async () => {
    const user = userEvent.setup();
    serveSettings();
    renderWithProviders(
      <>
        <SettingsPage />
        <LocationProbe />
      </>,
      { initialEntries: ['/settings'] },
    );
    await screen.findByRole('button', { name: 'Save' });
    await openTab(user, 'Reviewing');
    expect(screen.getByTestId('location')).toHaveTextContent('?tab=reviewing');
  });

  it('keeps an edit when the person switches tabs and back', async () => {
    const user = userEvent.setup();
    serveSettings();
    await openSettings();
    await openTab(user, 'Pace');
    await setNumber(user, 'Kana per day', '30');
    await openTab(user, 'Reviewing');
    await openTab(user, 'Pace');
    expect(screen.getByRole('textbox', { name: 'Kana per day' })).toHaveValue('30');
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
  });

  it('saves the edits of every tab in one request', async () => {
    const user = userEvent.setup();
    const puts = serveSettings();
    await openSettings();
    await openTab(user, 'Pace');
    await setNumber(user, 'Kana per day', '30');
    await openTab(user, 'Reviewing');
    await user.selectOptions(screen.getByLabelText('Kana review mode'), 'Typed answer');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    await screen.findByText('Settings saved');
    expect(puts).toEqual([
      makeSettings({ new_limits: { kana: 30, kanji: 15, vocab: 20 }, kana_mode: 'typed' }),
    ]);
  });

  it('has no Save or Reset on the System tab, and its button cannot submit the form', async () => {
    const user = userEvent.setup();
    const puts = serveSettings();
    serveSystem();
    await openSettings();
    await openTab(user, 'System');
    await screen.findByRole('region', { name: 'Server' });
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /Reset all tabs to recommended values/ }),
    ).not.toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: 'Build content' }));
    expect(puts).toEqual([]);
  });

  it('does not ask the System endpoints until the System tab is opened', async () => {
    const user = userEvent.setup();
    serveSettings();
    const calls = serveSystem();
    await openSettings();
    await openTab(user, 'Pace');
    expect(calls).toEqual({ health: 0, summary: 0, checks: 0, build: 0 });
    await openTab(user, 'System');
    await screen.findByRole('region', { name: 'Server' });
    expect(calls.health).toBeGreaterThan(0);
    expect(calls.summary).toBeGreaterThan(0);
  });

  it('shows a running build again after leaving the System tab and coming back', async () => {
    const user = userEvent.setup();
    serveSettings();
    serveSystem(makeBuildStatus());
    await openSettings();
    await openTab(user, 'System');
    expect(await screen.findByText('Reading the vocabulary deck')).toBeInTheDocument();
    await openTab(user, 'Pace');
    expect(screen.queryByText('Reading the vocabulary deck')).not.toBeInTheDocument();
    await openTab(user, 'System');
    expect(await screen.findByText('Reading the vocabulary deck')).toBeInTheDocument();
  });

  it('says why a daily limit is greyed out, pointing at the tab that holds the switch', async () => {
    const user = userEvent.setup();
    serveSettings();
    await openSettings();
    await user.click(screen.getByRole('switch', { name: 'Introduce new kanji' }));
    await openTab(user, 'Pace');
    expect(screen.getByRole('textbox', { name: 'Kanji per day' })).toBeDisabled();
    expect(screen.getAllByText('Switched off in Learning path.')).toHaveLength(1);
  });
});

describe('Settings tabs: errors on another tab', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  it('marks the tab, jumps to it and focuses the field when Save finds a bad value', async () => {
    const user = userEvent.setup();
    const puts = serveSettings();
    await openSettings();
    await openTab(user, 'Pace');
    await setNumber(user, 'Kana per day', '');
    await openTab(user, 'Learning path');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(tabNamed(/^Pace/)).toHaveAttribute('aria-selected', 'true');
    });
    expect(tabNamed('Pace (has errors)')).toBeInTheDocument();
    expect(tabNamed('Learning path')).not.toHaveAccessibleName(/has errors/);
    await waitFor(() => {
      expect(screen.getByRole('textbox', { name: 'Kana per day' })).toHaveFocus();
    });
    expect(puts).toEqual([]);
  });

  it('marks a tab while the person is on another one, and clears the mark once fixed', async () => {
    const user = userEvent.setup();
    serveSettings();
    await openSettings();
    await openTab(user, 'Pace');
    await setNumber(user, 'Kana per day', '');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    await openTab(user, 'Reviewing');
    expect(tabNamed('Pace (has errors)')).toBeInTheDocument();

    await openTab(user, 'Pace');
    await setNumber(user, 'Kana per day', '5');
    expect(tabNamed('Pace')).toBeInTheDocument();
  });

  it('jumps to the first errored tab in tab order when several have errors', async () => {
    const user = userEvent.setup();
    serveSettings();
    await openSettings();
    // Gate on first (its switch is disabled once kana is off), then kana off: the Learning-path error.
    await user.click(screen.getByRole('switch', { name: 'Wait for kana before starting kanji' }));
    await user.click(screen.getByRole('switch', { name: 'Introduce new kana' }));
    // Add a Pace error too; Learning path must still win.
    await openTab(user, 'Pace');
    await setNumber(user, 'Kanji per day', '');
    await openTab(user, 'Reviewing');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => {
      expect(tabNamed(/^Learning path/)).toHaveAttribute('aria-selected', 'true');
    });
  });

  it('shows the message of a server 422 on a review-mode field and jumps to its tab', async () => {
    const user = userEvent.setup();
    serveSettings();
    server.use(
      http.put('/api/v1/settings', () =>
        HttpResponse.json(
          {
            detail: [
              { loc: ['body', 'kana_mode'], msg: 'Not an allowed mode', type: 'value_error' },
            ],
          },
          { status: 422 },
        ),
      ),
    );
    await openSettings();
    await openTab(user, 'Reviewing');
    await user.selectOptions(screen.getByLabelText('Kana review mode'), 'Typed answer');
    await openTab(user, 'Learning path');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(tabNamed(/^Reviewing/)).toHaveAttribute('aria-selected', 'true');
    });
    expect(tabNamed('Reviewing (has errors)')).toBeInTheDocument();
    expect(screen.getByText('Not an allowed mode')).toBeInTheDocument();
  });

  it('clears every tab mark when Reset refills the form', async () => {
    const user = userEvent.setup();
    serveSettings();
    await openSettings();
    await openTab(user, 'Pace');
    await setNumber(user, 'Kana per day', '');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(tabNamed('Pace (has errors)')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Reset all tabs to recommended values' }));
    expect(tabNamed('Pace')).toBeInTheDocument();
    expect(within(screen.getByRole('tablist')).queryByText(/has errors/)).not.toBeInTheDocument();
  });
});
```

Also, in `SettingsPage.test.tsx` and `App.test.tsx` replace every `'Reset to recommended values'` (button name, test title) with `'Reset all tabs to recommended values'` (`sed -i "s/Reset to recommended values/Reset all tabs to recommended values/g" src/features/settings/SettingsPage.test.tsx src/App.test.tsx`).

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/features/settings/SettingsTabs.test.tsx`
Expected: FAIL (no error marks, no jump, no hint, old reset label, review-mode errors not shown).

- [ ] **Step 3: Implement**

`SaveBar.tsx`: change the reset button text to `Reset all tabs to recommended values`.

`ReviewingTab.tsx`: show each select's error. Replace the `select` helper's `NativeSelect` with:

```tsx
    <NativeSelect
      label={label}
      data={REVIEW_MODE_OPTIONS}
      value={values[field]}
      error={typeof form.errors[field] === 'string' ? form.errors[field] : undefined}
      onChange={(event) => {
        form.setFieldValue(field, event.currentTarget.value as SettingsFormValues[typeof field]);
      }}
    />
```

`PaceTab.tsx`: give each daily-limit input a hint when its type is off. Add above the component:

```tsx
const SWITCHED_OFF = 'Switched off in Learning path.';
```

and to each of the three `NumberInput`s add, next to `disabled`, e.g. for kana: `description={values.type_enabled.kana ? undefined : SWITCHED_OFF}` (kanji → `values.type_enabled.kanji`, vocabulary → `values.type_enabled.vocab`).

`SettingsTabs.tsx`: add the marks and the jump. Add imports `Box, VisuallyHidden` (from `@mantine/core`) and `firstErrorPathIn, firstTabWithErrors, tabsWithErrors, type FormTab` (from `./settingsForm`), then:

```tsx
/** After a failed Save or a placed 422: show the first tab with an error, and focus its field. */
const showFirstError = (errors: Readonly<Record<string, unknown>>) => {
  const target = firstTabWithErrors(errors);
  if (target === null) return;
  setTab(target);
  const path = firstErrorPathIn(errors, target);
  if (path === null) return;
  // The panel is shown on the next render; focus what the form tracks (not every control is one).
  window.setTimeout(() => {
    form.getInputNode(path)?.focus();
  }, 0);
};
```

Call it in the `onError` 422 branch right after `form.setErrors(placed.fields)` (`showFirstError(placed.fields);`) and as the second argument of `form.onSubmit`:

```tsx
onSubmit={form.onSubmit(
  (submitted) => {
    submit(toRequest(submitted));
  },
  (errors) => {
    showFirstError(errors);
  },
)}
```

Compute `const errorTabs = tabsWithErrors(form.errors);` next to `dirty`, and render each tab as:

```tsx
{SETTINGS_TABS.map(({ value, label }) => {
  const failing = value !== 'system' && errorTabs.has(value as FormTab);
  return (
    <Tabs.Tab
      key={value}
      value={value}
      color={failing ? 'red' : undefined}
      rightSection={
        failing ? (
          <Box component="span" w={8} h={8} bg="red" style={{ borderRadius: '50%' }} aria-hidden />
        ) : null
      }
    >
      {label}
      {failing && <VisuallyHidden> (has errors)</VisuallyHidden>}
    </Tabs.Tab>
  );
})}
```

Make `showFirstError` a function declared before `submit` (it is used inside `submit`), or hoist `submit` below it; keep `setTab` from the hook in scope.

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run src/features/settings src/App.test.tsx && npx tsc -b && npm run lint`
Expected: PASS. If the focus assertion is flaky because `setTimeout(…, 0)` runs before Mantine shows the panel, replace it with a `useEffect` keyed on a `pendingFocus` ref/state set in `showFirstError` (focus after the tab has actually changed); keep the same test.

- [ ] **Step 5: Commit**

```bash
npm run format -- src/features/settings src/App.test.tsx
git add src/features/settings src/App.test.tsx
git commit -m "feat(settings): mark tabs with errors and jump to the first one" -m "A red dot and hidden text on a tab that holds an error; a failed Save or a server 422 moves to that tab and focuses its field. The review-mode selects now show their error, the greyed-out daily limits say where the switch is, and the reset button says it resets all tabs." -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 9: Routing: redirect `/build`, drop the nav item, repoint the first-run links

**Files:**
- Modify: `frontend/src/App.tsx`, `frontend/src/components/AppLayout.tsx`
- Modify: `frontend/src/features/home/HomePage.tsx`, `frontend/src/features/review/ReviewFinished.tsx`, `frontend/src/features/stats/StatsPage.tsx`
- Modify tests: `frontend/src/App.test.tsx`, `frontend/src/components/AppLayout.test.tsx`, `frontend/src/features/home/HomePage.test.tsx`, `frontend/src/features/review/ReviewPage.test.tsx`, `frontend/src/features/stats/StatsPage.test.tsx`

**Interfaces:**
- Consumes: the `/settings?tab=system` URL (Tasks 2 and 7).
- Produces: the redirect route and the new link target.

- [ ] **Step 1: Write / update the failing tests**

`AppLayout.test.tsx`: in `'frames the page…'` replace the `Build content` link assertion with `expect(screen.queryByRole('link', { name: 'Build content' })).not.toBeInTheDocument();`; in the test's route table (`renderLayout`) replace `<Route path="build" element={<p>Build content page</p>} />` with `<Route path="settings" element={<p>Settings page</p>} />`; in `'navigates between pages'` click the `Settings` link and expect `Settings page`, then `Home`.

`HomePage.test.tsx`, `ReviewPage.test.tsx`, `StatsPage.test.tsx`: change each route table entry `path="build"` / `path="/build"` to `path="settings"` / `path="/settings"` (keeping the element text), and every `'/build'` href expectation to `'/settings?tab=system'`. In `HomePage.test.tsx` the click-through assertion (`screen.getByText('Build page')`) stays.

`App.test.tsx`: add to `rememberLogin()` the handler
`http.get('/api/v1/health', () => HttpResponse.json({ status: 'ok', version: '1.2.0', components: {} })),`
and replace the two build tests:

```tsx
  it('reaches the build tools through Settings, System', async () => {
    rememberLogin();
    render(<App />);
    const user = userEvent.setup();
    expect(screen.queryByRole('link', { name: 'Build content' })).not.toBeInTheDocument();
    await user.click(await screen.findByRole('link', { name: 'Settings' }));
    await user.click(await screen.findByRole('tab', { name: 'System' }));
    expect(await screen.findByRole('heading', { name: 'Build' })).toBeInTheDocument();
    expect(window.location.pathname).toBe('/settings');
    expect(window.location.search).toBe('?tab=system');
    await user.click(screen.getByRole('link', { name: 'Home' }));
    expect(await screen.findByRole('heading', { name: 'Your content' })).toBeInTheDocument();
  });

  it('sends an old /build link to the System tab', async () => {
    rememberLogin();
    goTo('/build');
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Build' })).toBeInTheDocument();
    expect(window.location.pathname).toBe('/settings');
    expect(window.location.search).toBe('?tab=system');
    expect(screen.getByRole('tab', { name: 'System' })).toHaveAttribute('aria-selected', 'true');
  });
```

(`beforeAll` in `App.test.tsx` already pre-imports the lazy settings page; also add `await import('./features/settings/SystemTab');` there.)

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/App.test.tsx src/components src/features/home src/features/review/ReviewPage.test.tsx src/features/stats`
Expected: FAIL (old route and links still in place).

- [ ] **Step 3: Implement**

`App.tsx`: import `Navigate` (`import { BrowserRouter, Navigate, Route, Routes } from 'react-router';`), delete the temporary `BuildPage` lazy constant from Task 5, and replace `<Route path="build" element={<BuildPage />} />` with:

```tsx
<Route path="build" element={<Navigate to="/settings?tab=system" replace />} />
```

`AppLayout.tsx`: delete the line `{ to: '/build', label: 'Build content' },` from `NAVIGATION`.

`HomePage.tsx`, `ReviewFinished.tsx`, `StatsPage.tsx`: change `to="/build"` to `to="/settings?tab=system"` on the "Build your content" button (one occurrence each).

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run && npx tsc -b && npm run lint`
Expected: the whole frontend suite PASSES (this includes the two tests noted as failing in Task 5).

- [ ] **Step 5: Commit**

```bash
npm run format -- src
git add -A src
git commit -m "feat(ui): move Build content into Settings, System and redirect /build" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 10: Release 1.2.0, docs and full verification

**Files:**
- Modify: `pyproject.toml`, `src/bunsho/__init__.py`, `uv.lock`, `frontend/package.json`, `frontend/package-lock.json` (two places), `frontend/openapi.json`
- Modify: `CHANGELOG.md`, `README.md`

**Interfaces:** none.

- [ ] **Step 1: Bump the version (from the repository root)**

```bash
cd "D:/Documents/Code/Bunshō"
python - <<'EOF'
import re
from pathlib import Path

def sub(path, old, new, count=1):
    p = Path(path); s = p.read_text(encoding="utf-8")
    assert s.count(old) >= count, (path, old)
    p.write_text(s.replace(old, new, count), encoding="utf-8")

sub("pyproject.toml", 'version = "1.1.2"', 'version = "1.2.0"')
sub("src/bunsho/__init__.py", '__version__ = "1.1.2"', '__version__ = "1.2.0"')
sub("frontend/package.json", '"version": "1.1.2"', '"version": "1.2.0"')
sub("frontend/package-lock.json", '"version": "1.1.2"', '"version": "1.2.0"', count=2)
sub("frontend/openapi.json", '"version": "1.1.2"', '"version": "1.2.0"')
p = Path("uv.lock"); s = p.read_text(encoding="utf-8")
s2 = re.sub(r'(name = "bunsho"\nversion = )"1\.1\.2"', r'\1"1.2.0"', s)
assert s != s2; p.write_text(s2, encoding="utf-8")
EOF
git diff --stat
```

Expected: one-line changes in each of the seven files (the CRLF warnings are only git's autocrlf notices).

- [ ] **Step 2: Changelog and README**

In `CHANGELOG.md`, directly under `## [Unreleased]` insert:

```markdown
## [1.2.0] - 2026-09-23

### Added

- Settings, System tab: the service version and the health of each component (`GET /health`), whether
  the study content is built with its kana, kanji and vocabulary counts, the environment checks and
  the content build, all in one place.

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
```

In `README.md`, in the paragraph that begins `**Statistics and settings.**`, replace the sentence starting `*Settings* holds every review setting in one form:` through `…the hour a new study day starts (in the server's timezone).` with:

```
*Settings* has four tabs: *Learning path* (how new cards are chosen, which types introduce new cards, the optional *Kana first* gate, the levels used by *Pinned levels* and the mastery threshold used by *Mastery unlock*), *Pace* (the daily new-card limits, where 0 means unlimited, the hour a new study day starts in the server's timezone, and your target retention), *Reviewing* (how you answer each type of card) and *System* (the service's status and *Build content*).
```

and keep the following sentences (`Nothing is saved until you press *Save*; …`), changing "*Reset to recommended values* only refills the form" to "*Reset all tabs to recommended values* only refills the form". Also replace any other README mention of a "Build content" page or the `/build` address with "Settings, System".

- [ ] **Step 3: Full verification**

```bash
cd frontend && npm run format:check && npm run lint && npx tsc -b && npx vitest run && npm run build && cd ..
uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src && uv run pytest -q
```

Expected: everything passes (626 Python tests; the frontend suite green). If `npm run format:check` complains about a touched file, run `npm run format` on it and re-run.

- [ ] **Step 4: Look at it in a browser**

Start the service and the frontend as the README describes, open Settings, and check by eye: four tabs, the wrap at a narrow window, an error mark after clearing "Kana per day" and saving from another tab, the System tab's four blocks, and `/build` landing on System. Report anything that looks wrong instead of fixing it silently.

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md README.md pyproject.toml src/bunsho/__init__.py uv.lock frontend/package.json frontend/package-lock.json frontend/openapi.json
git commit -m "chore(release): bump version to 1.2.0" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Self-review (done while writing)

- **Spec coverage:** grouping and tab contents → Task 7; controlled Mantine `Tabs`, `Tabs.List aria-label`, per-tab `color`/`rightSection`, `keepMounted` handling → Task 7 (structure) and Task 8 (marks); tab in URL and replace → Tasks 2 and 7; one form and no Save on System → Task 7; hidden-tab errors, jump, focus, the every-field-mapped guard → Tasks 1 and 8; cross-tab hint → Task 8; reset label → Task 8; System blocks and the `/health` 503 client → Tasks 3, 4, 6; `/build` redirect, nav removal, three links → Task 9; lazy System → Task 7; release and docs → Task 10.
- **Deviations from the spec, stated:** `keepMounted` is set on the root (`false`) and on the three settings panels, not the reverse. Verified in the installed `@mantine/core` (`TabsPanel.mjs`): a panel keeps its content when `ctx.keepMounted || keepMounted`, so a panel-level `false` cannot override a root-level `true` and the spec's original wording would have left System mounted (the spec is corrected in Task 7, Step 6). Focusing the first invalid field uses `form.getInputNode(path)`, which the installed `@mantine/form` implements as `document.querySelector('[data-path=…]')`; only controls spread from `form.getInputProps` carry `data-path` (the numeric limits, the thresholds), so focus is best effort for the rest (the tab still switches and shows the mark).
- **Verified in the installed Mantine, relevant to the tests:** in `env="test"` (the test provider) `Tabs.Panel` does not use React `Activity`; an inactive kept-mounted panel renders with an inline `display: none`, so Testing Library's role queries skip its controls.
- **Type consistency:** `SettingsFormApi`, `SettingsTab`, `FormTab`, `tabsWithErrors`, `firstTabWithErrors`, `firstErrorPathIn`, `useSettingsTab`, `rawRequestAllowing`, `endpoints.health`, `useHealth`, `ServerStatus`, `ContentStatus`, `BuildPanel`, `SystemTab`, `SaveBar`, `SettingsTabs` are named identically wherever they appear.
- **Placeholder scan:** none; where a step cannot know the outcome in advance (how Testing Library sees a hidden panel; focus timing), it says what to check and what to do in each case.
