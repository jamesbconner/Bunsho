# Bunshō: Content-Security-Policy and Security Headers — Design

Status: design approved in conversation 2026-09-26 (brainstorming); this document awaits review.
Next: implementation plan.
Parent designs: `2026-09-19-bunsho-foundation-and-review-engine-design.md` (the service and its
delivery, built by plan 1C) and `2026-09-20-bunsho-2b1-frontend-skeleton-design.md` (the Mantine
app shell).

This is sub-project B of the security items in `TODO.md` ("Security & Auth"). Its third part, the
JSON 500 outside CORS, shipped in 1.4.0 (PR #32); the WebSocket cap (PR #31), session revocation
(PR #30) and the login form work (PR #32) are done. This spec covers the last two open items:
the Content-Security-Policy header, and security headers on every response.

## Scope

Today `SPAStaticFiles` (`api/static.py`) sets `X-Content-Type-Options: nosniff`,
`Referrer-Policy: no-referrer` and `X-Frame-Options: DENY` on the responses it serves and nothing
else does: API responses, `/openapi.json`, `/docs` and `/redoc` carry no security headers, and no
response carries a Content-Security-Policy.

Covers: one middleware that puts the baseline headers on every HTTP response; a
Content-Security-Policy chosen per response class (the app shell, everything else, and the docs
pages); a per-request nonce for the shell so Mantine's runtime `<style>` elements are allowed
without `'unsafe-inline'`; the frontend reading that nonce; a `server.csp_report_only` setting;
tests; documentation; the changelog entry in the 1.4.0 section (1.4.0 is still untagged).

Out of scope: HSTS (see Decisions); `Permissions-Policy` and the `Cross-Origin-*-Policy` headers;
a CSP violation report endpoint (`report-uri` / `report-to`; the report-only switch is for
diagnosing in the browser console); Subresource Integrity; self-hosting the Swagger UI and Redoc
assets; changing CORS.

## Decisions (locked in brainstorming)

- **Style nonce, not `'unsafe-inline'` and not hashes.** Mantine's `MantineProvider` writes
  `<style data-mantine-styles>` elements at runtime (theme variables, responsive props). A CSP
  treats those as inline styles. The shell is served with a fresh nonce per request and the
  provider puts it on its `<style>` tags. Hashes were rejected: the content changes with any
  theme or Mantine change, and a stale hash silently breaks styling.
- **The docs pages get their own looser policy.** `/docs`, `/redoc` and `/docs/oauth2-redirect`
  load Swagger UI / Redoc from `cdn.jsdelivr.net` and run an inline bootstrap script, so they
  cannot work under the shell policy. They get a dedicated, tested policy that allows exactly
  that; the UI and API stay strict. Turning the docs off or leaving them without a CSP were
  rejected.
- **Enforced by default, with a switch.** `server.csp_report_only` (default `false`) sends the
  same policy as `Content-Security-Policy-Report-Only`, so a breakage can be diagnosed from the
  env file without rebuilding. Shipping report-only first and enforcing later was rejected: no
  report endpoint, so no feedback, and the protection would wait a release.
- **`connect-src 'self'`** covers the API and the same-origin WebSocket. Browsers older than
  Safari 15.4 do not treat `wss:` as same-origin; they are not supported.
- **No HSTS from the app.** It only applies over TLS, the README already puts TLS on the reverse
  proxy, and the app cannot reliably tell whether it is behind TLS. The README recommends that the
  proxy sets it.

## Backend

### Policies (`api/csp.py`)

A pure module: no I/O, no framework imports. The policy strings live here so they are read and
tested in one place.

```
SHELL   default-src 'none'; script-src 'self'; style-src 'self' 'nonce-<N>';
        img-src 'self'; font-src 'self'; connect-src 'self';
        base-uri 'none'; form-action 'self'; frame-ancestors 'none'
DEFAULT default-src 'none'; frame-ancestors 'none'
DOCS    default-src 'none'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net;
        style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net;
        img-src 'self' data: https://fastapi.tiangolo.com; connect-src 'self';
        frame-ancestors 'none'
```

- `shell_policy(nonce: str) -> str`, plus the `DEFAULT_POLICY` and `DOCS_POLICY` constants and
  `header_name(report_only: bool) -> str` (`Content-Security-Policy` or
  `Content-Security-Policy-Report-Only`).
- `img-src` has no `data:` for the shell: the built CSS contains no `url(...)` at all. If the
  manual browser check finds a `data:` image, it is added there, not by loosening anything else.
- The DOCS list is the starting point. Redoc may also need its font origin and `blob:` workers;
  the exact list is settled against the real pages during implementation and this section is
  updated to match. Swagger UI is the page the README points people to, so it is the acceptance
  test.
- `DEFAULT` is what every non-shell, non-docs response gets: JSON and hashed assets have no
  active content, and this also stops a file such as an SVG from running script if it is opened as
  a page.
- `generate_nonce() -> str` returns `base64.b64encode(secrets.token_bytes(16)).decode()`. Base64
  (not `token_urlsafe`) is what the CSP `nonce-source` grammar requires: `-` and `_` are not valid.

### Middleware (`api/security_headers.py`)

`SecurityHeadersMiddleware` is pure ASGI and the **outermost** user middleware (added last in
`create_app`), so it covers static files, API responses, `/docs`, CORS preflights and the JSON 500
from `UnhandledErrorMiddleware`.

- On `http.response.start` it adds `X-Content-Type-Options: nosniff`, `Referrer-Policy:
  no-referrer` and `X-Frame-Options: DENY`, and the CSP header. A header the inner app already set
  is left alone; the middleware only fills gaps.
- **Which CSP:** if the request scope carries a nonce (set by the static layer, below), the shell
  policy with that nonce; else if the path is one of the docs paths, `DOCS_POLICY`; else
  `DEFAULT_POLICY`. The docs paths are the FastAPI defaults (`/docs`, `/redoc`,
  `/docs/oauth2-redirect`); they are constants next to the policy, with a test that fails if the
  app's actual docs URLs differ.
- The header name comes from `header_name(config.server.csp_report_only)`. Exactly one CSP header
  is ever sent.
- Only `http` scopes are touched; `websocket` and `lifespan` pass through. A WebSocket handshake
  response is not a document and gets no CSP.
- `static.py` loses `_SECURITY_HEADERS` and keeps only its cache-control logic.

### Rendering the shell (`api/static.py`)

- `frontend/index.html` gains `<meta name="csp-nonce" content="__CSP_NONCE__" />` in `<head>`;
  Vite copies it into the build unchanged.
- `SPAStaticFiles` reads `index.html` once at construction and keeps the text. For each shell
  response (the root, `/index.html`, and any client route that falls back to it) it replaces the
  placeholder with a fresh nonce, returns an `HTMLResponse`, and records the nonce on the request
  scope under a private key for the middleware to read.
- `Cache-Control: no-cache` stays on the shell; hashed `assets/` keep `immutable` and are still
  served as files, with no nonce.
- **Fail fast, in config validation.** `validate_config` already checks `[paths] frontend_dir`
  and reports every problem together with an actionable message. It gains one more: if the folder
  has an `index.html` that does not contain the placeholder (an older build, or a hand-copied
  folder) it reports "the UI build is out of date: run `npm run build` in `frontend/`". A shell
  without a nonce would make the policy block every style, and a blank page is a worse failure
  than a startup message. The placeholder constant and the check live in a small neutral module
  (`bunsho/frontend_shell.py`) that both the config validation and `SPAStaticFiles` import, so
  the config layer does not import from the API layer. `SPAStaticFiles` also raises `ValueError`
  in its constructor as a backstop for direct use (tests, other callers). With `frontend_dir`
  unset nothing changes.

### Setting

`ServerSettings.csp_report_only: bool = False`, read from `[server] csp_report_only` /
`BUNSHO_SERVER__CSP_REPORT_ONLY` with the existing `ConfigNormalizer` boolean accessor, alongside
`cors_origins` and `trusted_proxies`, and validated like them. Documented in the README settings
section and in `.env.example`.

## Frontend

- `readCspNonce(): string | undefined` (`src/csp.ts`) reads the `content` of
  `<meta name="csp-nonce">`. It returns `undefined` when the tag is missing, empty, or still holds
  the literal `__CSP_NONCE__` (what `npm run dev` under Vite sees), so development needs no CSP
  and keeps working.
- `App.tsx` passes it: `<MantineProvider getStyleNonce={readCspNonce} …>`. That one change puts the
  nonce on the provider's style tags, including ones added later by responsive props.
- `src/main.tsx` and everything else are unchanged; no inline script is added anywhere.

## Testing

Backend (`pytest`, existing fixtures and `TestClient`):

- `csp.py`: the exact shell, default and docs policy strings; the nonce appears verbatim; the
  header name for both values of the switch; `generate_nonce` returns valid base64, differs per
  call and has 16 bytes of entropy.
- `SecurityHeadersMiddleware` at the ASGI level: baseline headers on 200, 404, 500 and a CORS
  preflight; an existing header value is not overwritten; the right CSP per class (shell with
  nonce, API, asset, each docs path); report-only uses the `-Report-Only` name and never both;
  websocket and lifespan scopes pass through untouched.
- Static and shell: the nonce is fresh on every request; the same value is in the header and in
  the `<meta>`; the placeholder never reaches the client; a deep link gets the shell with a nonce;
  assets and other files get no nonce and the default policy; a build without the placeholder
  raises `ValueError`, and `validate_config` reports the "rebuild the UI" message alongside other
  config errors; `frontend_dir` unset is unchanged. The existing header
  assertions in `tests/unit/api/test_static.py` move to the middleware tests or are updated.
- App-level: `/api/v1/health`, `/openapi.json` and a 401 carry the baseline headers and the default
  policy; `/docs`, `/redoc` carry the docs policy; the docs URLs match the constants.
- Config: `csp_report_only` parses `true`/`false` from the env and file, defaults to `false`, and
  rejects a non-boolean value with an actionable message.

Frontend (Vitest): `readCspNonce` with the tag present, missing, empty and holding the
placeholder; `App` renders with the nonce reaching `MantineProvider` (a `<style
data-mantine-styles>` element in the document carries the nonce attribute).

Manual, by James (the plan hands this over in the PR body): build the UI and run the service with
it, then load the app in a real browser with the console open. Log in and visit home, review,
stats and settings (and open the dark scheme, resize below the mobile breakpoint, trigger a
notification and look at the stats charts), and confirm **no CSP violations** are reported. Open
`/docs` and `/redoc` and confirm they render and "Try it out" works. Then set
`BUNSHO_SERVER__CSP_REPORT_ONLY=true`, reload, and confirm the header name changes and nothing is
blocked. Any violation found is added to the policy here, with the reason.

## Housekeeping

- `TODO.md`: move the CSP and security-headers items to done under a "CSP and security headers
  (1.4.0)" heading.
- `CHANGELOG.md`: entries in the existing `[1.4.0]` section (untagged), under `### Security`
  (the CSP and headers) and `### Added` (the setting).
- README: the new setting; the docs-page exception in one sentence; a line recommending that the
  TLS reverse proxy also sets HSTS.
- No version bump (it stays 1.4.0). No tag or release is created; that is James's step.

## Risks and notes

- **A policy mistake breaks the UI in a real browser, which tests cannot fully see.** Mitigations:
  the report-only switch, the fail-fast shell check, and the manual browser check above. The
  controller never types the password, so the authenticated screens cannot be exercised by it and
  are checked by James.
- **Library styles injected some other way.** `@mantine/charts` (Recharts) and
  `@mantine/notifications` are the likely candidates. React's `style` props go through the
  browser's style API, which CSP allows; only `<style>` elements and `style` attribute strings are
  blocked. The manual check covers both.
- **Swagger/Redoc versions move with FastAPI.** The DOCS policy is written against the versions
  FastAPI ships today; a FastAPI upgrade may need it revisited. A test over the rendered docs HTML
  pins the origins it references so a change is noticed.
- **The nonce is per request, but the shell is small and in memory,** so rendering costs a string
  replace and one `secrets.token_bytes` call.
- **The middleware is outermost, so a failure inside it is not caught by the JSON 500 layer.** It
  only reads the scope and appends headers, and it is covered by tests on every response class.
