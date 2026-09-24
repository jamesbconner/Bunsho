# Bunshō: Settings Page Tabs and a System Tab — Design

Status: design approved in conversation 2026-09-23 (brainstorming); this document awaits review.
Next: implementation plan.
Parent designs: `2026-09-21-bunsho-2b3-stats-settings-design.md` (the Settings page) and
`2026-09-20-bunsho-2b1-frontend-skeleton-design.md` (routing and the Build page).

## Scope

The Settings page is one long form: six headed sections and 16 controls. "New cards" mixes *what* to
introduce (type switches) with *how much* (daily limits), and the ordering rules (kana gate, levels,
mastery) sit in separate sections below it. Separately, "Build content" is its own top-level page
although it is a system operation, not a study action.

Covers: splitting the form across three Mantine tabs (Learning path, Pace, Reviewing); a fourth System
tab that takes over the Build page and adds server and content status; a deep-linkable tab selection;
error surfacing for fields on a hidden tab; the `/build` redirect and the links to it; tests; and the
1.2.0 release bump.

Out of scope: per-tab saving (one form, one Save); study-path presets (`TODO.md`); any backend change
(the two status blocks read endpoints that exist); changing what any setting means or how it is
validated; the review, stats and home pages beyond the three `/build` links.

## Decisions (locked in brainstorming)

| Topic | Decision |
|---|---|
| Grouping | Three form tabs by the question each answers, plus System (see the table below). |
| Component | Mantine `Tabs`, controlled, with `Tabs.List`, `Tabs.Tab`, `Tabs.Panel`. No hand-rolled tab strip. |
| Tab state | The `?tab=` search parameter, not local state and not nested routes. |
| One form | A single `useForm`, one Save. All three form panels stay mounted, so edits survive tab switches. |
| Build page | Moves into System. The nav item is removed and `/build` redirects to `/settings?tab=system`. |
| System contents | Server (version and component health), Content status, Environment checks, Build. |
| Hidden-tab errors | A tab whose fields have errors is marked; a failed Save jumps to the first such tab. |
| Release | 1.2.0 (a user-visible reorganisation with a changed URL, not a fix). |

## Tab contents

| Tab (`value`) | Question it answers | Controls |
|---|---|---|
| Learning path (`learning`) | What do I learn, and in what order? | New-card policy; levels to study and the mastery threshold (both belong beside the policy that enables them); introduce kana / kanji / vocabulary; the Kana first gate and its threshold. |
| Pace (`pace`) | How much, and how often? | Kana / kanji / vocabulary per day; a new study day starts at; target retention. |
| Reviewing (`reviewing`) | How do I answer? | Kana / kanji / vocabulary review mode. |
| System (`system`) | Is the service ready, and is content built? | Not settings: server status, content status, environment checks, build. |

Two couplings cross tabs and are handled explicitly. The per-day limits on Pace are disabled when the
matching type is switched off on Learning path, so a disabled limit says "Switched off in Learning
path" in its description instead of just greying out. The Kana first gate is disabled while new kana
are off; that pair stays together on Learning path, so its existing "Turn on new kana above" text
remains true.

## Component structure

`SettingsPage.tsx` (445 lines today) becomes a shell; each tab is its own file so each is small enough
to hold in mind and test on its own.

```
features/settings/
  SettingsPage.tsx        loads settings; renders SettingsTabs once data is present
  SettingsTabs.tsx        <Tabs>, the tab list, the single useForm, the Save bar, tab-error logic
  LearningPathTab.tsx     panel body, takes the form
  PaceTab.tsx             panel body, takes the form
  ReviewingTab.tsx        panel body, takes the form
  SystemTab.tsx           panel body: ServerStatus, ContentStatus, EnvironmentChecks, BuildPanel
  ServerStatus.tsx        version and per-component health
  ContentStatus.tsx       built or not, kana / kanji / vocab counts
  useSettingsTab.ts       the ?tab= <-> Tabs value binding
  settingsForm.ts         gains TAB_OF_FIELD and tabsWithErrors (pure)
features/build/
  BuildPanel.tsx          BuildPage minus its page title; EnvironmentChecks moves out to SystemTab
```

The form tab components receive `form: UseFormReturnType<SettingsFormValues>` and read what they need
from it; none of them owns state. `PolicyField`, `placeServerErrors`, `validateSettings` and the rest of
`settingsForm.ts` are unchanged apart from the two additions.

## Using Mantine Tabs

