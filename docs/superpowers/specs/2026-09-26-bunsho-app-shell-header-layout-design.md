# Bunshō: Header Navigation and Consistent Page Widths — Design

Status: design approved in conversation 2026-09-26 (brainstorming); this document awaits review.
Next: implementation plan.
Parent designs: `2026-09-20-bunsho-2b1-frontend-skeleton-design.md` (the app shell and routing).

## Scope

The logged-in pages do not share a layout. Only Study is centered and width-limited
(`ReviewPage.tsx`: `maw={720} mx="auto"`). Settings has `maw={720}` but no `mx="auto"`, so it hugs the
left edge. Home and Statistics have no limit and fill the space beside the sidebar, which looks
stretched on a widescreen monitor. Navigation is a 220 px sidebar holding four links plus Log out.

Covers: two named page widths applied by the layout rather than by each page; centering for every
logged-in page; moving navigation from the sidebar into the header; an Account menu for Log out; a
burger and drawer for phones; tests; a throwaway preview page for review; and a release note.

Out of scope: the login page (it is outside `AppLayout` and stays a centered card); any change to
routes, `?tab=`, the `/build` redirect or auth; page content and inner layout (Home's three-card grid,
the Stats charts and tables, the Study card and its buttons); a data router migration; fixing the
existing shell items in `TODO.md` (exact-path active state, toast placement); a wider redesign of the
header (breadcrumbs, per-page titles, a user name).

## Decisions (locked in brainstorming)

| Topic | Decision |
|---|---|
| Widths | Two named widths, both centered: **narrow** 720 px, **wide** 1100 px. |
| Assignment | Study and Settings and the 404 page are narrow; Home and Statistics are wide. |
| Mechanism | Pathless layout routes in `App.tsx`, each wrapping its pages in one `PageWidth` layout component. Pages no longer set their own width. |
| Navigation | The sidebar is removed. Header links (Home, Study, Statistics, Settings) inline on desktop; no dropdown menus for them. |
| Account | One Account menu on the right of the header holds Log out and its "ends this session on the server" note. |
| Connection badge | Stays in the header at every width. |
| Theme toggle | In the header from `md` up; inside the phone drawer below `md` (see "Amended after the preview"). |
| Phones (below `md`) | Inline links, the theme toggle and the Account menu are hidden; a Burger opens a `Drawer` with the four links, the theme toggle, Log out and the note. The header bar keeps the burger, the title on one line and the badge. |
| Header width | The header's inner content uses the wide width, so it lines up with the dashboard pages. |

### Why layout routes, not route `handle`

The first idea was for each route to declare `handle: { width }` and for `AppLayout` to read it with
`useMatches`. That hook exists only in a data router (`createBrowserRouter`); the app uses
`<BrowserRouter>` + `<Routes>`. Changing router type would be a much larger change than this task.
Pathless layout routes give the same result with the router we have, and the width is still declared
in one place, `App.tsx`, next to the routes.

### Why the loading and error states move

Today `AppLayout` renders `ErrorBoundary` and `Suspense` around the `Outlet`. If they stayed there,
the loading spinner and a failed-page message would render outside the centered column, and the page
would jump to its width when the lazy chunk arrives. They move into `PageWidth`, inside the
`Container`, so every state of a page (loading, error, loaded) has the same width. The
`key={pathname}` on `ErrorBoundary` moves with it so an error clears when the user navigates.

## Design

### Widths in one place

`pageWidths.ts` exports `PAGE_WIDTHS = { narrow: 720, wide: 1100 } as const` and the `PageWidthName`
type. It is its own file because the project's lint rule (`react-refresh/only-export-components`)
forbids a component file from exporting constants. `PageWidth.tsx` and the header both import it, so
the numbers exist nowhere else. `PageWidth` passes the number to `Container` (Mantine has no
theme key for custom container names: an unknown `size="narrow"` would resolve to an undefined CSS
variable, checked in `@mantine/core` 9.6.1 source). It also sets `data-width="narrow" | "wide"` on
the container, which is what tests assert. The 720 px value is Study's current width, so Study's card
does not change size.

### Component structure

```
components/
  AppLayout.tsx     AppShell (header only) + header content; renders <Outlet /> in AppShell.Main
  pageWidths.ts     new. PAGE_WIDTHS and the PageWidthName type (constants, no components)
  PageWidth.tsx     new. props: size 'narrow' | 'wide'. <Container size=…> wrapping
                    <ErrorBoundary key={pathname}><Suspense><Outlet/></Suspense></ErrorBoundary>
  AccountMenu.tsx   new. Mantine Menu: target button, Log out item, the note. Desktop only.
  NavDrawer.tsx     new. Mantine Drawer: four links, Log out, the note. Below `md` only.
                    (Extracted so AppLayout stays a short composition of its parts.)
  navigation.ts     new. the NAVIGATION list, shared by the header links and the drawer
```

`App.tsx` route tree:

```
<Route element={<RealtimeProvider><AppLayout/></RealtimeProvider>}>
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
</Route>
```

`ReviewPage` drops `maw={720} mx="auto"`; `SettingsPage` drops `maw={720}`.

### Header

`AppShell` keeps `header={{ height: 56 }}` and loses `navbar`. Inside the header, one wide `Container`
(with horizontal padding) holds a single `Group` with `justify="space-between"`:

- Left: the Burger (`hiddenFrom="md"`), the `Bunshō 文章` title (same markup, so `lang="ja"` stays),
  then the four links in a `Group` with `visibleFrom="md"`. Each link is a router `Link`;
  the current page gets `aria-current="page"` and a visible active style. The active test stays
  `pathname === to`, exactly as today.
