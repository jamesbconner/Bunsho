"""Single-flight background content builds with progress fan-out."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from bunsho.context import Context
from bunsho.orchestration.content_build import (
    BuildProgress,
    BuildReport,
    ContentBuildOrchestrator,
)

OrchestratorFactory = Callable[[Context], ContentBuildOrchestrator]


class BuildState(StrEnum):
    """Lifecycle of a build task."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class BuildAlreadyRunningError(RuntimeError):
    """A build was requested while another one is running."""


@dataclass(slots=True)
class BuildTask:
    """State of one build."""

    task_id: str
    dry_run: bool
    state: BuildState
    started_at: datetime
    finished_at: datetime | None = None
    progress: BuildProgress | None = None
    report: BuildReport | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class BuildEvent:
    """A change published to subscribers."""

    kind: Literal["progress", "state"]
    task_id: str
    state: BuildState
    progress: BuildProgress | None = None
    error: str | None = None


class BuildTaskManager:
    """Runs at most one content build at a time in a worker thread."""

    def __init__(
        self,
        ctx: Context,
        orchestrator_factory: OrchestratorFactory,
        *,
        clock: Callable[[], datetime] | None = None,
        max_history: int = 10,
        subscriber_queue_size: int = 512,
    ) -> None:
        """Create a manager.

        Args:
            ctx: Application context (config, logger, content repository handle).
            orchestrator_factory: Builds the orchestrator for a run (may raise, which
                marks the task failed).
            clock: Time source (defaults to UTC now).
            max_history: How many of the newest tasks to remember, including the active
                one. Older tasks are dropped only when a new build starts.
            subscriber_queue_size: Capacity of each subscriber queue.
        """
        self._ctx = ctx
        self._factory = orchestrator_factory
        self._clock = clock or (lambda: datetime.now(UTC))
        self._max_history = max_history
        self._queue_size = subscriber_queue_size
        self._logger = ctx.logger
        self._tasks: dict[str, BuildTask] = {}
        self._active: BuildTask | None = None
        self._runner: asyncio.Task[None] | None = None
        self._subscribers: set[asyncio.Queue[BuildEvent]] = set()

    @property
    def active(self) -> BuildTask | None:
        """The running build, if any."""
        return self._active

    def get(self, task_id: str) -> BuildTask | None:
        """Look up a remembered task."""
        return self._tasks.get(task_id)

    def latest(self) -> BuildTask | None:
        """The most recently started task, if any."""
        return next(reversed(self._tasks.values()), None)

    def subscribe(self) -> asyncio.Queue[BuildEvent]:
        """Register a queue that receives every published event.

        A subscriber that joins mid-build gets no snapshot: only events published from
        now on. Seed the view from ``active`` (and its ``progress``) instead. Always
        call ``unsubscribe`` in a ``finally`` block, or the queue keeps receiving events.
        """
        queue: asyncio.Queue[BuildEvent] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[BuildEvent]) -> None:
        """Stop delivering events to ``queue``."""
        self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        """Number of queues currently subscribed (a live WebSocket holds exactly one)."""
        return len(self._subscribers)

    def start(self, *, dry_run: bool) -> BuildTask:
        """Start a build in the background.

        Must be called on the event loop thread.

        Raises:
            BuildAlreadyRunningError: A build is already running.
        """
        loop = asyncio.get_running_loop()
        if self._active is not None:
            raise BuildAlreadyRunningError(f"build {self._active.task_id} is already running")
        task = BuildTask(
            task_id=uuid.uuid4().hex,
            dry_run=dry_run,
            state=BuildState.RUNNING,
            started_at=self._clock(),
        )
        self._active = task
        self._tasks[task.task_id] = task
        self._trim_history()
        self._runner = loop.create_task(self._run(task, loop))
        self._logger.info("content_build_task_started task_id=%s dry_run=%s", task.task_id, dry_run)
        self._publish(BuildEvent("state", task.task_id, task.state))
        return task

    async def join(self) -> None:
        """Wait for the active build (if any) to finish, even if its runner was cancelled."""
        runner = self._runner
        if runner is not None and not runner.done():
            await asyncio.wait({runner})

    async def aclose(self, timeout: float = 30.0) -> None:
        """Wait up to ``timeout`` seconds for an active build; log if it keeps running."""
        runner = self._runner
        if runner is None or runner.done():
            return
        _done, pending = await asyncio.wait({runner}, timeout=timeout)
        if pending:
            self._logger.warning("content_build_still_running_at_shutdown timeout=%s", timeout)

    def _trim_history(self) -> None:
        for task_id in list(self._tasks):
            if len(self._tasks) <= self._max_history:
                break
            if self._tasks[task_id] is not self._active:
                del self._tasks[task_id]

    async def _run(self, task: BuildTask, loop: asyncio.AbstractEventLoop) -> None:
        worker: asyncio.Future[BuildReport] | None = None
        try:
            orchestrator = self._factory(self._ctx)
            config = self._ctx.config
            # The thread future is shielded so that cancelling this runner cannot make the
            # build look finished while the worker thread is still writing content.db.
            worker = asyncio.ensure_future(
                asyncio.to_thread(
                    orchestrator.build,
                    config.deck_path,
                    config.content_db_path,
                    dry_run=task.dry_run,
                    on_progress=self._make_callback(task, loop),
                )
            )
            task.report = await asyncio.shield(worker)
            task.state = BuildState.SUCCEEDED
            if not task.dry_run:
                self._refresh_content_repo(task)
        except asyncio.CancelledError:
            task.state = BuildState.FAILED
            task.error = "Cancelled: build interrupted"
            self._logger.warning("content_build_task_cancelled task_id=%s", task.task_id)
            if worker is not None:
                await self._wait_for_worker(worker)
            raise
        except Exception as exc:
            # Any failure (including a factory error) is reported on the task, not raised.
            task.state = BuildState.FAILED
            task.error = f"{type(exc).__name__}: {exc}"
            self._logger.error(
                "content_build_task_failed task_id=%s error=%s",
                task.task_id,
                task.error,
                exc_info=True,
            )
        finally:
            # Release the single-flight slot first so a failing clock cannot wedge the manager.
            self._active = None
            task.finished_at = self._clock()
            self._logger.info(
                "content_build_task_finished task_id=%s state=%s", task.task_id, task.state
            )
            # Progress events precede this one because call_soon_threadsafe callbacks run in
            # FIFO order ahead of the to_thread completion that resumed this coroutine.
            self._publish(BuildEvent("state", task.task_id, task.state, error=task.error))

    def _refresh_content_repo(self, task: BuildTask) -> None:
        try:
            self._ctx.refresh_content_repo()
        except Exception:
            self._logger.exception("content_repo_refresh_failed task_id=%s", task.task_id)
            raise

    @staticmethod
    async def _wait_for_worker(worker: asyncio.Future[BuildReport]) -> None:
        """Wait for the worker thread to end (a thread cannot be interrupted)."""
        while not worker.done():
            try:
                await asyncio.wait({worker})
            except asyncio.CancelledError:
                continue  # cancelled again: the thread still owns content.db, keep waiting
        if not worker.cancelled():
            worker.exception()  # mark the outcome as retrieved; the task is already failed

    def _make_callback(
        self, task: BuildTask, loop: asyncio.AbstractEventLoop
    ) -> Callable[[BuildProgress], None]:
        last_stage: str | None = None

        def callback(progress: BuildProgress) -> None:
            # Runs in the worker thread: it must never raise, or it would abort the build.
            nonlocal last_stage
            try:
                stage_changed = progress.stage != last_stage
                last_stage = progress.stage
                step = max(1, progress.total // 100)
                if not (
                    stage_changed
                    or progress.current in (0, progress.total)
                    or progress.current % step == 0
                ):
                    return
                loop.call_soon_threadsafe(self._on_progress, task, progress)
            except Exception:  # includes RuntimeError when the event loop closed at shutdown
                self._logger.exception("build_progress_callback_failed task_id=%s", task.task_id)

        return callback

    def _on_progress(self, task: BuildTask, progress: BuildProgress) -> None:
        if task.state is not BuildState.RUNNING:
            return  # a late callback from a build that has already ended or been cancelled
        task.progress = progress
        self._publish(BuildEvent("progress", task.task_id, task.state, progress=progress))

    def _publish(self, event: BuildEvent) -> None:
        for queue in list(self._subscribers):
            if queue.full():
                queue.get_nowait()  # drop the oldest so the newest (e.g. the final state) fits
            queue.put_nowait(event)
