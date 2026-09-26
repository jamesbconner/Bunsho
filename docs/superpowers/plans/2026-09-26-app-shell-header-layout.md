# Header Navigation and Consistent Page Widths Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put every logged-in page in a centered, width-limited column (narrow 720 px or wide 1100 px), and move the navigation from the sidebar into the header, with an Account menu on desktop and a burger + drawer on phones.

**Architecture:** Two pathless layout routes in `App.tsx` wrap the pages in one `PageWidth` component (a Mantine `Container` around `ErrorBoundary` + `Suspense` + `Outlet`), so pages stop setting their own width and loading and error states share the page's width. `AppLayout` loses its navbar and gains a header with inline links; `AccountMenu` (Mantine `Menu`) and `NavDrawer` (Mantine `Drawer`) hold Log out and its note. No routing, auth or backend change.

**Tech Stack:** React 19, TypeScript (strict), Mantine 9.6, react-router 8 (`BrowserRouter`), Vitest + Testing Library + msw.

**Spec:** `docs/superpowers/specs/2026-09-26-bunsho-app-shell-header-layout-design.md`

**Verified by prototype:** every source and test file below (except the small edits inside existing files) was built in a scratch worktree from `origin/main` and passed `tsc -b`, `eslint .`, `prettier --check .` and `vitest run` (47 files, 498 tests). A throwaway preview page was also inspected in Chrome (wide, narrow, 390 px and 360 px). Copy the code as written; do not "improve" it.

## Global Constraints

