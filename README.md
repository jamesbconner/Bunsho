# Bunshō (文章)

A Japanese language learning tool: hiragana, katakana, JLPT N5-N1 kanji and vocabulary, and
spaced-repetition flashcards. Runs as a containerized FastAPI + React web app on a home server.

Status: early development. See `docs/superpowers/specs/` for the design.

## Running the service

Bunshō serves an authenticated REST + WebSocket API under `/api/v1`. Interactive docs are at `/docs`
(and `/openapi.json`); both are public by design, as is `GET /api/v1/health`.

1. Create a password hash. It is computed locally with the project's own `pwdlib` dependency; the
   password is prompted for twice (a typo aborts) and never echoed or stored:

   ```bash
   uv run python -c "import getpass; from pwdlib import PasswordHash; p = getpass.getpass('Password: '); assert p == getpass.getpass('Repeat: '), 'passwords differ'; print(PasswordHash.recommended().hash(p))"
   ```

   In Git Bash `getpass` may not work; use PowerShell, or prefix the command with `winpty`.

2. Put the settings in a `.env` file in the directory you start the service from (never commit it).
   Single-quote the hash: it contains `$`.

   ```env
   BUNSHO_AUTH__USERNAME=your-username
   BUNSHO_AUTH__PASSWORD_HASH='<the $argon2id$... hash from step 1>'
   BUNSHO_AUTH__JWT_SECRET=<at least 32 random characters>
   ```

   A suitable secret: `uv run python -c "import secrets; print(secrets.token_urlsafe(48))"`.

   The hash can instead be set as a real environment variable, which overrides `.env`. Always use single
   quotes (or, in YAML, escape each `$`), otherwise the shell mangles the `$` signs:

   ```bash
   export BUNSHO_AUTH__PASSWORD_HASH='$argon2id$...'          # bash
   ```

   ```powershell
   $env:BUNSHO_AUTH__PASSWORD_HASH='$argon2id$...'            # PowerShell, never double quotes
   ```

   ```yaml
   BUNSHO_AUTH__PASSWORD_HASH: "$$argon2id$$v=19$$..."         # docker-compose: each $ becomes $$
   ```

3. Start it with `uv run bunsho` (default `127.0.0.1:8192`; port 8000 is refused). If the configuration is
   invalid, every problem is logged together and the process exits with status 2. After starting, log in
   once to confirm the password you hashed is the one you meant to set.

4. First run. `paths.data_dir` defaults to `data` and `paths.resources_dir` to `resources`, both relative
   to the current working directory, so starting the service from another directory silently creates a
   new, empty `./data`; start it from the project root or set both paths explicitly. The content build
   needs the deck at `resources/JLPT_N5_to_N1_Japanese_Vocabulary.apkg`. Call
   `GET /api/v1/admin/config-check` first: it reports whether the deck and its checksum are in place.

### Limits

- Run a single worker (the `bunsho` launcher always does; never use `--workers` or `--reload` in service
  use). The login throttle and the build task manager live in process memory and reset on restart.
- The service speaks plain HTTP and does no HTTPS: passwords and tokens travel in clear text.
- It is meant for a home network only; do not expose it to the internet.
- Reverse proxies and Docker: unless `server.trusted_proxies` is set, Bunshō ignores `X-Forwarded-For`
  and similar headers and keys the login throttle on the TCP peer address, so behind a reverse proxy or
  Docker Desktop NAT every client shares one throttle bucket. See "Trusted proxies" under "Running with
  Docker" for the setting and what it makes you responsible for.

### Using the API

- `POST /api/v1/auth/login` with `{"username": ..., "password": ...}` returns an access and a refresh
  token; send the access token as `Authorization: Bearer <token>`. `POST /api/v1/auth/refresh` exchanges a
  refresh token for a new pair of the same login session. `POST /api/v1/auth/logout` with
  `{"refresh_token": ...}` ends that session on the server: the refresh token, every access token of the
  login and its open WebSocket streams stop working (streams close with code 1008). It answers `204` for
  any token, valid or not, and needs no access token. Revoked sessions are stored in `progress.db`, so
  they stay revoked across restarts.