- Right: `ConnectionBadge`, then `ColorSchemeToggle` and `AccountMenu`, both `visibleFrom="md"`.
- The title does not wrap (`white-space: nowrap`).

`AppShell` `padding="md"` still gives the main area its gutters, so `PageWidth`'s `Container` uses
`px={0}` to avoid doubling them. The header lines up with the columns the same way: an outer box with
`px="md"` around a `px={0}` wide container, so the header's content edges and the page column's edges
are the same at every viewport width (measured in the preview: both 730 to 1830 px at 2560 px wide).

### Amended after the preview

Built as a throwaway preview page, the first header design kept the theme toggle in the phone header
bar. At 390 px the title wrapped mid-word and the badge truncated to "Li…"; at 360 px the toggle was
clipped to "Aut". So below `md` the toggle moves into the drawer, and the title gets `nowrap`. With
that the bar shows the burger, the full title and the full "Live" badge at 360 px.

### Amended after the final review: the switch is at `md`, not `sm`

Measured in a browser with exact-width frames: from `sm` (768 px) the links, theme toggle and Account
menu together are wider than the header. At 768 px the Account button overflowed the container by
25 px and the page by 9 px, and up to about 840 px the connection badge was squeezed to 34 to 40 px
(natural 57 px). From 850 px everything fit. So every switch between the phone layout (burger and
drawer) and the desktop layout (links, theme toggle, Account menu) is at `md` (62em, 992 px), and the
viewport query that closes the drawer uses the same breakpoint.

### Account menu

A Mantine `Menu` whose target is a button named "Account". Its dropdown holds a `Log out` menu item
and, beneath it, the text "Logging out also ends this session on the server." The item has
`aria-describedby` pointing at that text, as the sidebar button does today, so the accessible
description does not regress. The dropdown is only mounted while open, which is fine because the note
matters at the moment of the decision. A menu with one action is thin, but it is the natural home for
a later "Signed in as…" line, and a bare button would lose the note on touch devices.

### Phone drawer

The Burger toggles a `Drawer` (`hiddenFrom="md"`) with the four links, the theme toggle, a Log out
button and the note (same `aria-describedby` wiring). Choosing a link closes it. The burger keeps its
`aria-label="Toggle navigation"` and gains `aria-expanded`. The drawer is unmounted when closed, so it
is not a keyboard tab stop while hidden (an item in `TODO.md` under the mobile shell).

## Behavior that must not change

Routes and their URLs, `/build` redirect, the `?tab=` parameter, auth and the RequireAuth return
path, the realtime badge, the theme toggle, the sticky Settings Save bar (`position: sticky` in the
window, so it stays at the bottom of the narrow column), the Study shortcuts and answer modes.

## Testing

- `AppLayout.test.tsx` is rewritten for the header: wordmark, four links with their hrefs, the badge,
  the theme toggle; navigating between pages; active link marked with `aria-current`.
- Account menu: opening it shows the item and the note visible; the item's accessible description is
  the note; choosing it calls `logout` once.
- Drawer: the burger opens it; it holds the four links, Log out and the note; choosing a link closes
  it. (jsdom ignores media queries, so the desktop-only and phone-only parts both render; tests query
  within the menu or drawer rather than by global role.)
- `PageWidth.test.tsx`: the container has the requested `data-width`; the loading indicator and a
  thrown page error both render inside the container; the error clears on navigation. The existing
  slow-page and error-boundary tests move here from `AppLayout.test.tsx`.
- A route-table test in `App.test.tsx`: Home and Stats render in a `data-width="wide"` container,
  Study, Settings, the `/build` redirect target and the 404 page in a `data-width="narrow"` one.
- Existing page tests must keep passing untouched, apart from removing any assertion on the deleted
  `maw`.

Frontend checks (`vitest`, `tsc`, `eslint`, `prettier`) run as for any UI change; no backend change.

## Manual browser check (needs a logged-in session)

I cannot type the password, so the authenticated screens are for James to eyeball. Checklist for the
PR: Home, Statistics, Study, Settings (all four tabs) at 1920 px, 1280 px and 390 px; header links
aligned with the page edges on the wide pages; the Study card and multiple-choice buttons at 720 px;
the Settings Save bar aligned to the column; the Account menu and the drawer open, focus and Escape;
no CSP violations opening the menu and drawer (Mantine portals and inline styles use the style nonce);
a slow first load of a lazy page shows the spinner inside the column, not full width.

A throwaway preview page (untracked `frontend/preview.html` + `src/preview.tsx`, Vite on port 5273,
deleted afterwards) shows the header and both widths before the real implementation, as with the
Settings redesign.

## Release

James's ruling (2026-09-26): this is a bug fix, not a feature. The pages are inconsistently laid out,
and nothing about content or capability changes. So it is a patch release, **1.4.1**, with a
`### Fixed` entry in `CHANGELOG.md` (for example "Every page is now centered in a width-limited
column, and navigation moved from the sidebar to the header"). The version bump in `pyproject.toml`
and `frontend/package.json` and the changelog entry are applied with the implementation, not with
this spec. No tag is created (that step is James's).

## Risks and open points

- Mantine `Menu` and `Drawer` render in portals with inline positioning styles; the CSP work already
  covers Mantine's nonce path, but the browser check above must confirm it for these two components.
- Header fit at 360 px is an existing `TODO.md` item; the phone bar must keep the burger, the title
  and the badge on one line at that width (checked in the preview page after the amendment above).
- The 1100 px wide width is a judgement about the Home grid and the Stats chart; if either looks
  cramped or too loose in the preview page, the number changes in `PAGE_WIDTHS` only.