- Branch `fix/app-shell-header-layout`, created from an up-to-date `main` (the spec and this plan are already on `main` once their PRs merge). Never merge; James reviews and merges. Open the PR yourself when done.
- Commits: conventional commits, stage explicit paths only, `git commit -m "<subject>" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"` (the trailer is its own paragraph). Never stage `.gitignore`, `.github/`, `.python-version`, `.superpowers/`, `.env.example` (untracked, stays that way), `frontend/preview.html`, `frontend/src/preview.tsx`.
- Release is a **bug fix: 1.4.1** (James's ruling), with a `### Fixed` CHANGELOG entry, as its own commit `chore(release): bump version to 1.4.1`. Do not create a tag.
- Widths, exactly: narrow 720 px, wide 1100 px. Study, Settings, `/build` (redirect target) and the 404 page are narrow; Home and Statistics are wide.
- Copy that must not change: the wordmark `Bunshō 文章` (with `lang="ja"` on the Japanese part), the note `Logging out also ends this session on the server.`, the burger `aria-label` `Toggle navigation`, the link names Home, Study, Statistics, Settings.
- Frontend checks, run from `frontend/`: `npx prettier --check .`, `npx eslint .`, `npx tsc -b`, `npx vitest run`, and `npm run build` before the PR. Python: no source change, but `tests/unit/api/test_openapi_snapshot.py` must pass after the version bump.
- TypeScript is strict; no `any`. Lint forbids exporting constants from a component file (`react-refresh/only-export-components`), which is why `pageWidths.ts` is separate.
- Windows quirks: quote the `Bunshō` path; write files with the Write/Edit tools, not shell heredocs; after any Python-driven edit run `npx prettier --write` on the touched files (CRLF); `unset VIRTUAL_ENV` before `uv`.
- Subagents: this project's hook demands `graphify query "<question>"` before reading or grepping source files. Put that instruction in every subagent prompt.
- Do not run a test loop while another agent edits files.

## Review Focus

Failure modes the spec implies that a per-task happy path would miss, most likely first. Each is pinned by a test in the task named in brackets (or, for the two CSS-only ones, by the browser check in Task 4).

1. **The page changes width when its code arrives:** the loading spinner of a lazy page must render inside the same column as the loaded page. [Task 1: `PageWidth.test.tsx` "shows the loading indicator inside the column"]
2. **An error page sticks after navigating away:** the error boundary must reset when the path changes, and a failing page must show inside its column. [Task 1: "shows a page that fails to render inside the column", "leaves the error page behind"]
3. **Near-miss routes get the wrong column:** the old `/build` link (which redirects to Settings) and an unknown address must land in the narrow column, and Home and Statistics in the wide one. [Task 1: `App.test.tsx` `it.each`]
4. **Log out becomes unreachable or loses its description:** Log out lives in a closed menu and a closed drawer, so a test must open each, and the accessible description (the server-session note) must survive; the drawer must be unmounted when closed and close on a link or Escape. [Task 2]
5. **The phone header overflows:** the title must not wrap and the theme toggle must not sit in the phone bar. jsdom cannot see CSS media queries, so the test only pins that the drawer carries the toggle; the fit at 360 px is checked in the browser. [Task 2 for the drawer, Task 4 for the fit]

---

### Task 1: Page widths (layout routes)

**Files:**
- Create: `frontend/src/components/pageWidths.ts`
- Create: `frontend/src/components/PageWidth.tsx`
- Create: `frontend/src/components/PageWidth.test.tsx`
- Modify: `frontend/src/App.tsx` (route tree, one import)
- Modify: `frontend/src/App.test.tsx` (one new `it.each`)
- Modify: `frontend/src/components/AppLayout.tsx` (drop the boundary and suspense it no longer owns)
- Modify: `frontend/src/components/AppLayout.test.tsx` (drop the slow-page test; it moves to `PageWidth.test.tsx`)
- Modify: `frontend/src/features/review/ReviewPage.tsx` (`maw`/`mx` removed)
- Modify: `frontend/src/features/settings/SettingsPage.tsx` (`maw` removed)

**Interfaces:**
- Produces: `PAGE_WIDTHS` (`{ narrow: 720, wide: 1100 }`) and `PageWidthName` (`'narrow' | 'wide'`) from `components/pageWidths.ts`; `PageWidth({ size })` layout-route component from `components/PageWidth.tsx`, which renders `<Container data-width={size}>` around `ErrorBoundary`/`Suspense`/`Outlet`. Task 2 imports `PAGE_WIDTHS`.
- Consumes: existing `ErrorBoundary`, `PageLoader`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/PageWidth.test.tsx`:

```tsx
import { act, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { lazy } from 'react';
import { Link, Route, Routes } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/render';
import { PageWidth } from './PageWidth';
import { PAGE_WIDTHS } from './pageWidths';

let releaseSlowPage: () => void = () => undefined;
const SlowPage = lazy(
  () =>
    new Promise<{ default: () => React.JSX.Element }>((resolve) => {
      releaseSlowPage = () => {
        resolve({ default: () => <p>Slow page loaded</p> });
      };
    }),
);

function Broken(): React.JSX.Element {
  throw new Error('boom');
}

function renderRoutes(initialEntries: string[]) {
  return renderWithProviders(
    <Routes>
      <Route element={<PageWidth size="wide" />}>
        <Route index element={<p>Wide page</p>} />
        <Route path="slow" element={<SlowPage />} />
      </Route>
      <Route element={<PageWidth size="narrow" />}>
        <Route path="narrow" element={<p>Narrow page</p>} />
        <Route path="broken" element={<Broken />} />
      </Route>
    </Routes>,
    { initialEntries },
  );
}

function widthOf(text: string): string | null {
  return screen.getByText(text).closest('[data-width]')?.getAttribute('data-width') ?? null;
}

describe('PageWidth', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('offers a narrow and a wide column, in that order of size', () => {
    expect(PAGE_WIDTHS.narrow).toBe(720);
    expect(PAGE_WIDTHS.wide).toBe(1100);
  });

  it('puts each page in the column its layout route asks for', () => {
    renderRoutes(['/']);
    expect(widthOf('Wide page')).toBe('wide');
  });

  it('centers the column and limits it to its width', () => {
    renderRoutes(['/narrow']);
    const column = screen.getByText('Narrow page').closest<HTMLElement>('[data-width]');
    // 720 px is 45 rem; Mantine wraps it in a scale factor.
    expect(column?.style.getPropertyValue('--container-size')).toContain('45rem');
  });

  it('shows the loading indicator inside the column, then the page', async () => {
    renderRoutes(['/slow']);
    const loader = screen.getByRole('status', { name: 'Loading page' });
    expect(loader.closest('[data-width="wide"]')).not.toBeNull();
    await act(async () => {
      releaseSlowPage();
      await Promise.resolve();
    });
    expect(await screen.findByText('Slow page loaded')).toBeInTheDocument();
    expect(widthOf('Slow page loaded')).toBe('wide');
    expect(screen.queryByRole('status', { name: 'Loading page' })).not.toBeInTheDocument();
  });

  it('shows a page that fails to render inside the column', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    renderRoutes(['/broken']);
    const heading = screen.getByRole('heading', { name: 'Something went wrong' });
    expect(heading.closest('[data-width="narrow"]')).not.toBeNull();
  });
});

