# Bunshō: Session Revocation and Logout Hardening — Design

Status: design approved in conversation 2026-09-25 (brainstorming); this document awaits review.
Next: implementation plan.
Parent designs: `2026-09-19-bunsho-foundation-and-review-engine-design.md` (JWT auth, WebSocket
stream) and `2026-09-20-bunsho-2b1-frontend-skeleton-design.md` (the browser session).

This is sub-project A of the security items in `TODO.md` ("Security & Auth"). Sub-projects B
(response hardening: CSP, security headers, 500 outside CORS), C (unauthenticated WebSocket cap)
and D (login form and `returnPath`) follow as separate specs, plans and PRs.

## Scope

Today the tokens are stateless JWTs. Each carries a `jti`, but nothing stores or checks it.
`POST /auth/refresh` returns a new pair without invalidating the old refresh token, and the UI's
Log out only clears the browser's local session. Consequences:

- A copied refresh token keeps working until it expires (`refresh_ttl_days`).
- After logout, an access token that was already issued stays valid for its remaining minutes.
- An open WebSocket keeps streaming after logout until it drops.
- A refresh request in flight when the user logs out can write a fresh token pair back into the
  cleared session (`session.setTokens` after `session.clear()`), undoing the logout.

Covers: a server-side, session-wide revocation store; `POST /auth/logout`; closing the revoked
session's open sockets; the frontend logout call; a session epoch that makes late refresh results
harmless; tests for the logout -> login stream lifecycle and StrictMode; the 1.4.0 release bump.

Out of scope: refresh-token rotation or reuse detection (two tabs refreshing at once would log the
user out, and a single-user local app does not justify it); a retry queue for a logout request that
never reached the server; "log out everywhere" or a session list; changing token lifetimes; the
other Security & Auth items (B, C, D).

## Decisions (locked in brainstorming)

| Topic | Decision |
|---|---|
| Revocation unit | The **session**: every token pair from one login shares a `sid` claim; revoking the sid revokes the refresh token and every access token of that login. |
| Rotation | None. `refresh` keeps the sid, so concurrent tabs cannot invalidate each other. |
| Store | `revoked_session` table in `progress.db` (Alembic migration 0002) plus a write-through in-memory set loaded at startup. |
| Old tokens | Tokens without a `sid` are rejected. The user logs in once after upgrading; a 401 on refresh already means "signed out" in the UI. |
| Logout endpoint | `POST /auth/logout` with `{refresh_token}`, no bearer required, always 204. |
| Open sockets | Closed with 1008 when their session is revoked. |
| Logout failure | Best effort. If the request cannot reach the server the local logout still happens; the token then lives until it expires, as today. |
| Release | 1.4.0 (a new endpoint and a behaviour change, not only a fix). |

## Backend

### Token identity

`AuthService.issue_tokens(username, sid=None)` puts a `sid` claim (a `uuid4().hex`) in both tokens.
`login` lets it default (a new sid); `refresh` passes the sid of the token it decoded, so the new
pair belongs to the same session. `_decode` adds `sid` to the required claims.

`_decode` returns a small frozen dataclass `SessionClaims(username, sid)`. The public surface:

- `authenticate(access_token) -> str` is unchanged (username), so REST dependencies do not change.
- `authenticate_session(access_token) -> SessionClaims` returns username and sid; the WebSocket
  handler uses it.
- `async revoke(refresh_token) -> str` (async because the store writes to SQLite) decodes the
  token, revokes its sid until **now plus the refresh TTL** (the latest any token of that session can
  expire; using the presented token's own `exp` would let a newer refresh token from another tab
  come back to life once the row was pruned), and returns the sid. It raises `AuthError` for a
  token that does not verify, is expired, or belongs to an already-revoked session (the endpoint
  answers 204 for all of these; an already-revoked session's sockets were closed by the first
  logout).

`_decode` raises `AuthError("session revoked")` when the sid is in the revocation set. The message
never reaches a client: routers already answer with a fixed generic 401.

### Revocation store

A port in `services/protocols.py`:

```python
class SessionRevocations(Protocol):
    def is_revoked(self, sid: str) -> bool: ...      # sync, in-memory
    async def revoke(self, sid: str, expires_at: datetime) -> None: ...
```

