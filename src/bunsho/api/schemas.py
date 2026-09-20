"""Pydantic request and response models for the API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from bunsho import __version__
from bunsho.orchestration.build_tasks import BuildEvent, BuildState, BuildTask
from bunsho.services.config_check import CheckResult
from bunsho.services.health import HealthReport

Status = Literal["ok", "degraded", "error"]


class LoginRequest(BaseModel):
    """Credentials for ``POST /auth/login``."""

    username: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=1024)


class RefreshRequest(BaseModel):
    """Body of ``POST /auth/refresh``."""

    refresh_token: str = Field(min_length=1)


class TokenResponse(BaseModel):
    """An access and refresh token."""

    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int


class ComponentHealthModel(BaseModel):
    """Health of one component."""

    status: Status
    detail: str
    latency_ms: float


class HealthResponse(BaseModel):
    """Response of ``GET /health``."""

    status: Status
    version: str
    components: dict[str, ComponentHealthModel]


class CheckResultModel(BaseModel):
    """One config check."""

    name: str
    ok: bool
    detail: str


class ConfigCheckResponse(BaseModel):
    """Response of ``GET /admin/config-check``."""

    ok: bool
    checks: list[CheckResultModel]


class BuildRequest(BaseModel):
    """Body of ``POST /admin/content/build``."""

    dry_run: bool = False


class BuildProgressModel(BaseModel):
    """Progress of a running build."""

    stage: str
    current: int
    total: int


class BuildReportModel(BaseModel):
    """Summary of a finished build."""

    dry_run: bool
    target: str
    deck_sha256: str
    kana_count: int
    kanji_count: int
    unleveled_kanji_count: int
    vocab_count: int
    sentence_count: int
    vocab_by_level: dict[str, int]
    kanji_by_level: dict[str, int]
    kanji_without_details: int
    duration_seconds: float


class BuildStatusResponse(BaseModel):
    """State of a build task."""

    task_id: str
    state: BuildState
    dry_run: bool
    started_at: datetime
    finished_at: datetime | None
    progress: BuildProgressModel | None
    report: BuildReportModel | None
    error: str | None


class ContentSummaryResponse(BaseModel):
    """Response of ``GET /content/summary``."""

    built: bool
    kana: int = 0
    kanji: int = 0
    vocab: int = 0
    meta: dict[str, str] = Field(default_factory=dict)


def health_response(report: HealthReport) -> HealthResponse:
    """Convert a ``HealthReport`` to its response model."""
    return HealthResponse(
        status=report.status,
        version=__version__,
        components={
            name: ComponentHealthModel(
                status=c.status, detail=c.detail, latency_ms=round(c.latency_ms, 2)
            )
            for name, c in report.components.items()
        },
    )


def config_check_response(results: list[CheckResult]) -> ConfigCheckResponse:
    """Convert check results to the response model."""
    return ConfigCheckResponse(
        ok=all(r.ok for r in results),
        checks=[CheckResultModel(name=r.name, ok=r.ok, detail=r.detail) for r in results],
    )


def build_status(task: BuildTask) -> BuildStatusResponse:
    """Convert a ``BuildTask`` to its response model."""
    report = task.report
    return BuildStatusResponse(
        task_id=task.task_id,
        state=task.state,
        dry_run=task.dry_run,
        started_at=task.started_at,
        finished_at=task.finished_at,
        progress=(
            BuildProgressModel(
                stage=task.progress.stage,
                current=task.progress.current,
                total=task.progress.total,
            )
            if task.progress
            else None
        ),
        report=(
            BuildReportModel(
                dry_run=report.dry_run,
                target=str(report.target),
                deck_sha256=report.deck_sha256,
                kana_count=report.kana_count,
                kanji_count=report.kanji_count,
                unleveled_kanji_count=report.unleveled_kanji_count,
                vocab_count=report.vocab_count,
                sentence_count=report.sentence_count,
                vocab_by_level=report.vocab_by_level,
                kanji_by_level=report.kanji_by_level,
                kanji_without_details=report.kanji_without_details,
                duration_seconds=round(report.duration_seconds, 3),
            )
            if report
            else None
        ),
        error=task.error,
    )


class WsAuthMessage(BaseModel):
    """First message a WebSocket client must send."""

    type: Literal["auth"]
    token: str = Field(min_length=1)


class WsReady(BaseModel):
    """Sent once after a successful WebSocket authentication."""

    type: Literal["ready"] = "ready"


class BuildEventModel(BaseModel):
    """A build event as sent over the WebSocket."""

    kind: Literal["progress", "state"]
    task_id: str
    state: BuildState
    progress: BuildProgressModel | None
    error: str | None


class WsSnapshot(BaseModel):
    """The latest known build, sent right after ``ready``."""

    type: Literal["snapshot"] = "snapshot"
    task: BuildStatusResponse


class WsEvent(BaseModel):
    """One build event."""

    type: Literal["event"] = "event"
    event: BuildEventModel


def build_event(event: BuildEvent) -> BuildEventModel:
    """Convert a ``BuildEvent`` to its WebSocket model."""
    progress = event.progress
    return BuildEventModel(
        kind=event.kind,
        task_id=event.task_id,
        state=event.state,
        progress=(
            BuildProgressModel(stage=progress.stage, current=progress.current, total=progress.total)
            if progress
            else None
        ),
        error=event.error,
    )
