import asyncio

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


def test_progress_db_failure_is_an_error(app_config: AppConfig, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    report = _check(_Db(OSError("disk gone")), _ctx(app_config, quiet_logger))
    assert report.status == "error"
    assert report.components["progress_db"].status == "error"
    assert "disk gone" in report.components["progress_db"].detail
