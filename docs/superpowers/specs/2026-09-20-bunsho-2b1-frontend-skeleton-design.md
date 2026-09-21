# Bunshō Plan 2B-1: Frontend Skeleton and Delivery — Design

Status: design approved 2026-09-20 (brainstorming). Next: implementation plan.
Parent design: `2026-09-19-bunsho-foundation-and-review-engine-design.md` (its "Frontend" section);
backend it builds on: `2026-09-20-bunsho-2a-review-engine-design.md` (merged in PR #9).

## Scope and slicing

Plan 2B is split, as Plan 2 was:

- **2B-1 (this spec): skeleton and delivery.** Vite + React + TypeScript app, generated API types,
  an authentication-aware API client, the login screen, the app shell, a Home screen, the content
  Build screen with live WebSocket progress, and the whole delivery pipeline (static serving by the
  backend, Docker Node stage, frontend CI job, Dependabot `npm`, smoke-test checks). It ends with a
  deployed, working UI you can log into and use to build content.
- **2B-2 (later, own spec): the study screens.** Dashboard, flip-and-grade review with keyboard
  shortcuts and furigana, statistics, settings screen.

Out of scope for 2B-1: any review, statistics or settings UI; typed-answer and multiple-choice
modes; refresh-token revocation (server side); a full Content-Security-Policy; browser end-to-end
tests.

## Decisions (locked in brainstorming)

| Topic | Decision |
|---|---|
| Versions | **Latest stable release of every library and tool** (React, Vite, TypeScript, Mantine, TanStack Query, React Router, ofetch, openapi-typescript, ESLint, Prettier, Vitest, MSW, Node in the Docker stage and CI). Verified with current docs / the npm registry at the task that introduces each one. An older major is allowed only when the newest cannot work with something else in the stack, and the reason is recorded in the PR. Dependabot keeps them current afterwards. |
| Styling | **Mantine** for the chrome (AppShell, forms, modals, notifications, progress, dark mode) plus hand-written **CSS modules** for the study surface (2B-2). Japanese typography: a Japanese-aware Mantine theme font stack (system fonts Hiragino Sans / Yu Gothic / Noto Sans JP; self-hosting via `@fontsource/noto-sans-jp` is optional), `lang="ja"` on the root and on every Japanese text run, and a custom `<Furigana>` component (native `<ruby>`) in 2B-2. |
| Login storage | Refresh token in `localStorage`, access token in memory only. |
| Serving | FastAPI serves the built assets (same origin, no CORS in production). |
| Type pipeline | A committed OpenAPI snapshot plus drift checks; no hand-written API types. |
| Routing / data | React Router (library mode), TanStack Query for server state, one small auth context. |
| Dev workflow | Vite dev server proxies `/api` (including WebSocket) to the backend; no CORS needed. |
| Tests | Vitest + React Testing Library + MSW at the network layer. |

## Layout and tooling

```
frontend/
  package.json, package-lock.json, vite.config.ts, tsconfig*.json,
  eslint.config.js, .prettierrc, index.html, .gitignore   (node_modules, dist, coverage)
  openapi.json                 committed snapshot of the API schema
  src/
    main.tsx, App.tsx          providers + router
    theme.ts                   Mantine theme, Japanese font stack
    api/        schema.d.ts (generated, committed), client.ts, endpoints.ts, errors.ts
    auth/       AuthProvider, tokenStore, RequireAuth
    realtime/   RealtimeProvider, useBuildStream
    features/   login/, home/, build/
    components/ AppShell parts, ErrorBoundary, ConnectionBadge
    test/       MSW handlers, render helper, setup
```

Strict TypeScript. ESLint (flat config, React and TypeScript plugins) and Prettier. `package-lock.json`
is committed and installs use `npm ci`. Scripts: `dev`, `build` (`tsc -b && vite build`), `lint`,
`format:check`, `test`, `gen:api`. The root `.gitignore` is not touched (the frontend has its own);
`.gitattributes` forces LF for `frontend/`.

### API type pipeline (two drift checks)

1. `scripts/export_openapi.py` builds the app with dummy configuration (the lifespan does not run)
   and writes `frontend/openapi.json` with sorted keys.
2. A pytest test regenerates the document and fails if the committed file differs, so a backend
   change cannot ship without refreshing the snapshot. It runs in the existing Python CI.
3. `npm run gen:api` (`openapi-typescript`) turns the snapshot into `src/api/schema.d.ts`. The
   frontend CI job runs it and fails if the committed file differs.

`api/endpoints.ts` is the only place mapping routes to typed functions; its types come from the
generated schema.

## Authentication and the API client

- **Tokens.** The refresh token lives in `localStorage` (`bunsho.refresh_token`), the access token and
  its expiry in memory. Every storage access is wrapped in try/catch (blocked storage means "not
  remembered"). Tokens never appear in URLs, logs or the query cache.
- **Bootstrap.** With a stored refresh token the app shows a loading state and calls
  `/auth/refresh`. A 401 clears the token and shows the login screen; a network error or 5xx shows
  a "cannot reach the server" retry screen and keeps the token (a server restart never logs you out).
- **`request()` wrapper** around `ofetch`: attaches the bearer token; on a 401 from a non-auth route
  runs a **single-flight refresh** (concurrent 401s share one promise) and retries the call once; if
  refresh fails with 401 it clears the tokens, marks the session expired, and the router sends the
  user to `/login` with a toast.
- **Errors** are normalized to `ApiError(status, detail, retryAfter)`; the UI shows messages, never
  raw status codes or stacks: login 401 "Invalid username or password"; login 429 a countdown from
  `Retry-After`; build 409 "A build is already running"; 503 "Content isn't built yet"; 422 field
  messages; network failure "Can't reach the server".
- **Logout** clears storage and the query cache; a `storage` listener logs out other tabs. The UI says
  it logs out this browser only, because the server cannot revoke tokens yet.
- **Query defaults:** retry only on network errors and 5xx (never 4xx), modest stale time.
- The WebSocket authenticates with a fresh access token (refreshing first when near expiry).

## Screens

- **`/login`:** Mantine form with validation and autofocus; returns to the intended page.
- **`/` Home:** reads `GET /content/summary`. Not built: first-run banner linking to `/build`. Built:
  counts for kana, kanji (leveled and unleveled) and vocabulary and a per-level table from the typed
  `*_by_level` fields.
- **`/build`:** environment checks from `GET /admin/config-check` (deck present, checksum, data folder
  writable, dictionary available); a Build button and a "Dry run" switch; a confirmation modal before
  rebuilding built content; live status (Mantine progress bar with friendly stage labels, a state
  badge, the report on success with counts by level and duration); a readable message on failure;
  409 shown as "already running".
- **Not Found** page and a route-level error boundary with a friendly fallback.
- **Shell:** header with the Bunshō 文章 wordmark, navigation (Home, Build content), a connection
  badge, a light / dark / system theme toggle and Log out; collapses to a burger on narrow screens.
  There are no placeholder routes for 2B-2 screens.
- English-only UI; accessible labels, focus handling and `aria-live` for progress and state.

## Real-time build progress

One `RealtimeProvider` inside the authenticated area keeps the connection badge and the query cache
live on every page.

- **Protocol** (the server's, unchanged): send `{type:"auth", token}`; receive `ready`, then a
  `snapshot` of the latest build, then `event` messages. Messages are checked with small type guards on
  top of the generated types.
- **Reconnect:** exponential backoff with full jitter, 1 s up to a 30 s cap, reset on `ready`. Close
  code 1008 means auth failed: refresh the token and reconnect once, log out if refresh fails.
- **Cache:** snapshots and events write into the TanStack Query cache for the latest build; a finished
  build invalidates the content summary and the environment checks.
- **Polling fallback:** while a build is running and the socket is down, poll
  `GET /admin/content/build/{id}` every 2 s.
- **Badge states:** connected, connecting, retrying in N s, disconnected.

## Delivery

**Serving the UI (backend).** A new optional setting `paths.frontend_dir`
(`BUNSHO_PATHS__FRONTEND_DIR`), unset by default: the app then serves the API only and logs one info
line. A value that is not a directory joins the existing list of configuration errors.
`api/static.py` adds `SPAStaticFiles` (a `StaticFiles` subclass) that falls back to `index.html` for
unknown non-API paths so deep links survive a reload; an unknown `/api/...` path keeps its JSON 404.
It is mounted last at `/`, so `/api/v1/...`, `/docs` and `/openapi.json` always win. `assets/*` get
`Cache-Control: public, max-age=31536000, immutable`, `index.html` gets `no-cache`; both get
`X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` and `X-Frame-Options: DENY`.

**Docker.** A new first stage `FROM node:<latest LTS>-slim AS frontend`: `npm ci` (cache mount,
dependencies before sources), then `npm run build`; it needs no Python (the committed schema types
are the input). The runtime image gets an explicit `COPY --from=frontend /frontend/dist /app/frontend`
and `BUNSHO_PATHS__FRONTEND_DIR=/app/frontend`. The read-only root filesystem is unaffected.

**CI.** A new `frontend` job (setup-node pinned by SHA): `npm ci`, lint, `format:check`, `gen:api`
plus a diff check on the generated file, `tsc -b`, `vitest` with coverage, `vite build`. The `smoke`
job builds the real image (now with the UI) and checks: `GET /` returns the HTML shell, a deep link
returns `index.html`, a hashed asset carries the immutable header, `GET /api/v1/nope` is a JSON 404.
Dependabot gains an `npm` entry for `/frontend` (minor and patch grouped).

**Dev workflow.** `npm run dev` proxies `/api` (WebSocket included) to `127.0.0.1:8192` (override with
`VITE_API_TARGET`), so development needs no CORS. The README's frontend paragraph is rewritten around
this; the CORS setting stays documented as optional.

**Packaging.** Wheel and sdist stay API-only (the sdist already uses an explicit include list); Docker
is the deployment path. The README explains how to point a pip install at a built `dist`.

## Testing

- **Frontend (Vitest, React Testing Library, MSW at the network layer):** the token store (including
  blocked storage); the `request()` wrapper (bearer attached, parallel 401s share one refresh, a
  single retry, session expiry); the login form (invalid credentials, the 429 countdown); the
  bootstrap states (checking, anonymous, authenticated, server unreachable keeps the token); Home in
  its not-built and built states; the Build screen (start, dry run, 409, live progress, failure);
  `useBuildStream` against a fake WebSocket (auth message first, `ready`/`snapshot`/events, backoff
  timing with fake timers and seeded jitter, the 1008 refresh-and-reconnect path, the polling
  fallback); the theme toggle; the error boundary. Coverage reported with an 80% gate.
- **Backend (pytest):** static serving (SPA fallback, JSON 404 under `/api`, cache and security
  headers, no mount when unset), `frontend_dir` validation, the OpenAPI snapshot drift test.
- **Container smoke test:** the extra checks above, against the real image.

## Order of work

One branch (`feat/plan-2b1-frontend-skeleton`), draft PR opened early, no stacked PRs. Delivery comes
before the screens so deployment risk is found early.

1. `scripts/export_openapi.py`, the committed snapshot and the drift test.
2. Backend static serving: config field, `SPAStaticFiles`, tests.
3. Frontend scaffold: tooling, theme, `gen:api`, a hello page that passes lint, test and build.
4. Delivery: Docker Node stage, CI `frontend` job, Dependabot `npm`, smoke-test checks (the hello page
   is deployed and verified in the real image).
5. API layer, auth provider and the login screen.
6. App shell, routing, Home and the error boundary.
7. Real-time provider and the Build screen.
8. Docs, whole-branch verification (local npm gate plus the Docker smoke test) and the final review.

## Risks

- Library majors are new (Mantine, React, openapi-typescript): verify each with current docs at the
  task that uses it, and record any exception to the latest-version rule.
- jsdom polyfills for Mantine in tests.
- WebSocket and fake-timer test flakiness: a fake socket class and deterministic jitter.
- Windows line endings on generated files: `.gitattributes` for `frontend/`, LF forced.
- A slower CI and image build from the Node stage: cache mounts and layered `npm ci`.
- Unhandled backend errors return their JSON 500 from outside CORS middleware (a known follow-up from
  2A); irrelevant for the same-origin deployment used here, relevant only for a cross-origin dev setup.

## Implementation notes

Decisions taken while building, where they differ from or refine the text above.

- The HTML root is `lang="en"` (the UI text is English); every Japanese text run carries `lang="ja"`.
- TypeScript is pinned to 6.0.3, not 7.0.2: `typescript-eslint` 8.70 supports only `typescript <6.1.0`, and
  `openapi-typescript` 7.13 needs the JavaScript compiler API and declares `^5.x` as its peer range. An
  `overrides` entry in `package.json` lets npm accept that peer range (verified to run on 6.0.3). Move to
  TypeScript 7 when both tools support it. Dependabot's `ignore` rule (major versions of `typescript` and
  `@types/node`) stops it proposing TypeScript 7; adopt it by hand, removing the rule and the pin together.
- React Router is used in declarative mode (`BrowserRouter`, `Routes`, `Route`, `Navigate`, `Outlet`); TanStack
  Query owns data fetching. The UI's first-class routes are `/`, `/build` and `/login`.
- Task order differs from "Order of work": the real-time provider and the Build screen came before the shell,
  Home page and routing, so each screen was tested on its own before it was wired.
- `SPAStaticFiles` answers 405 for non-GET methods on unknown non-API paths (Starlette's `StaticFiles` allows only
  GET and HEAD); unknown `GET /api/...` paths keep their JSON 404.
- The Log out control sits at the bottom of the navbar (and the mobile drawer) with visible text that it only
  clears this browser; the server does not revoke refresh tokens yet.