describe('PageWidth error reset', () => {
  it('leaves the error page behind when the user navigates away', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    renderWithProviders(
      <>
        <Link to="/ok">Go to ok</Link>
        <Routes>
          <Route element={<PageWidth size="narrow" />}>
            <Route path="bad" element={<Broken />} />
            <Route path="ok" element={<p>Fine page</p>} />
          </Route>
        </Routes>
      </>,
      { initialEntries: ['/bad'] },
    );
    expect(screen.getByRole('heading', { name: 'Something went wrong' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: 'Go to ok' }));
    expect(screen.getByText('Fine page')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Something went wrong' })).not.toBeInTheDocument();
  });
});
```

In `frontend/src/App.test.tsx`, add this test directly above `it('answers an unknown address with a not-found page', ...)`:

```tsx
  it.each([
    ['/', 'Your content', 'wide'],
    ['/stats', 'Statistics', 'wide'],
    ['/review', 'Study', 'narrow'],
    ['/settings', 'Settings', 'narrow'],
    ['/build', 'Build', 'narrow'],
    ['/nothing/here', 'Page not found', 'narrow'],
  ])('puts %s (%s) in a %s column', async (path, heading, width) => {
    rememberLogin();
    goTo(path);
    render(<App />);
    const title = await screen.findByRole('heading', { name: heading });
    expect(title.closest('[data-width]')).toHaveAttribute('data-width', width);
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`): `npx vitest run src/components/PageWidth.test.tsx src/App.test.tsx`
Expected: `PageWidth.test.tsx` FAILS to import `./PageWidth` (module not found); the new `App.test.tsx` cases FAIL (`data-width` attribute missing / `closest` returns null).

- [ ] **Step 3: Create the two source files**

Create `frontend/src/components/pageWidths.ts`:

```ts
/** The two page widths, in px: focused pages are narrow, dashboards are wide. */
export const PAGE_WIDTHS = { narrow: 720, wide: 1100 } as const;

export type PageWidthName = keyof typeof PAGE_WIDTHS;
```

Create `frontend/src/components/PageWidth.tsx`:

```tsx
import { Container } from '@mantine/core';
import { Suspense } from 'react';
import { Outlet, useLocation } from 'react-router';

import { ErrorBoundary } from './ErrorBoundary';
import { PageLoader } from './PageLoader';
import { PAGE_WIDTHS, type PageWidthName } from './pageWidths';

/**
 * A layout route: centers the routed page in a column of one of the two widths. The loading
 * indicator and the error page render inside the column too, so a page does not change width
 * when its code arrives. `AppShell.Main` already provides the side gutters, hence `px={0}`.
 */
export function PageWidth({ size }: { size: PageWidthName }) {
  const { pathname } = useLocation();
  return (
    <Container size={PAGE_WIDTHS[size]} px={0} data-width={size}>
      <ErrorBoundary key={pathname}>
        <Suspense fallback={<PageLoader />}>
          <Outlet />
        </Suspense>
      </ErrorBoundary>
    </Container>
  );
}
```

- [ ] **Step 4: Wire the routes and remove the per-page widths**

In `frontend/src/App.tsx`, add the import after the `AppLayout` import:

```tsx
import { PageWidth } from './components/PageWidth';
```

and replace the six `<Route>` lines inside the `AppLayout` route (from `<Route index element={<HomePage />} />` to `<Route path="*" element={<NotFoundPage />} />`) with:

```tsx
                  <Route element={<PageWidth size="wide" />}>
                    <Route index element={<HomePage />} />
                    <Route path="stats" element={<StatsPage />} />
                  </Route>
                  <Route element={<PageWidth size="narrow" />}>
                    <Route path="review" element={<ReviewPage />} />
                    <Route path="settings" element={<SettingsPage />} />
                    <Route path="build" element={<Navigate to="/settings?tab=system" replace />} />
                    <Route path="*" element={<NotFoundPage />} />
                  </Route>
```

In `frontend/src/features/review/ReviewPage.tsx`, change `<Stack gap="md" maw={720} mx="auto">` to `<Stack gap="md">` (one occurrence, the main return near the end of the component).

In `frontend/src/features/settings/SettingsPage.tsx`, change `<Stack gap="lg" maw={720}>` to `<Stack gap="lg">`.

- [ ] **Step 5: Take the boundary and suspense out of `AppLayout` (the sidebar stays until Task 2)**

In `frontend/src/components/AppLayout.tsx`:

Remove these three import lines:

```tsx
import { Suspense } from 'react';
import { ErrorBoundary } from './ErrorBoundary';
import { PageLoader } from './PageLoader';
```

and replace

```tsx
        <ErrorBoundary key={pathname}>
          <Suspense fallback={<PageLoader />}>
            <Outlet />
          </Suspense>
        </ErrorBoundary>
```

with

```tsx
        <Outlet />
```

(`pathname` is still used by the navigation links.)

In `frontend/src/components/AppLayout.test.tsx` make these five edits, because the slow-page behavior is now tested in `PageWidth.test.tsx`:

1. `import { act, screen } from '@testing-library/react';` becomes `import { screen } from '@testing-library/react';`
2. Delete the line `import { lazy } from 'react';`
3. Delete the `let releaseSlowPage ...` line and the whole `const SlowPage = lazy(...)` block below it (through its closing `);` and the blank line after).
4. Delete the line `            <Route path="slow" element={<SlowPage />} />`.
5. Delete the last test in the file, `it('shows a loading indicator while a page is being fetched, then the page', ...)`, through its closing `});` (keep the final `});` that closes `describe`).

- [ ] **Step 6: Format and run the checks**

Run (from `frontend/`): `npx prettier --write src && npx tsc -b && npx eslint . && npx vitest run`
Expected: no type or lint errors; all tests PASS (the new `PageWidth.test.tsx` cases and the six `App.test.tsx` width cases included).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/pageWidths.ts frontend/src/components/PageWidth.tsx frontend/src/components/PageWidth.test.tsx frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/components/AppLayout.tsx frontend/src/components/AppLayout.test.tsx frontend/src/features/review/ReviewPage.tsx frontend/src/features/settings/SettingsPage.tsx
git commit -m "fix(ui): center every page in a narrow or wide column" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Header navigation

**Files:**
- Create: `frontend/src/components/navigation.ts`
- Create: `frontend/src/components/AccountMenu.tsx`
- Create: `frontend/src/components/NavDrawer.tsx`
- Replace: `frontend/src/components/AppLayout.tsx` (whole file)
- Replace: `frontend/src/components/AppLayout.test.tsx` (whole file)
- Modify: `frontend/src/App.test.tsx` (the log out test)

**Interfaces:**
- Consumes: `PAGE_WIDTHS` from `./pageWidths` (Task 1); `useAuth().logout: () => void`; `ConnectionBadge`, `ColorSchemeToggle` (unchanged).
- Produces: `NAVIGATION`, `isCurrentPage(pathname, to)`, `LOGOUT_NOTE` from `components/navigation.ts`; `AccountMenu()`; `NavDrawer({ opened, onClose })`.

- [ ] **Step 1: Write the failing tests**

Replace the whole of `frontend/src/components/AppLayout.test.tsx` with:

```tsx
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router';
import { describe, expect, it, vi } from 'vitest';