- `GET /api/v1/admin/config-check` validates the deck, resources and optional services.
- `POST /api/v1/admin/content/build` (body `{}` or `{"dry_run": true}`) starts a background content
  build and answers `202` with a `task_id`; poll `GET /api/v1/admin/content/build/{task_id}` or follow it
  over the WebSocket. `GET /api/v1/content/summary` reports the built content counts.
- `WebSocket /api/v1/ws/tasks`: browsers cannot set headers on a WebSocket and a token in the URL leaks
  into logs, so authenticate with the first message within 5 seconds:
  `{"type": "auth", "token": "<access token>"}`. The server answers `{"type": "ready"}`, then a
  `{"type": "snapshot", ...}` of the latest build if there is one, then `{"type": "event", ...}` messages
  for build state changes and progress. Any invalid first message, a refresh token, a token of a revoked session, or silence closes the
  socket with code 1008, and so does logging out the session that authenticated it.
- Logins are throttled: 5 failures within 60 seconds per client address returns `429` with a
  `Retry-After` header. Validation errors return `422` with only `loc`, `msg` and `type`.
- `/health` reports component status and exception class names only, never messages.
- A build still running when the service shuts down is reported as failed with
  `Cancelled: build interrupted`.

### Settings

Environment variables `BUNSHO_<SECTION>__<KEY>` override the `.env` file, which overrides a TOML file
named by `BUNSHO_CONFIG_FILE` (`BUNSHO_ENV_FILE` names a different `.env`). Keys: `server.host`,
`server.port`, `server.cors_origins` (comma separated; empty means no CORS), `server.trusted_proxies`
(comma separated IP addresses or CIDR networks whose `X-Forwarded-For` header is believed; empty, the
default, means proxy headers are ignored), `server.csp_report_only` (`true` sends the
Content-Security-Policy as `Content-Security-Policy-Report-Only`: the browser reports violations in its
console and blocks nothing; default `false`), `auth.access_ttl_minutes`, `auth.refresh_ttl_days`,
`paths.data_dir`, `paths.resources_dir`, `paths.jamdict_db`, `logging.level`.

`progress.db` (your study history) lives in `data_dir`. When an existing database needs a schema
migration at startup, a timestamped backup is written to `data_dir/backups/` first, named
`progress-<UTC timestamp>-from-<revision or unversioned>.db`; a database that is already current is not
backed up. Migrations run under a lock file (`progress.db.migrate.lock`, left in place and harmless), so
two processes starting at once cannot collide. Backups are never pruned; delete old ones yourself.
To restore a backup, stop the service, delete `progress.db-wal` and `progress.db-shm` next to
`progress.db` (SQLite would replay a leftover `-wal` onto the restored file and corrupt it), then copy
the backup over `progress.db`.

### Studying (review API)

After a content build, the API serves flashcards. Every route needs a bearer token.

| Route | What it does |
|---|---|
| `GET /api/v1/reviews/next` | The next card (with its content, and how long each grade would wait), or no card plus `next_due_at`; also the counts still to do. Fetching creates nothing. |
| `POST /api/v1/reviews/answer` | Grade a card: `item_id`, `direction`, `grade` (1 Again, 2 Hard, 3 Good, 4 Easy), `expected_last_review` (copied from the card; `null` for a new card) and optionally `duration_ms`. A card that changed in the meantime (a double submit, or a second device) answers `409`. |
| `GET /api/v1/stats/summary` | Reviews today, the last 30 days, 30-day retention, and progress per type and JLPT level. |
| `GET /api/v1/settings`, `PUT /api/v1/settings` | The review settings (below). `PUT` replaces the whole document. |

A card is an item plus a direction: kana `glyph_to_sound` / `sound_to_glyph`, kanji `kanji_to_meaning` / `kanji_to_reading` / `meaning_to_kanji`, vocabulary `recognition` / `recall`. Item ids are opaque strings taken from the API (`vocab:度:ど#2` exists); do not build or parse them. A card is created the first time it is graded; scheduling uses FSRS with a configurable target retention.

