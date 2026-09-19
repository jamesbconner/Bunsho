"""Shared test builders and fixtures for Bunshō."""

from __future__ import annotations

import logging
import threading
from dataclasses import replace
from functools import cache
from pathlib import Path

import pytest
from pwdlib import PasswordHash

from bunsho.config.service import (
    MIN_JWT_SECRET_LENGTH,
    AuthSettings,
    ServerSettings,
    ServiceConfig,
)
from bunsho.config.settings import DEFAULT_DECK_FILENAME, DEFAULT_DECK_SHA256, AppConfig
from bunsho.models.content import (
    JlptLevel,
    KanjiDetails,
    RubySegment,
    Sentence,
    Vocab,
    vocab_id,
)
from bunsho.orchestration.content_build import BuildProgress, BuildReport
from bunsho.services.content_repository import ContentWriter

PASSWORD = "correct horse battery staple"
JWT_SECRET = "s" * (MIN_JWT_SECRET_LENGTH + 8)


@cache
def _password_hash() -> str:
    return PasswordHash.recommended().hash(PASSWORD)


def make_auth_settings(**overrides: object) -> AuthSettings:
    """Build ``AuthSettings`` for user ``james`` with a cached argon2 hash of ``PASSWORD``."""
    base = AuthSettings(
        username="james",
        password_hash=_password_hash(),
        jwt_secret=JWT_SECRET,
        access_ttl_minutes=15,
        refresh_ttl_days=30,
    )
    return replace(base, **overrides)  # type: ignore[arg-type]


def make_vocab(
    expression: str = "日本",
    reading: str = "にほん",
    level: JlptLevel = JlptLevel.N5,
    *,
    tags: tuple[str, ...] = (),
    sentence: Sentence | None = None,
) -> Vocab:
    """Build a ``Vocab`` with sensible defaults for tests."""
    return Vocab(
        id=vocab_id(expression, reading),
        expression=expression,
        reading=reading,
        reading_segments=(RubySegment(base=expression, reading=reading),),
        meaning="test meaning",
        part_of_speech=("noun",),
        tags=tags,
        level=level,
        sentence=sentence,
    )


def make_kanji_details(**overrides: object) -> KanjiDetails:
    """Build ``KanjiDetails`` with defaults, overriding any field by keyword."""
    values: dict[str, object] = {
        "meanings": ("day",),
        "on_readings": ("ニチ",),
        "kun_readings": ("ひ",),
        "stroke_count": 4,
        "grade": 1,
        "frequency": 1,
        "radical": 72,
    }
    values.update(overrides)
    return KanjiDetails.model_validate(values)


class FakeKanjiSource:
    """In-memory kanji source for unit tests (duck-types ``KanjiInfoSource``)."""

    def __init__(self, details: dict[str, KanjiDetails] | None = None) -> None:
        self.details = details or {}
        self.calls: list[str] = []

    def get_kanji(self, char: str) -> KanjiDetails | None:
        """Return canned details, recording each lookup."""
        self.calls.append(char)
        return self.details.get(char)


class FakeKanjiCatalog:
    """In-memory kanji catalog for unit tests (duck-types ``KanjiCatalog``)."""

    def __init__(self, literals: list[str] | None = None) -> None:
        self.literals = literals or []

    def graded_kanji(self) -> list[str]:
        """Return the canned literals."""
        return list(self.literals)


@pytest.fixture
def app_config(tmp_path: Path) -> AppConfig:
    """An ``AppConfig`` rooted in a temporary directory."""
    return AppConfig(
        data_dir=tmp_path / "data",
        resources_dir=tmp_path / "resources",
        deck_filename=DEFAULT_DECK_FILENAME,
        deck_sha256=DEFAULT_DECK_SHA256,
        jamdict_db=None,
        log_level="INFO",
    )


@pytest.fixture
def quiet_logger() -> logging.Logger:
    """A logger that stays out of test output."""
    logger = logging.getLogger("bunsho.tests")
    logger.setLevel(logging.CRITICAL)
    return logger


def make_service_config(
    tmp_path: Path, *, cors_origins: tuple[str, ...] = (), **auth_overrides: object
) -> ServiceConfig:
    """A ``ServiceConfig`` rooted in ``tmp_path`` for user ``james``.

    Extra keyword arguments override ``make_auth_settings`` fields.
    """
    app = AppConfig(
        data_dir=tmp_path / "data",
        resources_dir=tmp_path / "resources",
        deck_filename=DEFAULT_DECK_FILENAME,
        deck_sha256=DEFAULT_DECK_SHA256,
        jamdict_db=None,
        log_level="INFO",
    )
    return ServiceConfig(
        app=app,
        server=ServerSettings(host="127.0.0.1", port=8192, cors_origins=cors_origins),
        auth=make_auth_settings(**auth_overrides),
    )


@pytest.fixture
def service_config(tmp_path: Path) -> ServiceConfig:
    """A default ``ServiceConfig`` rooted in a temporary directory."""
    return make_service_config(tmp_path)


def make_build_report(dry_run: bool) -> BuildReport:
    """A small ``BuildReport`` for tests."""
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


class StubOrchestrator:
    """Fake content build orchestrator: emits progress, optionally blocks, fails or writes."""

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
        """Pretend to build; see the class docstring."""
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
        return make_build_report(dry_run)
