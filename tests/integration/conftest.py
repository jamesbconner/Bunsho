"""Fixtures for tests that run against the real deck and the real jamdict database."""

from pathlib import Path

import pytest

from bunsho.config.settings import DEFAULT_DECK_FILENAME, DEFAULT_DECK_SHA256, AppConfig
from bunsho.factories import create_content_build_orchestrator, create_context
from bunsho.orchestration.content_build import BuildReport
from bunsho.services.content_repository import ContentRepository

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def real_content(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[BuildReport, ContentRepository]:
    """Build ``content.db`` once per test session from the pinned deck and jamdict-data-fix."""
    config = AppConfig(
        data_dir=tmp_path_factory.mktemp("data"),
        resources_dir=REPO_ROOT / "resources",
        deck_filename=DEFAULT_DECK_FILENAME,
        deck_sha256=DEFAULT_DECK_SHA256,
        jamdict_db=None,
        log_level="INFO",
    )
    if not config.deck_path.is_file():
        pytest.skip(f"deck not present: {config.deck_path}")
    ctx = create_context(config)
    if ctx.kanji_source is None:
        pytest.skip("jamdict-data-fix database unavailable")
    report = create_content_build_orchestrator(ctx).build(config.deck_path, config.content_db_path)
    return report, ContentRepository(config.content_db_path)