Implementation `RevokedSessionStore` next to `ProgressRepository` (in `db/`):

- `revoked_session(sid TEXT PRIMARY KEY, expires_at)` (singular, like `card_state` and
  `app_setting`); timestamps stored the way the other `progress.db` tables store them
  (`db/timestamps.py`).
- `RevokedSessionStore.load()` runs in `build_services` (already async, inside the lifespan): it
  deletes rows whose `expires_at` has passed and loads the remaining sids into a set.
- `is_revoked` reads only the set, because `authenticate` runs on every request and WebSocket
  connect in async handlers and must not block the event loop on SQLite. Safe because the app is
  single-process (the instance lock in `db/instance_lock.py` guarantees it).
- `revoke` inserts the row first and adds to the set second (a failed insert leaves the set
  unchanged and raises), and prunes expired rows in the same transaction.

Migration 0002 creates the table; its `downgrade()` drops it. A test covers the round trip
(`tests/unit/db/test_migrate.py` already exercises migrations).

### Logout endpoint

`POST /auth/logout`, `operation_id="logout"`, body `LogoutRequest{refresh_token}`, response 204
with no body, tag `auth`.

- Needs no bearer, so it works after the access token expired.
- A token that is invalid, expired or already revoked still returns 204: the endpoint must not
  tell a caller whether a token was valid.
- Logs `logout sid=<sid> client=<host>` at info when it revoked something and
  `logout_ignored client=<host>` at debug otherwise. Never the token, never exception text.
- Not throttled and never touches the login throttle: a token that verifies costs one signature
  check and one insert, and a flood of bad logout calls must not be able to block
  `POST /auth/login`. A test asserts that.

The router stays thin. The logout workflow lives in `orchestration/session_logout.py`, which
coordinates `AuthService` and `SessionSockets` (below), per the project's orchestration rule.

### Closing open sockets

`SessionSockets` (module `orchestration/session_sockets.py`): a registry `sid -> set[WebSocket]`.

- `register(sid, websocket)` / `unregister(sid, websocket)`.
- `async close_session(sid)` closes every registered socket for that sid with code 1008 and
  suppresses `RuntimeError`/`WebSocketDisconnect` (the socket may already be gone).

`task_stream` calls `authenticate_session`, registers the socket after a successful auth, and
unregisters in its existing `finally`. Unauthenticated sockets are never registered.

`session_logout.logout(refresh_token)`:

1. `sid = auth.revoke(refresh_token)` (raises `AuthError` for an unverifiable token: the caller
   returns 204 without closing anything);
2. `await sockets.close_session(sid)`.

Order matters: revoke first, close second, so a reconnecting client cannot authenticate in between.
Closing the socket ends `_drain`, and `_stream` unwinds through its normal path (subscription
removed last, as the module comments require).

Both `RevokedSessionStore` and `SessionSockets` are wired in `build_services` and reachable through
`Services`. `ServiceOverrides` keeps working for tests.

## Frontend

### Logout call

`AuthProvider.logout()`:

1. Read the refresh token (`session.getRefreshToken()`).
2. `session.clear()`, `queryClient.clear()`, `setStatus('anonymous')` exactly as today (the UI
   responds immediately).
3. If a token was read, `void` a `rawRequest('/auth/logout', {method: 'POST', body: {refresh_token}})`;
   any error is swallowed (no token, no error text logged). A small `logoutRequest` helper in
   `api/client.ts` keeps the call out of the provider.

Other tabs already follow through the `storage` event and only clear locally; only the tab that
clicked Log out calls the server.

