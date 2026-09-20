"""Shared fixtures and the CI skip policy for the whole test suite."""

import os
from collections.abc import Generator
from typing import Any

import pytest

from tests.base import app_config, quiet_logger, service_config

__all__ = ["app_config", "pytest_runtest_makereport", "quiet_logger", "service_config"]


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, Any]:
    """Turn a skipped ``integration`` test into a failure when ``CI`` is set.

    Integration tests skip when the real deck or the jamdict database is missing, which is
    right on a laptop and wrong in CI, where a skipped suite would look green. Setup skips
    (fixtures, ``skipif`` markers) and call skips are both covered; expected failures
    (``xfail``, which also report as skipped) and non-integration tests are left alone.
    """
    outcome = yield
    report = outcome.get_result()
    if (
        report.skipped
        and not hasattr(report, "wasxfail")
        and os.environ.get("CI")
        and item.get_closest_marker("integration") is not None
        and call.when in {"setup", "call"}
    ):
        reason = report.longrepr[2] if isinstance(report.longrepr, tuple) else str(report.longrepr)
        report.outcome = "failed"
        report.longrepr = (
            f"integration test skipped under CI (its inputs must exist there): {reason}"
        )