import { AuthContext, type AuthContextValue } from '../auth/authContext';
import { RealtimeContext } from '../realtime/realtimeContext';
import { renderWithProviders } from '../test/render';
import { AppLayout } from './AppLayout';

const NOTE = 'Logging out also ends this session on the server.';

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
            <Route path="settings" element={<p>Settings page</p>} />
          </Route>
        </Routes>
      </RealtimeContext>
    </AuthContext>,
    { initialEntries },
  );
  return logout;
}

/** The page links in the header (the phone drawer is closed and unmounted until the burger opens it). */
function headerLinks() {
  return within(screen.getByRole('navigation', { name: 'Main' }));
}

describe('AppLayout header', () => {
  it('frames the page with the wordmark, the page links and the connection state', () => {
    renderLayout();
    expect(screen.getByRole('heading', { name: /Bunshō/ })).toBeInTheDocument();
    expect(document.querySelector('span[lang="ja"]')).toHaveTextContent('文章');
    expect(headerLinks().getByRole('link', { name: 'Home' })).toHaveAttribute('href', '/');
    expect(headerLinks().getByRole('link', { name: 'Study' })).toHaveAttribute('href', '/review');
    expect(headerLinks().getByRole('link', { name: 'Statistics' })).toHaveAttribute(
      'href',
      '/stats',
    );
    expect(headerLinks().getByRole('link', { name: 'Settings' })).toHaveAttribute(
      'href',
      '/settings',
    );
    expect(screen.queryByRole('link', { name: 'Build content' })).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Live');
    expect(screen.getByText('Home content')).toBeInTheDocument();
  });

  it('marks only the current page as current', () => {
    renderLayout(vi.fn(), ['/settings']);
    expect(headerLinks().getByRole('link', { name: 'Settings' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(headerLinks().getByRole('link', { name: 'Home' })).not.toHaveAttribute('aria-current');
    expect(headerLinks().getByRole('link', { name: 'Study' })).not.toHaveAttribute('aria-current');
  });

  it('navigates between pages and moves the current-page marker', async () => {
    renderLayout();
    await userEvent.click(headerLinks().getByRole('link', { name: 'Settings' }));
    expect(screen.getByText('Settings page')).toBeInTheDocument();
    expect(headerLinks().getByRole('link', { name: 'Settings' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    await userEvent.click(headerLinks().getByRole('link', { name: 'Home' }));
    expect(screen.getByText('Home content')).toBeInTheDocument();
    expect(headerLinks().getByRole('link', { name: 'Home' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('has a theme toggle', () => {
    renderLayout();
    expect(screen.getByRole('radio', { name: 'Dark' })).toBeInTheDocument();
  });
});

describe('Account menu', () => {
  it('keeps Log out out of sight until the menu is opened', () => {
    renderLayout();
    expect(screen.getByRole('button', { name: 'Account' })).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: 'Log out' })).not.toBeInTheDocument();
  });

  it('logs out on request', async () => {
    const logout = renderLayout();
    await userEvent.click(screen.getByRole('button', { name: 'Account' }));
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Log out' }));
    expect(logout).toHaveBeenCalledTimes(1);
  });

  it('says, in visible text, that logging out also ends the session on the server', async () => {
    renderLayout();
    await userEvent.click(screen.getByRole('button', { name: 'Account' }));
    const item = await screen.findByRole('menuitem', { name: 'Log out' });
    const note = screen.getByText(NOTE);
    expect(note).toBeVisible();
    expect(note).toHaveAttribute('id');
    expect(item).toHaveAttribute('aria-describedby', note.id);
    expect(item).toHaveAccessibleDescription(NOTE);
  });
});

describe('Phone navigation drawer', () => {
  it('is closed until the burger is pressed', () => {
    renderLayout();
    const burger = screen.getByRole('button', { name: 'Toggle navigation' });
    expect(burger).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('opens with the pages, Log out and the note, and closes again', async () => {
    const logout = renderLayout();
    const burger = screen.getByRole('button', { name: 'Toggle navigation' });
    await userEvent.click(burger);
    expect(burger).toHaveAttribute('aria-expanded', 'true');
    const drawer = within(await screen.findByRole('dialog', { name: 'Menu' }));
    for (const name of ['Home', 'Study', 'Statistics', 'Settings']) {
      expect(drawer.getByRole('link', { name })).toBeInTheDocument();
    }
    expect(drawer.getByRole('radio', { name: 'Dark' })).toBeInTheDocument();
    const note = drawer.getByText(NOTE);
    expect(note).toBeVisible();
    expect(drawer.getByRole('button', { name: 'Log out' })).toHaveAccessibleDescription(NOTE);
    await userEvent.click(drawer.getByRole('button', { name: 'Log out' }));
    expect(logout).toHaveBeenCalledTimes(1);
  });

  it('closes when a page is chosen', async () => {
    renderLayout();
    await userEvent.click(screen.getByRole('button', { name: 'Toggle navigation' }));
    const drawer = within(await screen.findByRole('dialog', { name: 'Menu' }));
    await userEvent.click(drawer.getByRole('link', { name: 'Settings' }));
    expect(screen.getByText('Settings page')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('closes on Escape', async () => {
    renderLayout();
    await userEvent.click(screen.getByRole('button', { name: 'Toggle navigation' }));
    await screen.findByRole('dialog', { name: 'Menu' });
    await userEvent.keyboard('{Escape}');
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });
});
```

In `frontend/src/App.test.tsx`, in the test `logs out and forgets the remembered login`, replace

```tsx
    await userEvent.click(await screen.findByRole('button', { name: 'Log out' }));
```

with

```tsx
    await userEvent.click(await screen.findByRole('button', { name: 'Account' }));
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Log out' }));
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`): `npx vitest run src/components/AppLayout.test.tsx src/App.test.tsx`
Expected: FAIL. There is no `navigation` landmark named "Main", no "Account" button and no dialog yet.

- [ ] **Step 3: Create the shared navigation module and the two parts**

Create `frontend/src/components/navigation.ts`:

```ts
/** The places in the header (and the phone drawer), in order. */
export const NAVIGATION = [
  { to: '/', label: 'Home' },
  { to: '/review', label: 'Study' },
  { to: '/stats', label: 'Statistics' },
  { to: '/settings', label: 'Settings' },
] as const;

/** The current page is the link whose address is exactly the path (no prefix matching). */
export function isCurrentPage(pathname: string, to: string): boolean {
  return pathname === to;
}

/** The wording beside every Log out control; the accessible description points at it. */
export const LOGOUT_NOTE = 'Logging out also ends this session on the server.';
```

Create `frontend/src/components/AccountMenu.tsx`:

```tsx
import { Button, Menu } from '@mantine/core';
import { useId } from '@mantine/hooks';

import { useAuth } from '../auth/authContext';
import { LOGOUT_NOTE } from './navigation';

/** The header's Account menu (desktop): Log out, with what it does written under it. */
export function AccountMenu() {
  const { logout } = useAuth();
  const noteId = useId();

  return (
    <Menu position="bottom-end" width={260}>
      <Menu.Target>
        <Button variant="subtle" size="xs">
          Account
        </Button>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Item onClick={logout} aria-describedby={noteId}>
          Log out
        </Menu.Item>
        <Menu.Label id={noteId}>{LOGOUT_NOTE}</Menu.Label>
      </Menu.Dropdown>
    </Menu>
  );
}
```

Create `frontend/src/components/NavDrawer.tsx`:

```tsx
import { Button, Divider, Drawer, NavLink, Stack, Text } from '@mantine/core';
import { useId } from '@mantine/hooks';
import { Link, useLocation } from 'react-router';

import { useAuth } from '../auth/authContext';
import { ColorSchemeToggle } from './ColorSchemeToggle';
import { isCurrentPage, LOGOUT_NOTE, NAVIGATION } from './navigation';

interface NavDrawerProps {
  opened: boolean;
  onClose: () => void;
}

/** The navigation on a phone: opened by the header's burger; unmounted while closed. */
export function NavDrawer({ opened, onClose }: NavDrawerProps) {
  const { logout } = useAuth();
  const { pathname } = useLocation();
  const noteId = useId();

  return (
    <Drawer opened={opened} onClose={onClose} title="Menu" size="xs" hiddenFrom="sm">
      <Stack gap="md">
        <nav aria-label="Pages">
          {NAVIGATION.map((item) => (
            <NavLink
              key={item.to}
              component={Link}
              to={item.to}
              label={item.label}
              active={isCurrentPage(pathname, item.to)}
              aria-current={isCurrentPage(pathname, item.to) ? 'page' : undefined}
              onClick={onClose}
            />
          ))}
        </nav>
        <Divider />
        <ColorSchemeToggle />
        <Divider />
        <Stack gap={4}>
          <Button variant="subtle" onClick={logout} aria-describedby={noteId}>
            Log out
          </Button>
          <Text id={noteId} size="xs" c="dimmed">
            {LOGOUT_NOTE}
          </Text>
        </Stack>
      </Stack>
    </Drawer>
  );
}
```

- [ ] **Step 4: Replace `AppLayout.tsx`**

Replace the whole of `frontend/src/components/AppLayout.tsx` with:

```tsx
import { AppShell, Box, Burger, Button, Container, Group, Title } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { Link, Outlet, useLocation } from 'react-router';

import { ConnectionBadge } from '../realtime/ConnectionBadge';
import { AccountMenu } from './AccountMenu';
import { ColorSchemeToggle } from './ColorSchemeToggle';
import { NavDrawer } from './NavDrawer';
import { isCurrentPage, NAVIGATION } from './navigation';
import { PAGE_WIDTHS } from './pageWidths';

/**
 * The frame around every logged-in page: the header (title, page links, connection state, theme,
 * account) and the routed page. The page's own width comes from the `PageWidth` layout route
 * around it.
 */
export function AppLayout() {
  const [drawerOpened, { toggle, close }] = useDisclosure(false);
  const { pathname } = useLocation();

  return (
    <AppShell header={{ height: 56 }} padding="md">
      <AppShell.Header>
        {/* The outer padding + a px={0} container line the header up with the page columns below. */}
        <Box h="100%" px="md">
          <Container size={PAGE_WIDTHS.wide} px={0} h="100%">
            <Group h="100%" justify="space-between" wrap="nowrap">
              <Group gap="lg" wrap="nowrap">
                <Group gap="sm" wrap="nowrap">
                  <Burger
                    opened={drawerOpened}
                    onClick={toggle}
                    hiddenFrom="sm"
                    size="sm"
                    aria-label="Toggle navigation"
                    aria-expanded={drawerOpened}
                  />
                  <Title order={3} style={{ whiteSpace: 'nowrap' }}>
                    Bunshō <span lang="ja">文章</span>
                  </Title>
                </Group>
                <Box component="nav" aria-label="Main" visibleFrom="sm">
                  <Group gap={4} wrap="nowrap">
                    {NAVIGATION.map((item) => {
                      const current = isCurrentPage(pathname, item.to);
                      return (
                        <Button
                          key={item.to}
                          component={Link}
                          to={item.to}
                          variant={current ? 'light' : 'subtle'}
                          color={current ? undefined : 'gray'}
                          aria-current={current ? 'page' : undefined}
                        >
                          {item.label}
                        </Button>
                      );
                    })}
                  </Group>
                </Box>
              </Group>
              <Group gap="xs" wrap="nowrap">
                <ConnectionBadge />
                {/* On a phone the theme toggle lives in the drawer; the bar has no room for it. */}
                <Box visibleFrom="sm">
                  <ColorSchemeToggle />
                </Box>
                <Box visibleFrom="sm">
                  <AccountMenu />
                </Box>
              </Group>
            </Group>
          </Container>
        </Box>
      </AppShell.Header>
      <NavDrawer opened={drawerOpened} onClose={close} />
      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
```

- [ ] **Step 5: Format and run the checks**

Run (from `frontend/`): `npx prettier --write src && npx tsc -b && npx eslint . && npx vitest run`
Expected: no type or lint errors; all tests PASS (47 test files, 498 tests at the time of writing; the count changes only if `main` moved).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/navigation.ts frontend/src/components/AccountMenu.tsx frontend/src/components/NavDrawer.tsx frontend/src/components/AppLayout.tsx frontend/src/components/AppLayout.test.tsx frontend/src/App.test.tsx
git commit -m "fix(ui): move navigation from the sidebar to the header" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Release 1.4.1

**Files:**
- Modify: `CHANGELOG.md`, `pyproject.toml`, `src/bunsho/__init__.py`, `uv.lock`, `frontend/package.json`, `frontend/package-lock.json`, `frontend/openapi.json`, `TODO.md`

**Interfaces:** none.

- [ ] **Step 1: Bump the version strings from 1.4.0 to 1.4.1**

Change exactly these lines (each currently says `1.4.0`; check with `grep -n 1.4.0 <file>` first):

- `pyproject.toml` line 3: `version = "1.4.1"`
- `src/bunsho/__init__.py` line 3: `__version__ = "1.4.1"`
- `uv.lock`: the `version = "1.4.0"` line directly under `name = "bunsho"` (about line 200) becomes `version = "1.4.1"`. Change only that one; other packages' versions stay.
- `frontend/package.json` line 4: `"version": "1.4.1",`
- `frontend/package-lock.json`: only lines 3 and 9 (the project's own two entries at the top); the many other `1.4.0` lines belong to dependencies and stay.
- `frontend/openapi.json` line 1738: `"version": "1.4.1"`

- [ ] **Step 2: Add the changelog entry**

In `CHANGELOG.md`, between `## [Unreleased]` and `## [1.4.0] - 2026-09-25`, insert (use today's date from `date +%F`):

```markdown
## [1.4.1] - <today's date>

### Fixed

- Every page now sits centered in a width-limited column. Home and Statistics were stretched across
  the whole window on a wide monitor and Settings hugged the left edge; Study and Settings now share
  a 720 px column, and Home and Statistics an 1100 px one.
- Navigation moved from the sidebar to the header (Home, Study, Statistics, Settings), with Log out
  in an Account menu. On a phone the header has a menu button that opens a drawer with the pages,
  the theme switch and Log out.

```

- [ ] **Step 3: Update the mobile shell item in `TODO.md`**

Replace

```
- [ ] Mobile shell: Burger aria-expanded/aria-controls, hide the collapsed drawer from keyboard users,
      verify header fit at 360 px; an `ErrorBoundary` now wraps the routed page content (`AppLayout.tsx`),
      but not the header/nav/Burger around it — consider one further out if those can throw
```

with

```
- [ ] Mobile shell: the Burger has `aria-expanded` but no `aria-controls`; an `ErrorBoundary` wraps the
      routed page content (`PageWidth.tsx`) but not the header, Account menu or drawer — consider one
      further out if those can throw
```

- [ ] **Step 4: Verify the version consistency**

Run: `unset VIRTUAL_ENV; uv run pytest tests/unit/api/test_openapi_snapshot.py tests/unit/api/test_openapi.py -q`
Expected: PASS (the snapshot test compares `frontend/openapi.json` with the app's schema, version included).

Run (from `frontend/`): `npm run build`
Expected: `tsc -b` and `vite build` succeed. The preview files, if present, are not part of the build.

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md pyproject.toml src/bunsho/__init__.py uv.lock frontend/package.json frontend/package-lock.json frontend/openapi.json TODO.md
git commit -m "chore(release): bump version to 1.4.1" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Browser check and pull request (controller)

**Files:**
- Create, untracked and deleted afterwards: `frontend/preview.html`, `frontend/src/preview.tsx`

This task is done by the controller (not a subagent): it needs a browser, and the authenticated screens need James.

- [ ] **Step 1: Create the throwaway preview page**

`frontend/preview.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Bunshō layout preview</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/preview.tsx"></script>
  </body>
</html>
```

`frontend/src/preview.tsx`:

```tsx
/* eslint-disable react-refresh/only-export-components */
// THROWAWAY: a login-free preview of the app shell with stand-in pages. Never commit this file.
import '@mantine/core/styles.css';

import { MantineProvider, Paper, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes } from 'react-router';

import { AuthContext, type AuthContextValue } from './auth/authContext';
import { AppLayout } from './components/AppLayout';
import { PageWidth } from './components/PageWidth';
import { RealtimeContext } from './realtime/realtimeContext';
import { theme } from './theme';

const auth: AuthContextValue = {
  status: 'authenticated',
  sessionExpired: false,
  login: () => Promise.resolve(),
  logout: () => {},
  retry: () => {},
};

function Filler({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <Stack gap="md">
      <Title order={2}>{title}</Title>
      {children}
    </Stack>
  );
}

function Cards({ n }: { n: number }) {
  return (
    <SimpleGrid cols={{ base: 1, sm: n }}>
      {Array.from({ length: n }, (_, i) => (
        <Paper key={i} withBorder p="md">
          <Text size="sm" c="dimmed">
            Card {i + 1}
          </Text>
          <Text fz={28} fw={600}>
            {(i + 1) * 1234}
          </Text>
        </Paper>
      ))}
    </SimpleGrid>
  );
}

const start = new URLSearchParams(window.location.search).get('path') ?? '/';

const container = document.getElementById('root');
if (container === null) throw new Error('no #root');
createRoot(container).render(
  <StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="auto">
      <AuthContext value={auth}>
        <RealtimeContext value={{ kind: 'connected' }}>
          <MemoryRouter initialEntries={[start]}>
            <Routes>
              <Route element={<AppLayout />}>
                <Route element={<PageWidth size="wide" />}>
                  <Route
                    index
                    element={
                      <Filler title="Your content">
                        <Cards n={3} />
                      </Filler>
                    }
                  />
                  <Route
                    path="stats"
                    element={
                      <Filler title="Statistics">
                        <Cards n={4} />
                        <Paper withBorder p="md" h={260}>
                          <Text c="dimmed">chart</Text>
                        </Paper>
                      </Filler>
                    }
                  />
                </Route>
                <Route element={<PageWidth size="narrow" />}>
                  <Route
                    path="review"
                    element={
                      <Filler title="Study">
                        <Paper withBorder p="xl" ta="center">
                          <Text fz={72} lang="ja">
                            あ
                          </Text>
                        </Paper>
                      </Filler>
                    }
                  />
                  <Route
                    path="settings"
                    element={
                      <Filler title="Settings">
                        <Paper withBorder p="md" h={320}>
                          <Text c="dimmed">settings form</Text>
                        </Paper>
                      </Filler>
                    }
                  />
                </Route>
              </Route>
            </Routes>
          </MemoryRouter>
        </RealtimeContext>
      </AuthContext>
    </MantineProvider>
  </StrictMode>,
);
```

- [ ] **Step 2: Serve it and inspect it**

Run (from `frontend/`): `npx vite --port 5273 --strictPort` (5173 is James's other project). Open `http://localhost:5273/preview.html?path=/stats`, `?path=/review`, `?path=/settings` and `?path=/`.

Check with the Chrome tools (skill `claude-in-chrome`; the preview needs no login):

1. Wide pages (`/`, `/stats`): the page column and the header container are both 1100 px and share the same left and right edges (compare `getBoundingClientRect()` of `header .mantine-Container-root` and `[data-width]`).
2. Narrow pages (`/review`, `/settings`): the column is 720 px and exactly centered (`left + right == innerWidth`).
3. Phone width: the browser window cannot be made narrower than the display, so load the page in a same-origin `<iframe>` of width 360 and 390 (build the iframes with `javascript_tool`) and confirm the title is on one line, the badge reads "Live" in full, nothing scrolls sideways (`scrollWidth <= innerWidth`), and the burger opens a drawer with four links (current one highlighted), the theme toggle, Log out and the note.
4. Desktop Account menu: after clicking Account, the dropdown is 260 px wide, right-aligned to the header edge, with "Log out" and the note.

If a screenshot call times out after clicking, stop retrying it and rely on the `javascript_tool` measurements.

- [ ] **Step 3: Delete the preview and stop the server**

Stop Vite, then delete `frontend/preview.html` and `frontend/src/preview.tsx`. Run `git status` and confirm neither is listed.

- [ ] **Step 4: Full checks, push, open the PR**

Run (from `frontend/`): `npx prettier --check . && npx eslint . && npx tsc -b && npx vitest run && npm run build`.

Push `fix/app-shell-header-layout` and open the PR (title `fix(ui): consistent page widths and header navigation`). The body must contain: a summary; the two widths; "no routing/auth/backend change"; the release note (1.4.1, bug fix, no tag); a Manual check list for James (needs a login): Home, Statistics, Study, Settings (four tabs) at about 1920, 1280 and 390 px; the Study card and multiple-choice buttons at 720 px; the sticky Settings Save bar aligned to the column; Account menu and drawer open, Escape and focus; no CSP violations in the console when opening the menu and drawer on the real (nonce) server; a slow first load of Stats shows the spinner inside the column; `.env.example` untracked and not part of the PR. End with the `🤖 Generated with [Claude Code](https://claude.com/claude-code)` line.

- [ ] **Step 5: Final review**

Dispatch one whole-branch review on **Sonnet** (`model: sonnet`; James's standing rule, cost), one fix wave, then report.