**Settings** (defaults in brackets): `new_card_policy` (`strict_order`: N5 first, then N4 and so on; `mastery_unlock`: the next level also waits until `mastery_threshold` [0.80] of the current level's cards are in the FSRS Review state; `pinned_levels`: only `active_levels` [`["N5"]`]), `new_limits` per type in **cards** per day (kana 20, kanji 15, vocab 20; `0` = unlimited), `type_enabled` per type (all `true`; a `false` type introduces no new cards but its scheduled cards stay due; all three `false` means reviews only), `kana_gate` (`kanji` and `vocab`, both `false`: hold that type's new cards back until `threshold` [0.80] of all kana cards, both directions, are in the FSRS Review state; needs kana enabled; checked on every plan, so a later dip pauses them again), `target_retention` [0.90, range 0.70-0.99] and `rollover_hour` [4, range 0-23]. Unleveled kanji are never offered.

Some behaviours to know about:

- `POST /reviews/answer` accepts any known item; it does not check that the card is due or was the one offered. This is a single-user app, and the stale-answer check (`409`) only protects against double submits and two devices.
- Changing `rollover_hour` mid-day moves the study-day window, so that day's new-card allowance can look larger or smaller.
- `pinned_levels` offers `active_levels` in study order N5 to N1, whatever order the list is written in.

**Study day and timezone.** Daily limits reset at `rollover_hour` in the server's timezone, read from the `TZ` environment variable (an IANA name such as `America/New_York`). Without `TZ` the study day uses UTC and the service logs a warning. In Docker, put `TZ=America/New_York` in the env file next to the credentials.

**One instance per data folder.** The service takes an exclusive lock (`.bunsho.instance.lock`) in the data folder; a second instance on the same folder refuses to start with an explanatory error. `progress.db` runs in WAL mode, so you will also see `progress.db-wal` and `progress.db-shm` files next to it; back up the folder with the service stopped, or use the timestamped backups in `backups/`. When you restore, stop the service and remove those two files first (see the note under "Where the data lives" and the restore steps above).

**Web UI.** The Docker image contains the built web UI and serves it at `http://<host>:8192/` (log in with the credentials from your env file; the pages are `/` for the dashboard and content summary, `/review` for the study session, `/stats` for statistics, `/settings` for the settings (its System tab, `/settings?tab=system`, has the service status and the content build; the old `/build` address redirects there) and `/login`). Outside Docker the API serves the UI only when `paths.frontend_dir` (`BUNSHO_PATHS__FRONTEND_DIR`) points at a built `frontend/dist`; unset, it serves the API only. Unknown paths under `/api` stay JSON 404s. The UI's Log out clears the tokens in this browser and asks the server to end the session; if the server cannot be reached the token stays valid until it expires (30 days by default).

**Studying in the browser.** Open the dashboard (`/`) and press *Study now*, or use the *Study* link. The review shows one card at a time: press Space or Enter (or *Show answer*) to flip it, then grade yourself with the buttons or the keys `1` Again, `2` Hard, `3` Good, `4` Easy (each button shows when the card would come back). Furigana is hidden on the front of cards that test a word's reading or meaning and shown once you flip the card; the *Show furigana* switch also shows it on the front (remembered in this browser only). There is no undo, because every grade is written to the append-only review log.

Typed-answer and multiple-choice are two more ways to answer, chosen per item type (kana,
kanji, vocabulary) on the Settings page. Both grade automatically — correct is graded Good,
wrong is graded Again — and show whether you were right before you continue to the next card;
a wrong typed answer also shows the correct one, and multiple-choice always highlights the
correct option regardless of your pick.