The note beside the Log out button in `AppLayout` ("Logging out only affects this browser: the
server cannot end sessions yet.") becomes false and is replaced by "Logging out also ends this
session on the server." Its visible-text and `aria-describedby` test is updated to match.

### Session epoch

`session.ts` gets a module-level counter `epoch`:

- `clear()` and `expire()` increment it; `session.getEpoch()` exposes it.
- `session.setTokens(pair, {epoch})`: when `epoch` is given and differs from the current one, the
  pair is discarded and the call returns `false`. Login calls `setTokens` without an epoch (a
  login is always current).
- `expire(epoch)`: an `expire` carrying a stale epoch is a no-op.

`refreshOnce` in `api/client.ts`:

- captures `session.getEpoch()` together with the refresh token, before the request;
- on success calls `setTokens(pair, {epoch})`; when the pair is discarded it throws
  `ApiError(401, 'Session changed')` without calling `expire` (the session was already ended or
  replaced, and its listeners were told then);
- on a 401 calls `expire(epoch)`, so a stale 401 cannot end a newer session (the second bug in the
  same window: log out, log in, then the old token's 401 arrives).

`clear()` also resets `refreshInFlight` (exposed through a small `resetRefresh()` in `client.ts` or
by moving the in-flight promise into `session.ts`; the plan picks whichever keeps the import graph
acyclic), so a new session never joins a refresh started under the old one.

## Testing

Backend (`tests/unit/...`, pytest, following `tests/base.py`):

- `AuthService`: tokens carry a `sid`; `refresh` keeps it; a revoked sid is rejected for access and
  refresh tokens; a token without `sid` is rejected; `revoke` of a garbage/expired token raises
  `AuthError`.
- `RevokedSessionStore`: revoke persists across a new instance (`load()`); expired rows pruned at
  load and on revoke; a failed insert leaves the set unchanged.
- Migration 0002 upgrade and downgrade round trip.
- `POST /auth/logout`: 204 for a valid, an invalid, an expired and an already-revoked token; after
  logout `POST /auth/refresh` and a protected route both 401; a second session (other sid) is
  unaffected; bad logout calls do not block login.
- WebSocket: an authenticated socket is closed with 1008 by logout and the stream unwinds (the
  existing "wait for unsubscribe" pattern); a socket of another sid stays open; a token revoked
  before connect is refused at auth; the registry is empty afterwards.
- OpenAPI snapshot regenerated; `schema.ts` regenerated.
- Flaky check per `working-agreements`: the socket tests touch threads and TestClient teardown, so
  loop them 40-60 runs before calling them stable.

Frontend (Vitest):

- `session.ts`: `setTokens` with a stale epoch is discarded; `expire` with a stale epoch does
  nothing; `clear` bumps the epoch.
- `client.ts`: a refresh that resolves after `session.clear()` leaves the session cleared; a stale
  401 after logout -> login does not expire the new session; a new session does not join an old
  in-flight refresh.
- `AuthProvider`: logout sends `POST /auth/logout` with the captured token and still clears locally
  when the request fails; other tabs (storage event) do not call the server.
- Stream lifecycle (`RealtimeProvider` + `AuthProvider` with the existing fake socket): logout
  closes the stream; a new stream opens after login; under `StrictMode`'s double mount exactly one
  socket is live at the end.

## Housekeeping

- Version 1.4.0 in the files a release bump touches (`pyproject.toml`, `src/bunsho/__init__.py`,
  `uv.lock`, `frontend/package.json`, `frontend/package-lock.json`, `frontend/openapi.json`) and a
  CHANGELOG entry (Added: `POST /auth/logout`, session revocation; Changed:
  tokens issued before the upgrade are rejected, so log in once; Fixed: a refresh in flight can no
  longer undo a logout).
- README: a short paragraph on logout semantics (server-side revocation, open streams closed,
  best-effort when the server is unreachable).
- `TODO.md`: move the three items (revocation, session epoch, stream lifecycle tests) to the
  completed section under this change.
- Branch `feat/session-revocation`; conventional commits with the Co-Authored-By paragraph; the PR
  is opened for James, who reviews and merges.

## Risks and notes

- **Upgrade logs the user out once.** Intended (sid-less tokens are rejected). The CHANGELOG says
  so.
- **In-memory set and multi-process.** Correct only while the app is single-process, which the
  instance lock enforces. A future multi-worker deployment must swap the set for a shared store;
  the `SessionRevocations` port is the seam.
- **Unreachable server at logout** leaves the token valid until it expires. Accepted and
  documented; no retry queue.
- **Access tokens are also checked**, so the revocation set is consulted on every authenticated
  request: it is a set lookup, not I/O.