```tsx
<Tabs value={tab} onChange={setTab} keepMounted={false}>  {/* controlled from ?tab= */}
  <Tabs.List aria-label="Settings sections">     {/* announced on first focus */}
    <Tabs.Tab value="learning" color={errors.learning ? 'red' : undefined}
              rightSection={errors.learning ? <ErrorDot /> : null}>Learning path</Tabs.Tab>
    ...                                          {/* pace, reviewing the same way; system has no dot */}
    <Tabs.Tab value="system">System</Tabs.Tab>
  </Tabs.List>

  <form onSubmit={...} noValidate>               {/* only the three settings panels */}
    <Tabs.Panel value="learning" pt="md" keepMounted><LearningPathTab form={form} /></Tabs.Panel>
    <Tabs.Panel value="pace" pt="md" keepMounted><PaceTab form={form} /></Tabs.Panel>
    <Tabs.Panel value="reviewing" pt="md" keepMounted><ReviewingTab form={form} /></Tabs.Panel>
    {tab !== 'system' && <SaveBar ... />}
  </form>

  <Tabs.Panel value="system" pt="md"><SystemTab /></Tabs.Panel>
</Tabs>
```

Constructs used and why (Mantine 9):

- **Controlled `value` / `onChange`.** The selection is owned by the URL; this is the pattern Mantine
  documents for react-router. `onChange` passes `string | null`; `useSettingsTab` narrows it to a known
  tab and ignores anything else.
- **Root `keepMounted={false}`, and `keepMounted` on the three settings panels.** The settings panels
  stay mounted (Mantine's default `activity` mode hides them and pauses their effects), so field
  state, error placement and the `aria-describedby` wiring of the group controls do not depend on
  which tab is showing. The System panel inherits the root value and unmounts when hidden, so its
  health, content-summary, config-check and build-status queries run only while System is open.
- **`Tabs.Tab` `color` and `rightSection`** carry the error mark: a red tab plus a small dot, with
  visually hidden text ("has errors") because colour alone must not carry meaning. The mark is not an
  ARIA state; `aria-invalid` is not valid on the `tab` role.
- **`Tabs.List` `aria-label`** names the group for screen readers; each `Tabs.Tab` is labelled by its
  text, so no per-tab `aria-label`.
- **Built-in keyboard support, unchanged defaults:** arrow keys move and activate (`activateTabWithKeyboard`)
  and focus wraps (`loop`). `role="tablist"`, `role="tab"`, `role="tabpanel"`, and the
  `aria-controls` / `aria-labelledby` links are generated by Mantine; the code adds none of them.
- **`Tabs.List` wraps** (it is `flex-wrap: wrap`), so four tabs at phone width need no overflow handling.
  The default variant is kept so the page matches the rest of the app.
- **`allowTabDeactivation` stays off**, so `onChange` never yields `null` in practice.

## Routing

- **Tab in the URL.** `useSettingsTab` reads `?tab=` with `useSearchParams`, returns one of
  `learning | pace | reviewing | system`, and falls back to `learning` for a missing or unknown value.
  Changing tab calls `setSearchParams({ tab }, { replace: true })`, so Back leaves Settings instead of
  stepping through tabs.
- **`/build` redirect.** `App.tsx` replaces the `build` route with `<Navigate to="/settings?tab=system"
  replace />`. Bookmarks and any external link keep working.
- **Links.** The three first-run buttons (`HomePage.tsx`, `ReviewFinished.tsx`, `StatsPage.tsx`) point
  at `/settings?tab=system`. The "Build content" entry is removed from the nav list in `AppLayout.tsx`.
- **Lazy loading.** `BuildPage` is lazy-loaded today. `BuildPanel` becomes part of `SystemTab`, which is
  lazy-loaded from `SettingsTabs` so that the build UI (the modal, the progress card, the report table)
  does not enlarge the initial Settings chunk.

## Errors on a hidden tab

The form's errors are keyed by field path (`new_limits.kana`, `kana_gate.threshold_percent`, and the
group key `kana_gate`), from both client validation and `placeServerErrors` (422). The risk is Save
appearing to do nothing because the bad field is on another tab.

- `settingsForm.ts` exports `TAB_OF_FIELD`, mapping the first path segment to a tab:
  `new_card_policy`, `active_levels`, `mastery_threshold_percent`, `type_enabled`, `kana_gate` →
  `learning`; `new_limits`, `rollover_hour`, `target_retention_percent` → `pace`; `kana_mode`,
  `kanji_mode`, `vocab_mode` → `reviewing`. An unmapped path is treated as `learning`, and a test
  asserts that every key of `SettingsFormValues` is mapped, so a new field cannot be forgotten.
- `tabsWithErrors(errors)` returns the set of tabs that have at least one error, in tab order.
- `SettingsTabs` marks those tabs (above). When a submit fails validation, or a 422 response has
  placed errors, it moves to the first tab in the set, then focuses that tab's first invalid field via
  the form's own `onSubmit` invalid-handler. A general (non-field) error stays in the Save bar, visible
  on all three settings tabs.
- Errors clear the way they do now (per field on edit, the `kana_gate` group message when a switch
  changes); the marks follow because they are derived from the same error state.