**Statistics and settings.** *Statistics* shows today's reviews and new cards, your 30-day retention, a chart of the last 30 days, the number of cards by state and your progress through each JLPT level. *Settings* has four tabs: *Learning path* (how new cards are chosen, which types introduce new cards, the optional *Kana first* gate, the levels used by *Pinned levels* and the mastery threshold used by *Mastery unlock*), *Pace* (the daily new-card limits, where 0 means unlimited, the hour a new study day starts in the server's timezone, and your target retention), *Reviewing* (how you answer each type of card) and *System* (the service's status and *Build content*). Nothing is saved until you press *Save*; the new settings apply from the next card. *Discard changes* puts every field back to what was last saved, and *Reset all tabs to recommended values* only refills the form. The Save, Discard and Reset buttons stay in view at the bottom of the window.

**Developing the UI.** Requires Node 24 or newer. Start the backend (`uv run bunsho`), then in `frontend/`: `npm ci`, `npm run dev`, and open `http://localhost:5173`. The dev server proxies `/api` (WebSocket included) to `http://127.0.0.1:8192`, so no CORS setup is needed (set `VITE_API_TARGET` if the backend runs elsewhere). Other commands: `npm run lint`, `npm run format:check`, `npm test`, `npm run coverage`, `npm run build`. After changing the API, refresh the frontend's types: `uv run python scripts/export_openapi.py` (rewrites `frontend/openapi.json`; a unit test fails while it is stale), then `npm run gen:api`, and commit both files. The `BUNSHO_SERVER__CORS_ORIGINS` setting remains available for setups that do not use the proxy.

## Running with Docker

The repository ships a multi-stage `Dockerfile` and a `compose.yaml` that run the same service as one
container (one replica only: never scale it or add workers). The image is about 518 MB, of which about
310 MB is the dictionary database. The Japanese vocabulary deck is **not** baked into the image: compose
mounts the repository's `resources/` folder read-only at `/app/resources` (the deck is GPL-3.0, the
application is MIT).

### Prerequisites

- Docker with Compose v2 (the commands below were checked with Docker 29 and Compose v5).
- The deck in `resources/`: it is committed to the repository, so a clone already has it.
- An env file with the three required settings. compose refuses to build, start or even print the
  configuration (`docker compose config`) when the env file is missing. When the env file is present,
  the output of `docker compose config` contains the JWT secret and the password hash in clear: do not
  paste it into an issue or a chat.

### Configure

Create `.env` next to `compose.yaml` with the same three settings as step 2 of "Running the service"
(create the hash the same way, with `uv run` on the host):

```env
BUNSHO_AUTH__USERNAME=your-username
BUNSHO_AUTH__PASSWORD_HASH='<the $argon2id$... hash>'
BUNSHO_AUTH__JWT_SECRET=<at least 32 random characters>
```

The hash contains `$`, so single-quote it in an env file (the quotes are removed by compose). Only if you
put the hash into a YAML `environment:` block of a compose file do you write each `$` as `$$`.

The single quotes are a Docker Compose `env_file` convention. `docker run --env-file` does **not** strip
them, so with plain `docker run` write the hash unquoted; otherwise the service exits with status 2 and
"[auth] password_hash is required and must be an argon2 hash".

The container gets `BUNSHO_SERVER__HOST=0.0.0.0`, `BUNSHO_PATHS__DATA_DIR=/data` and
`BUNSHO_PATHS__RESOURCES_DIR=/app/resources` from the image, so no path settings are needed. Two
host-side variables, read by compose itself, are optional: `BUNSHO_ENV_FILE` (a different env file,
default `.env`) and `BUNSHO_HOST_PORT` (the published host port, default `8192`).

### Start and first run

```bash
docker compose up -d --build
docker compose ps
```

`docker compose ps` shows `(healthy)` after up to a minute. On a first run the health endpoint answers
HTTP 200 with status `degraded` (no content built yet), which Docker counts as healthy; after a content
build it says `ok`. An HTTP 503 (the progress database is down) is reported as unhealthy. The health
check adds one access-log line every 30 seconds.

Then the first-run flow from "Running the service", here with `curl` (bash; on Windows use Git Bash, or
make the same calls from the interactive docs at `http://localhost:8192/docs`). Replace the username and
password with the ones you hashed:

```bash
BASE=http://localhost:8192/api/v1

curl -s -w '\n' "$BASE/health"

TOKEN=$(curl -s -X POST "$BASE/auth/login" -H 'Content-Type: application/json' \
  -d '{"username":"your-username","password":"your-password"}' \
  | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')

curl -s -w '\n' -H "Authorization: Bearer $TOKEN" "$BASE/admin/config-check"

TASK=$(curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}' \
  "$BASE/admin/content/build" | sed -n 's/.*"task_id":"\([^"]*\)".*/\1/p')

# Repeat until "state" is no longer "running" ("succeeded" on success); about 40 seconds.
curl -s -w '\n' -H "Authorization: Bearer $TOKEN" "$BASE/admin/content/build/$TASK"

curl -s -w '\n' -H "Authorization: Bearer $TOKEN" "$BASE/content/summary"
```

`config-check` should report the deck and its checksum as present. The access token expires after
15 minutes by default; log in again if a later call answers `401`.

### Where the data lives

The named volume `bunsho-data` is mounted at `/data` and holds `progress.db` (your study history),
`content.db` (rebuilt from the deck at any time) and, once a migration backup has been taken,
`backups/`. Because the compose project is named
`bunsho`, the volume's full name is `bunsho_bunsho-data` (see `docker volume ls`). It survives
`docker compose down`; only `docker compose down -v` deletes it, and your study history with it.

Every `docker run ... busybox` command below mounts the volume at `/data`. Shell notes for them:

- Linux, macOS and PowerShell: nothing special (in PowerShell write `-v "${PWD}:/backup"` where a command
  has `-v "$PWD":/backup`).
- **Git Bash on Windows** rewrites container-side paths (`/data` becomes `C:/Program Files/Git/data`), so
  every one of these commands fails with "No such file or directory". Run `export MSYS_NO_PATHCONV=1` once
  in that shell before them (or put `MSYS_NO_PATHCONV=1` in front of each `docker run`), and where a
  command has `-v "$PWD":/backup` write `-v "$(pwd -W)":/backup` instead.
- If your compose project is not named `bunsho` (for example you used `-p`), the volume is called
  `<project>_bunsho-data`; substitute it in every command. Check with `docker volume ls`.

Back up the whole volume to a tarball in the current directory. Stop the service first so the copy is
consistent:

```bash
docker compose stop
docker run --rm -v bunsho_bunsho-data:/data -v "$PWD":/backup busybox tar czf /backup/bunsho-data.tgz -C /data .
docker compose start
```

To restore a tarball, stop the service and extract it into the volume (if you removed the volume, run
`docker compose up -d` and `docker compose stop` once to recreate it). `progress.db` runs in WAL mode, and
SQLite replays a leftover `progress.db-wal` onto whatever `progress.db` sits beside it, which can corrupt
the restored database: extract into an empty volume, or delete `progress.db-wal` and `progress.db-shm`
first, as the first command below does. The archive carries the file owners, so the service user keeps
access:

```bash
docker run --rm -v bunsho_bunsho-data:/data busybox rm -f /data/progress.db-wal /data/progress.db-shm
docker run --rm -v bunsho_bunsho-data:/data -v "$PWD":/backup busybox tar xzf /backup/bunsho-data.tgz -C /data
```

### Upgrading

```bash
git pull
docker compose up -d --build
```

At startup the service migrates `progress.db` if needed, after copying the existing file to
`backups/progress-<UTC timestamp>-from-<revision or unversioned>.db` in the volume. The `backups/`
folder only exists once a migration backup has been taken, so on a fresh volume `ls /data/backups` failing
with "No such file or directory" is expected. To go back to a backup, stop the service, delete `progress.db-wal` and `progress.db-shm` (a leftover WAL
file would be replayed onto the restored database and corrupt it), copy the backup over `progress.db` and hand
the file back to the service user (a plain `cp` made by root leaves it owned by root), then start it again.
List the backups first and put the file name you want in place of the example:

```bash
docker compose stop
docker run --rm -v bunsho_bunsho-data:/data busybox ls /data/backups
docker run --rm -v bunsho_bunsho-data:/data busybox sh -c \
  'rm -f /data/progress.db-wal /data/progress.db-shm && cp /data/backups/progress-20260101T000000Z-from-unversioned.db /data/progress.db && chown 10001:10001 /data/progress.db'
docker compose start
```

