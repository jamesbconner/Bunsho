import asyncio
import logging
import sqlite3
from pathlib import Path

import pytest

from bunsho.context import Context
from bunsho.models.review import ContentNotReadyError
from bunsho.services.content_access import ContentGate
from tests.base import make_service_config, make_vocab, write_content


def _ctx(tmp_path: Path, repo) -> Context:  # type: ignore[no-untyped-def]
    return Context(
        config=make_service_config(tmp_path).app,
        logger=logging.getLogger("bunsho.tests.gate"),
        content_repo=repo,
    )


def test_missing_content_is_not_ready(tmp_path: Path) -> None:
    with pytest.raises(ContentNotReadyError, match="not been built"):
        asyncio.run(ContentGate(_ctx(tmp_path, None)).repository())


def test_a_schema_mismatch_is_not_ready(tmp_path: Path) -> None:
    repo = write_content(tmp_path / "c.db", schema_version="1")
    with pytest.raises(ContentNotReadyError, match="schema_version"):
        asyncio.run(ContentGate(_ctx(tmp_path, repo)).repository())


def test_usable_content_is_returned_and_verified_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = write_content(tmp_path / "c.db", vocab=[make_vocab()])
    calls: list[int] = []
    original = repo.verify_schema
    monkeypatch.setattr(repo, "verify_schema", lambda: (calls.append(1), original())[1])
    gate = ContentGate(_ctx(tmp_path, repo))

    async def scenario() -> None:
        assert await gate.repository() is repo
        assert await gate.repository() is repo

    asyncio.run(scenario())
    assert calls == [1]


def test_a_rebuilt_repository_is_verified_again(tmp_path: Path) -> None:
    first = write_content(tmp_path / "a.db")
    ctx = _ctx(tmp_path, first)
    gate = ContentGate(ctx)

    async def scenario() -> None:
        assert await gate.repository() is first
        ctx.content_repo = write_content(tmp_path / "b.db", schema_version="1")
        with pytest.raises(ContentNotReadyError):
            await gate.repository()

    asyncio.run(scenario())


def test_an_unreadable_database_is_not_ready_and_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    repo = write_content(tmp_path / "c.db")

    def broken() -> None:
        raise sqlite3.DatabaseError("file is not a database")

    monkeypatch.setattr(repo, "verify_schema", broken)
    with (
        caplog.at_level(logging.WARNING, logger="bunsho.tests.gate"),
        pytest.raises(ContentNotReadyError, match="cannot be read"),
    ):
        asyncio.run(ContentGate(_ctx(tmp_path, repo)).repository())
    assert "content_unreadable" in caplog.text
