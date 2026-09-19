import asyncio
import threading
from pathlib import Path

import pytest

from bunsho.config.settings import AppConfig
from bunsho.context import Context
from bunsho.orchestration.build_tasks import (
    BuildAlreadyRunningError,
    BuildEvent,
    BuildState,
    BuildTaskManager,
)
from bunsho.orchestration.content_build import BuildProgress, BuildReport, ContentBuildError
from bunsho.services.content_repository import ContentWriter


def _report(dry_run: bool) -> BuildReport:
    return BuildReport(
        dry_run=dry_run,
        target=Path("content.db"),
        deck_sha256="a" * 64,
        kana_count=208,
        kanji_count=3,
        vocab_count=2,
        sentence_count=0,
        vocab_by_level={"N5": 2},
        kanji_by_level={"N5": 3},
        kanji_without_details=0,
        duration_seconds=0.1,
    )


class _Stub:
    """Fake orchestrator: emits progress, optionally blocks, fails, or writes content.db."""

    def __init__(
        self,
        *,
        items: int = 3,
        gate: threading.Event | None = None,
        error: Exception | None = None,
    ) -> None:
        self.items = items
        self.gate = gate
        self.error = error

    def build(self, deck_path, target, *, dry_run=False, on_progress=None):  # type: ignore[no-untyped-def]
        assert on_progress is not None
        on_progress(BuildProgress("import_deck", 0, 1))
        on_progress(BuildProgress("import_deck", 1, 1))
        for index in range(1, self.items + 1):
            on_progress(BuildProgress("enrich_kanji", index, self.items))
        if self.gate is not None:
            assert self.gate.wait(10), "test gate was never released"
        if self.error is not None:
            raise self.error
        if not dry_run:
            on_progress(BuildProgress("write", 0, 1))
            ContentWriter().write(target, kana=[], kanji=[], vocab=[], meta={})
            on_progress(BuildProgress("write", 1, 1))
        return _report(dry_run)


def _manager(  # type: ignore[no-untyped-def]
    app_config: AppConfig, quiet_logger, stub: _Stub, **kwargs
) -> tuple[Context, BuildTaskManager]:
    ctx = Context(config=app_config, logger=quiet_logger)
    return ctx, BuildTaskManager(ctx, lambda _ctx: stub, **kwargs)  # type: ignore[arg-type,return-value]


def _drain(queue: "asyncio.Queue[BuildEvent]") -> list[BuildEvent]:
    events: list[BuildEvent] = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events


def test_successful_build_publishes_events_and_refreshes_the_repository(
    app_config: AppConfig,
    quiet_logger,  # type: ignore[no-untyped-def]
) -> None:
    async def scenario() -> None:
        ctx, manager = _manager(app_config, quiet_logger, _Stub())
        queue = manager.subscribe()
        assert ctx.content_repo is None
        task = manager.start(dry_run=False)
        assert task.state is BuildState.RUNNING
        assert manager.active is task
        await manager.join()
        assert task.state is BuildState.SUCCEEDED
        assert task.report is not None
        assert task.finished_at is not None
        assert manager.active is None
        assert ctx.content_repo is not None  # refreshed after the real build
        events = _drain(queue)
        assert (events[0].kind, events[0].state) == ("state", BuildState.RUNNING)
        assert (events[-1].kind, events[-1].state) == ("state", BuildState.SUCCEEDED)
        stages = [e.progress.stage for e in events if e.progress is not None]
        assert stages[0] == "import_deck"
        assert stages[-1] == "write"
        assert manager.get(task.task_id) is task
        assert manager.latest() is task

    asyncio.run(scenario())