"Reset to recommended values" refills all three tabs, so its label becomes "Reset all tabs to
recommended values". "Unsaved changes" stays in the Save bar. The Save bar is not rendered on System,
which has no form state.

## The System tab

Four blocks, top to bottom, each its own component:

1. **Server** (`ServerStatus`). The app version and the per-component status from `GET /health`. The
   frontend has no `/health` client today, so this adds `endpoints.health()` and a `useHealth` query.
   `GET /health` answers 503 with the full body when a dependency is in error, so `endpoints.health()`
   returns the parsed `HealthResponse` for both 200 and 503 and throws for anything else; a 503 is data
   to show, not a failure to hide behind a generic error.
2. **Content** (`ContentStatus`). Built or not, and the kana, kanji and vocabulary counts, from the
   existing `useContentSummary`. `formatCount` from `features/build/format.ts` is reused.
3. **Environment checks.** `EnvironmentChecks`, unchanged, moved up from the Build page.
4. **Build.** `BuildPanel`: the existing start, rebuild-confirm, dry-run, progress and report behaviour
   (`useMutation` for `startBuild`, `useLatestBuild`, `BuildProgressCard`, the confirm `Modal`, the
   live-region announcement) moved as is. Its `<Title order={2}>Content</Title>` goes; System supplies
   `h3` block headings under the page's `h2`. The first-run `Alert` stays at the top of the tab.

The "Build content" button is `type="button"` and sits outside the `<form>`, so it can never submit
settings.

## Error handling

- `useSettingsTab` never throws: an unknown `?tab=` value is the default tab.
- A failing health, summary or config-check request shows an inline `Alert` in its own block with a
  retry; one failing block does not blank the others.
- Settings load and save errors behave exactly as today (load failure alert with retry; 422 placed by
  field; other save errors in the Save bar with "Try again").

## Testing

Existing behaviour tests are kept; what changes is that they first open the tab that holds the control
they use (a small `openTab(name)` helper using `getByRole('tab', { name })`). New coverage:

- **Tabs and URL.** Renders four tabs with the default selected; `?tab=pace` selects Pace; an unknown
  value selects Learning path; clicking a tab updates `?tab=` without adding history; arrow keys move
  between tabs (Mantine behaviour, asserted once as an integration check).
- **One form.** Edit on Learning path, switch to Pace and back, edit is intact; Save sends every tab's
  values in one request; Save is absent on System.
- **Hidden-tab errors.** An invalid value on Pace, while on Learning path, marks the Pace tab and, on
  Save, moves to it. A 422 for a Reviewing field does the same. Fixing the field removes the mark.
- **Pure helpers.** `TAB_OF_FIELD` covers every key of `SettingsFormValues`; `tabsWithErrors` for
  nested paths, the `kana_gate` group key and an empty error set.
- **Cross-tab hint.** A limit whose type is off shows "Switched off in Learning path".
- **System tab.** The health block for 200 and for a 503 body with a component in error; the content
  block built and not built; per-block failure with retry; the existing build tests moved to
  `BuildPanel` unchanged in substance; the queries do not run until System is opened
  (`keepMounted={false}`).
- **Routing.** `/build` lands on `/settings?tab=system`; the three first-run buttons link there; the
  nav has no "Build content" entry. `App.test.tsx`, which asserts `/build` today, is updated.

Coverage stays at or above the current level for `features/settings` and `features/build`.

## Release and docs

Version 1.1.2 → 1.2.0 in `pyproject.toml`, `src/bunsho/__init__.py`, `uv.lock`, `frontend/package.json`,
`frontend/package-lock.json` (two places) and `frontend/openapi.json`. `CHANGELOG.md` gets a `[1.2.0]`
section: **Changed** (Settings is now four tabs; Build content moved into Settings > System; `/build`
redirects there) and **Added** (server and content status on the System tab). The README paragraph that
describes the Settings page is updated to match. No backend or API change, so no migration and nothing
to do on upgrade.

## Risks

- **Hidden-tab errors** are the main one; the mark, the jump and the every-field-is-mapped test exist
  for that reason.
- **First-run discoverability.** The build action is one level deeper. Mitigated by the three
  first-run buttons, which stay and now open the System tab directly.
- **Test churn.** `SettingsPage.test.tsx` (658 lines) and `BuildPage.test.tsx` (274 lines) move or gain
  an `openTab` step. The `activity` keep-mounted mode hides inactive panels; the plan must confirm, on the first
  migrated test, how hidden panels appear to Testing Library (role queries are expected to skip them)
  before the rest are converted.
- **`/health` 503.** Treating a 503 as data is deliberate, but it is the one place the frontend reads
  an error status as success; it is limited to `endpoints.health()` and covered by a test.
