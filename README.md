# Bunshō (文章)

A Japanese language learning tool: hiragana, katakana, JLPT N5-N1 kanji and vocabulary, and
spaced-repetition flashcards. Runs as a containerized FastAPI + React web app on a home server.

Status: early development. See `docs/superpowers/specs/` for the design.

## Running the service

Bunshō serves an authenticated REST + WebSocket API under `/api/v1`. Interactive docs are at `/docs`
(and `/openapi.json`); both are public by design, as is `GET /api/v1/health`.

1. Create a password hash. It is computed locally with the project's own `pwdlib` dependency; the
   password is prompted for and never echoed or stored:

   ```bash
   uv run python -c "import getpass; from pwdlib import PasswordHash; print(PasswordHash.recommended().hash(getpass.getpass()))"
   ```

2. Put the settings in a `.env` file in the directory you start the service from (never commit it).
   Single-quote the hash: it contains `$`.

   ```env
   BUNSHO_AUTH__USERNAME=your-username
   BUNSHO_AUTH__PASSWORD_HASH='<the $argon2id$... hash from step 1>'
   BUNSHO_AUTH__JWT_SECRET=<at least 32 random characters>
   ```

   A suitable secret: `uv run python -c "import secrets; print(secrets.token_urlsafe(48))"`.

3. Start it with `uv run bunsho` (default `127.0.0.1:8192`; port 8000 is refused). If the configuration is
   invalid, every problem is logged together and the process exits with status 2. To let uvicorn manage
   the process instead, use `uv run uvicorn --factory bunsho.main:create_app_from_env`.

### Using the API

- `POST /api/v1/auth/login` with `{"username": ..., "password": ...}` returns an access and a refresh
  token; send the access token as `Authorization: Bearer <token>`. `POST /api/v1/auth/refresh` exchanges a
  refresh token for a new pair.
- `GET /api/v1/admin/config-check` validates the deck, resources and optional services.
- `POST /api/v1/admin/content/build` (body `{}` or `{"dry_run": true}`) starts a background content
  build and answers `202` with a `task_id`; poll `GET /api/v1/admin/content/build/{task_id}` or follow it
  over the WebSocket. `GET /api/v1/content/summary` reports the built content counts.
- `WebSocket /api/v1/ws/tasks`: browsers cannot set headers on a WebSocket and a token in the URL leaks
  into logs, so authenticate with the first message within 5 seconds:
  `{"type": "auth", "token": "<access token>"}`. The server answers `{"type": "ready"}`, then a
  `{"type": "snapshot", ...}` of the latest build if there is one, then `{"type": "event", ...}` messages
  for build state changes and progress. Any invalid first message, a refresh token, or silence closes the
  socket with code 1008.
- Logins are throttled: 5 failures within 60 seconds per client address returns `429` with a
  `Retry-After` header. Validation errors return `422` with only `loc`, `msg` and `type`.
- `/health` reports component status and exception class names only, never messages.
- A build still running when the service shuts down is reported as failed with
  `Cancelled: build interrupted`.

**Reverse proxies and Docker.** The login throttle keys on the client address that uvicorn reports. The
launcher passes no proxy options, so uvicorn's defaults apply: behind a reverse proxy or Docker NAT the
client address is normally the proxy's, and all clients then share one throttle bucket. The Bunshō code
does no forwarded-header handling of its own; the proxy and client-address setup is settled with the
Docker setup in a later plan.

### Settings

Environment variables `BUNSHO_<SECTION>__<KEY>` override the `.env` file, which overrides a TOML file
named by `BUNSHO_CONFIG_FILE` (`BUNSHO_ENV_FILE` names a different `.env`). Keys: `server.host`,
`server.port`, `server.cors_origins` (comma separated; empty means no CORS), `auth.access_ttl_minutes`,
`auth.refresh_ttl_days`, `paths.data_dir`, `paths.resources_dir`, `paths.jamdict_db`, `logging.level`.

`progress.db` (your study history) lives in `data_dir`. When an existing database needs a schema
migration at startup, a timestamped backup is written to `data_dir/backups/` first; a database that is
already current is not backed up.
