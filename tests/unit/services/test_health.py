import asyncio
import logging

import pytest

from bunsho.config.settings import AppConfig
from bunsho.context import Context
from bunsho.services.content_repository import CONTENT_SCHEMA_VERSION, ContentWriter
from bunsho.services.health import HealthService
from tests.base import FakeKanjiSource


class _Db:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    async def ping(self) -> None:
        if self.error is not None:
            raise self.error


def _ctx(app_config: AppConfig, quiet_logger, *, meta=None, jamdict=True) -> Context:  # type: ignore[no-untyped-def]
    ctx = Context(
        config=app_config,
        logger=quiet_logger,
        kanji_source=FakeKanjiSource() if jamdict else None,  # type: ignore[arg-type]
    )
    if meta is not None:
        ContentWriter().write(app_config.content_db_path, kana=[], kanji=[], vocab=[], meta=meta)
        ctx.refresh_content_repo()
    return ctx


def _check(db: _Db, ctx: Context):  # type: ignore[no-untyped-def]
    return asyncio.run(HealthService(db, ctx).check())  # type: ignore[arg-type]


def test_everything_ok(app_config: AppConfig, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    ctx = _ctx(app_config, quiet_logger, meta={"schema_version": CONTENT_SCHEMA_VERSION})
    report = _check(_Db(), ctx)
    assert report.status == "ok"
    assert {name: c.status for name, c in report.components.items()} == {
        "progress_db": "ok",
        "content_db": "ok",
        "jamdict": "ok",
    }
    assert report.components["progress_db"].latency_ms >= 0


def test_content_not_built_is_degraded(app_config: AppConfig, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    report = _check(_Db(), _ctx(app_config, quiet_logger))
    assert report.status == "degraded"
    assert report.components["content_db"].status == "degraded"
    assert "not built" in report.components["content_db"].detail


def test_content_schema_mismatch_is_degraded_with_a_rebuild_hint(
    app_config: AppConfig, quiet_logger
) -> None:  # type: ignore[no-untyped-def]
    report = _check(_Db(), _ctx(app_config, quiet_logger, meta={"schema_version": "0"}))
    assert report.components["content_db"].status == "degraded"
    assert "rebuild" in report.components["content_db"].detail


def test_missing_jamdict_is_degraded(app_config: AppConfig, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    ctx = _ctx(
        app_config, quiet_logger, meta={"schema_version": CONTENT_SCHEMA_VERSION}, jamdict=False
    )
    report = _check(_Db(), ctx)
    assert report.status == "degraded"
    assert report.components["jamdict"].status == "degraded"


def test_progress_db_failure_is_an_error_without_leaking_details(
    app_config: AppConfig,
    quiet_logger,  # type: ignore[no-untyped-def]
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = f"disk gone at {app_config.data_dir}"
    with caplog.at_level(logging.WARNING, logger=quiet_logger.name):
        report = _check(_Db(OSError(secret)), _ctx(app_config, quiet_logger))
    assert report.status == "error"
    component = report.components["progress_db"]
    assert component.status == "error"
    assert component.detail == "OSError"
    assert secret not in component.detail
    logged = [r.getMessage() for r in caplog.records]
    assert any("progress_db" in m and secret in m for m in logged)


def test_unreadable_content_db_is_degraded_without_leaking_details(
    app_config: AppConfig,
    quiet_logger,  # type: ignore[no-untyped-def]
    caplog: pytest.LogCaptureFixture,
) -> None:
    app_config.data_dir.mkdir(parents=True)
    app_config.content_db_path.write_bytes(b"definitely not sqlite" * 20)
    ctx = _ctx(app_config, quiet_logger)
    ctx.refresh_content_repo()
    with caplog.at_level(logging.WARNING, logger=quiet_logger.name):
        report = _check(_Db(), ctx)
    component = report.components["content_db"]
    assert component.status == "degraded"
    assert component.detail == "DatabaseError"
    assert str(app_config.content_db_path) not in component.detail
    logged = [r.getMessage() for r in caplog.records]
    assert any("content_db" in m and "not a database" in m for m in logged)


def test_unexpected_content_db_error_is_degraded_not_raised(
    app_config: AppConfig,
    quiet_logger,  # type: ignore[no-untyped-def]
) -> None:
    class _Repo:
        def verify_schema(self) -> None:
            raise ValueError("odd")

    ctx = _ctx(app_config, quiet_logger)
    ctx.content_repo = _Repo()  # type: ignore[assignment]
    component = _check(_Db(), ctx).components["content_db"]
    assert component.status == "degraded"
    assert component.detail == "ValueError"