Backups accumulate in the volume; nothing prunes them.

### Stopping

`docker compose stop` sends SIGTERM and waits up to 60 seconds (`stop_grace_period`). A content build
runs in a thread that cannot be interrupted, so a stop issued mid-build waits for the build to finish
(about 40 seconds for the real deck) before the process exits; the 60 seconds cover that. `content.db`
is only replaced when a build completes, so neither a stop nor a hard kill can corrupt it; leftover
`content.db.<hex>.tmp` files from a hard kill are removed at the next start. The container is set to
`restart: unless-stopped`, so it comes back after a reboot or a crash but not after you stop it.

### Data folder ownership

The service runs as the unprivileged user 10001 with a read-only root filesystem, a 64 MB `/tmp`,
`no-new-privileges` and all capabilities dropped. A fresh named volume works with no setup, because
the image creates `/data` owned by that user. A bind mount (`./data:/data`) or a volume created by
root is not writable by it: the service then refuses to start with an error that names the database
path and the backups folder, and, because of `restart: unless-stopped`, keeps restarting in a loop
(`docker compose logs bunsho` shows the message). Fix the ownership and it starts by itself:

```bash
docker run --rm -v bunsho_bunsho-data:/data busybox chown -R 10001:10001 /data
```

For a bind mount run `chown -R 10001:10001 <host directory>` on the host instead.

### Limits and networking

- One replica, one worker: the login throttle and the build task manager live in process memory.
- Run one instance per data volume. Two instances on the same volume both start: the migration lock
  protects only the startup migration, and a starting instance removes leftover build temp files
  (`content.db.<hex>.tmp`), which can break a build running in the other instance. Docker Compose runs a
  single replica; do not scale it (`docker compose up --scale`, `deploy.replicas`).
- The container listens on `0.0.0.0` inside its network and compose publishes `8192` on **all** host
  interfaces, so anything on your LAN can reach it. The app does no HTTPS: passwords and tokens cross
  the network in clear text. Either keep it on a trusted network or put a TLS-terminating reverse proxy
  in front. Never expose the port to the internet.
- Every response carries `X-Content-Type-Options`, `Referrer-Policy` and `X-Frame-Options` headers and a
  Content-Security-Policy. The UI's policy allows only the service's own scripts and styles (styles by a
  per-request nonce); the API is default-deny; `/docs` and `/redoc` get a looser policy so they can load
  Swagger UI and Redoc from `cdn.jsdelivr.net`. If a browser or extension misbehaves under the policy,
  set `BUNSHO_SERVER__CSP_REPORT_ONLY=true` to see the violations in the browser console without
  blocking anything. The service does not send `Strict-Transport-Security`; if a reverse proxy
  terminates TLS, have the proxy send it. The app shell (`index.html`) is read once at startup, so after
  rebuilding the UI with `npm run build`, restart the service to serve the new build.
- To keep the service off the LAN, publish it on the loopback interface only. The simplest way is a
  `compose.override.yaml` next to `compose.yaml` (compose reads it automatically). Plain `ports:` would
  be merged with the existing entry and leave the LAN-wide port open, so replace the list with
  `!override` (needs a recent Compose; checked with v5.1):

  ```yaml
  services:
    bunsho:
      ports: !override
        - "127.0.0.1:8192:8192"
  ```

  With it, `docker compose ps` shows `127.0.0.1:8192->8192/tcp`, and `BUNSHO_HOST_PORT` no longer has an
  effect.
- The WebSocket layer rejects frames over 64 KiB (close code 1009) before they reach the application;
  the first authentication message is additionally capped at 8,192 characters.

### Trusted proxies

Without `BUNSHO_SERVER__TRUSTED_PROXIES` the service ignores proxy headers and keys the login throttle
(5 failed logins per 60 seconds) on the TCP peer address. That has two consequences:

- Behind a reverse proxy every client arrives from the proxy's address and shares one bucket.
- Docker Desktop (Mac, Windows) routes published ports through NAT, so every client, including the other
  machines on your LAN, appears as the gateway address (`172.19.0.1` was observed). The throttle is then
  effectively global: one host's failed logins can lock everyone out for the 60 second window. Docker
  on Linux with a published port preserves the real client address and does not have this problem.

If a reverse proxy such as nginx fronts the service, set the setting in the env file to the proxy's
address or network (comma separated), and make the proxy **overwrite** `X-Forwarded-For` with the
address it sees, so nothing the client sent is passed on:

```env
BUNSHO_SERVER__TRUSTED_PROXIES=192.168.1.10
```

```nginx
proxy_set_header X-Forwarded-For $remote_addr;
```

When the peer is trusted, uvicorn takes the rightmost address in `X-Forwarded-For` that is not itself
trusted as the client, so entries a client prepends before a proxy-supplied one do not help it; but a
proxy that passes a client-supplied header through unchanged still lets clients choose their own
bucket. Trusting an address means believing whatever client address that host reports, so list only
real proxies. Broad but legitimate networks
(for example the Docker bridge `172.16.0.0/12`) are accepted; that is your call, and every host in the
network can then set the client address. Hostnames are not accepted (for example a compose service name
such as `nginx`): use the proxy's IP address or its network. `*`, `0.0.0.0/0`, `::/0` and entries with host bits set (such
as `127.0.0.5/8`) are rejected at startup, together with any other configuration errors.

### Smoke test

```bash
uv run python scripts/smoke_test.py
```

This needs Docker with Compose v2 and the real deck, and takes about a minute with a warm build cache
and up to four minutes cold. It builds the image and starts a throwaway stack (compose project
`bunsho-smoke`, port 18192, generated credentials in a temporary folder), then checks: the first-run
`degraded` health, a `401` for a wrong password, login, a full content build from the real deck (7,734
vocabulary entries, 3,088 kanji, 208 kana), health `ok`, Docker's own health check, a container restart
that keeps the data and accepts the old refresh token, and that forged `X-Forwarded-For` headers do
not give an attacker new throttle buckets. It always removes its containers, network, volume and temp
folder (set `BUNSHO_SMOKE_KEEP=1` to keep them for debugging, `BUNSHO_SMOKE_PORT` to change the port).
It only shares the image tag `bunsho:local` with your own compose stack: it reuses and retags it. CI
runs the same script in its `smoke` job.

## Development

```bash
uv sync --extra dev
```

The checks CI runs (and that must pass before a change is merged):

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
uv run bandit -c pyproject.toml -r src/ -l
uv run pytest --cov
```

The tests fail below 90 % coverage. Some integration tests need the real deck and the jamdict database;
locally they are skipped when either is missing. CI sets `CI=1`, which turns those skips into failures,
so `CI=1 uv run pytest --cov` reproduces what CI sees (PowerShell: `$env:CI=1; uv run pytest --cov`).

The frontend checks (Node 24 or newer), run in `frontend/`, are what CI's `frontend` job runs:

```bash
npm ci
npm run format:check
npm run lint
npm run build      # type-check and production build
npm run coverage   # vitest; fails below 80 %
```

CI also checks that the generated API types are current (`npm run gen:api`, then `git diff --exit-code -- src/api/schema.d.ts`); a backend unit test checks `frontend/openapi.json` against the API.

Git hooks are optional and installed per clone: `uv run pre-commit install` runs YAML and TOML checks,
ruff (lint and format), mypy and bandit on each commit.

## License

The Bunshō source code is released under the MIT License (see `LICENSE`).

Third-party data is **not** covered by it:

- `resources/JLPT_N5_to_N1_Japanese_Vocabulary.apkg` is GPL-3.0 (see `resources/LICENSE` and
  `resources/README.md`). A `content.db` built from it is a derived work.
- Dictionary data comes from `jamdict-data-fix` (JMdict and KANJIDIC2, distributed under the
  [EDRDG licence](https://www.edrdg.org/edrdg/licence.html)). Check those terms before redistributing
  a built `content.db`.
