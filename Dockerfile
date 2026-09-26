# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.13
ARG NODE_VERSION=24

# ---- frontend: build the static UI (no Python needed: the API types are committed) ----
# Pinned to the build host's platform: dist/ is plain static files, so a multi-arch build runs the
# JS build natively once instead of under emulation for every target architecture.
FROM --platform=$BUILDPLATFORM node:${NODE_VERSION}-bookworm-slim AS frontend
WORKDIR /frontend
# Dependencies first so this layer is cached until package.json or the lockfile change.
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci
COPY frontend ./
RUN npm run build

# ---- build: resolve and install locked dependencies into a virtualenv ----
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder
# uv 0.12.17 is pinned in three places (ci.yml, release.yml, Dockerfile); bump them together.
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first so this layer is cached until pyproject.toml or uv.lock change.
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ---- runtime: only the virtualenv, as a non-root user ----
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime
RUN groupadd --system --gid 10001 bunsho \
    && useradd --system --uid 10001 --gid bunsho --home-dir /nonexistent --shell /usr/sbin/nologin bunsho \
    && install -d -o bunsho -g bunsho -m 0750 /data
COPY --from=builder /app/.venv /app/.venv
COPY --from=frontend /frontend/dist /app/frontend
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BUNSHO_SERVER__HOST=0.0.0.0 \
    BUNSHO_PATHS__FRONTEND_DIR=/app/frontend \
    BUNSHO_PATHS__DATA_DIR=/data \
    BUNSHO_PATHS__RESOURCES_DIR=/app/resources
WORKDIR /app
USER bunsho
VOLUME ["/data"]
EXPOSE 8192
# Healthy = HTTP 200 (a first-run "degraded" answer is still 200). HTTP 503 raises and fails.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8192/api/v1/health', timeout=4)"]
STOPSIGNAL SIGTERM
# The launcher, never uvicorn directly: it runs one worker with proxy headers ignored.
ENTRYPOINT ["bunsho"]