def test_dry_run_does_not_refresh_the_repository(app_config: AppConfig, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    async def scenario() -> None:
        ctx, manager = _manager(app_config, quiet_logger, _Stub())
        task = manager.start(dry_run=True)
        await manager.join()
        assert task.state is BuildState.SUCCEEDED
        assert task.report is not None
        assert ctx.content_repo is None
        assert not app_config.content_db_path.exists()

    asyncio.run(scenario())


def test_failure_marks_the_task_failed_and_allows_a_new_build(
    app_config: AppConfig,
    quiet_logger,  # type: ignore[no-untyped-def]
) -> None:
    async def scenario() -> None:
        stub = _Stub(error=ContentBuildError("jamdict is unavailable"))
        _ctx, manager = _manager(app_config, quiet_logger, stub)
        queue = manager.subscribe()
        task = manager.start(dry_run=False)
        await manager.join()
        assert task.state is BuildState.FAILED
        assert task.error == "ContentBuildError: jamdict is unavailable"
        final = _drain(queue)[-1]
        assert (final.state, final.error) == (BuildState.FAILED, task.error)
        stub.error = None
        second = manager.start(dry_run=True)  # not blocked by the failed build
        await manager.join()
        assert second.state is BuildState.SUCCEEDED

    asyncio.run(scenario())


def test_a_factory_error_is_reported_as_a_failed_task(app_config: AppConfig, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    def broken_factory(_ctx: Context):  # type: ignore[no-untyped-def]
        raise ContentBuildError("cannot build content")

    async def scenario() -> None:
        manager = BuildTaskManager(Context(config=app_config, logger=quiet_logger), broken_factory)
        task = manager.start(dry_run=False)
        await manager.join()
        assert task.state is BuildState.FAILED
        assert "cannot build content" in (task.error or "")

    asyncio.run(scenario())


def test_only_one_build_may_run_at_a_time(app_config: AppConfig, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    async def scenario() -> None:
        gate = threading.Event()
        _ctx, manager = _manager(app_config, quiet_logger, _Stub(gate=gate))
        first = manager.start(dry_run=False)
        with pytest.raises(BuildAlreadyRunningError, match=first.task_id):
            manager.start(dry_run=True)
        gate.set()
        await manager.join()
        assert first.state is BuildState.SUCCEEDED

    asyncio.run(scenario())


def test_progress_events_are_throttled(app_config: AppConfig, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    async def scenario() -> None:
        _ctx, manager = _manager(app_config, quiet_logger, _Stub(items=3000))
        queue = manager.subscribe()
        manager.start(dry_run=True)
        await manager.join()
        events = _drain(queue)
        enrich = [e.progress for e in events if e.progress and e.progress.stage == "enrich_kanji"]
        assert 90 <= len(enrich) <= 140  # about one per percent, not 3000
        assert enrich[-1] == BuildProgress("enrich_kanji", 3000, 3000)

    asyncio.run(scenario())


def test_a_full_subscriber_queue_drops_old_events_but_keeps_the_final_state(
    app_config: AppConfig,
    quiet_logger,  # type: ignore[no-untyped-def]
) -> None:
    async def scenario() -> None:
        _ctx, manager = _manager(
            app_config, quiet_logger, _Stub(items=500), subscriber_queue_size=2
        )
        queue = manager.subscribe()
        manager.start(dry_run=True)
        await manager.join()
        events = _drain(queue)
        assert len(events) == 2
        assert (events[-1].kind, events[-1].state) == ("state", BuildState.SUCCEEDED)

    asyncio.run(scenario())


def test_history_is_trimmed_and_unsubscribed_queues_get_nothing(
    app_config: AppConfig,
    quiet_logger,  # type: ignore[no-untyped-def]
) -> None:
    async def scenario() -> None:
        _ctx, manager = _manager(app_config, quiet_logger, _Stub(), max_history=2)
        queue = manager.subscribe()
        manager.unsubscribe(queue)
        tasks = []
        for _ in range(3):
            tasks.append(manager.start(dry_run=True))
            await manager.join()
        assert manager.get(tasks[0].task_id) is None
        assert manager.get(tasks[1].task_id) is tasks[1]
        assert manager.latest() is tasks[2]
        assert queue.empty()

    asyncio.run(scenario())


def test_aclose_waits_for_the_active_build(app_config: AppConfig, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    async def scenario() -> None:
        gate = threading.Event()
        _ctx, manager = _manager(app_config, quiet_logger, _Stub(gate=gate))
        task = manager.start(dry_run=True)
        asyncio.get_running_loop().call_later(0.05, gate.set)
        await manager.aclose(timeout=5)
        assert task.state is BuildState.SUCCEEDED

    asyncio.run(scenario())
