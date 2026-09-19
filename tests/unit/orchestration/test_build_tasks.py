import asyncio
import logging
import threading
import time
from collections.abc import Callable

import pytest

from bunsho.config.settings import AppConfig
from bunsho.context import Context
from bunsho.orchestration.build_tasks import (
    BuildAlreadyRunningError,
    BuildEvent,
    BuildState,
    BuildTaskManager,
)
from bunsho.orchestration.content_build import BuildProgress, ContentBuildError
from tests.base import StubOrchestrator as _Stub


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
        # the first item, then every 30th of 3000 (30, 60, ..., 3000): about one per percent
        assert len(enrich) == 1 + 3000 // 30
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


async def _until(condition: Callable[[], bool], timeout: float = 5.0) -> None:
    """Yield to the event loop until ``condition`` holds (fails the test on timeout)."""
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "condition was never met"
        await asyncio.sleep(0.005)


def test_cancelling_the_runner_keeps_the_build_active_until_the_worker_ends(
    app_config: AppConfig,
    quiet_logger,  # type: ignore[no-untyped-def]
) -> None:
    async def scenario() -> None:
        gate = threading.Event()
        _ctx, manager = _manager(app_config, quiet_logger, _Stub(gate=gate))
        queue = manager.subscribe()
        task = manager.start(dry_run=True)
        await _until(lambda: task.progress == BuildProgress("enrich_kanji", 3, 3))
        runner = manager._runner  # noqa: SLF001 - simulate a shutdown-style cancellation
        assert runner is not None
        runner.cancel()
        await asyncio.sleep(0.05)
        assert manager.active is task  # the worker thread is still alive
        with pytest.raises(BuildAlreadyRunningError):
            manager.start(dry_run=True)
        gate.set()
        await manager.join()
        assert task.state is BuildState.FAILED
        assert "Cancelled" in (task.error or "")
        assert task.finished_at is not None
        assert manager.active is None
        final = _drain(queue)[-1]
        assert (final.kind, final.state) == ("state", BuildState.FAILED)
        assert final.error == task.error
        assert manager.start(dry_run=True) is not task
        await manager.join()

    asyncio.run(scenario())


def test_progress_arriving_after_the_task_ended_is_ignored(
    app_config: AppConfig,
    quiet_logger,  # type: ignore[no-untyped-def]
) -> None:
    class LateProgressStub(_Stub):
        def build(self, deck_path, target, *, dry_run=False, on_progress=None):  # type: ignore[no-untyped-def]
            report = super().build(deck_path, target, dry_run=dry_run, on_progress=on_progress)
            assert on_progress is not None
            on_progress(BuildProgress("late", 1, 1))
            return report

    async def scenario() -> None:
        gate = threading.Event()
        _ctx, manager = _manager(app_config, quiet_logger, LateProgressStub(gate=gate))
        queue = manager.subscribe()
        task = manager.start(dry_run=True)
        await _until(lambda: task.progress == BuildProgress("enrich_kanji", 3, 3))
        runner = manager._runner  # noqa: SLF001 - simulate a shutdown-style cancellation
        assert runner is not None
        runner.cancel()
        await asyncio.sleep(0.05)
        gate.set()
        await manager.join()
        await asyncio.sleep(0.05)  # let any late call_soon_threadsafe callback run
        assert task.state is BuildState.FAILED
        assert task.progress == BuildProgress("enrich_kanji", 3, 3)
        events = _drain(queue)
        assert all(e.progress is None or e.progress.stage != "late" for e in events)
        assert (events[-1].kind, events[-1].state) == ("state", BuildState.FAILED)

    asyncio.run(scenario())


def test_a_refresh_failure_after_a_successful_build_fails_the_task(
    app_config: AppConfig,
    quiet_logger,  # type: ignore[no-untyped-def]
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_refresh(self: Context) -> None:
        raise OSError("content.db is locked")

    monkeypatch.setattr(Context, "refresh_content_repo", broken_refresh)
    caplog.set_level(logging.DEBUG, logger=quiet_logger.name)

    async def scenario() -> None:
        _ctx, manager = _manager(app_config, quiet_logger, _Stub())
        task = manager.start(dry_run=False)
        await manager.join()
        assert task.state is BuildState.FAILED
        assert task.error == "OSError: content.db is locked"
        assert task.report is not None

    asyncio.run(scenario())
    assert "content_repo_refresh_failed" in caplog.text


def test_a_subscriber_joining_mid_build_only_gets_later_events(
    app_config: AppConfig,
    quiet_logger,  # type: ignore[no-untyped-def]
) -> None:
    async def scenario() -> None:
        gate = threading.Event()
        _ctx, manager = _manager(app_config, quiet_logger, _Stub(gate=gate))
        task = manager.start(dry_run=False)
        await _until(lambda: task.progress == BuildProgress("enrich_kanji", 3, 3))
        queue = manager.subscribe()
        gate.set()
        await manager.join()
        events = _drain(queue)
        stages = [e.progress.stage for e in events if e.progress is not None]
        assert stages == ["write", "write"]
        assert (events[-1].kind, events[-1].state) == ("state", BuildState.SUCCEEDED)

    asyncio.run(scenario())


def test_a_failing_progress_callback_does_not_abort_the_build(
    app_config: AppConfig,
    quiet_logger,  # type: ignore[no-untyped-def]
    caplog: pytest.LogCaptureFixture,
) -> None:
    class BadProgressStub(_Stub):
        def build(self, deck_path, target, *, dry_run=False, on_progress=None):  # type: ignore[no-untyped-def]
            assert on_progress is not None
            on_progress(BuildProgress("bad", 1, "oops"))  # type: ignore[arg-type]
            return super().build(deck_path, target, dry_run=dry_run, on_progress=on_progress)

    caplog.set_level(logging.DEBUG, logger=quiet_logger.name)

    async def scenario() -> None:
        _ctx, manager = _manager(app_config, quiet_logger, BadProgressStub())
        task = manager.start(dry_run=True)
        await manager.join()
        assert task.state is BuildState.SUCCEEDED
        assert task.report is not None

    asyncio.run(scenario())
    assert "build_progress_callback_failed" in caplog.text
