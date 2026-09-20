import dataclasses
from pathlib import Path

from bunsho.context import Context
from bunsho.services.config_check import run_config_checks
from tests.apkg_builder import build_apkg, note
from tests.base import FakeKanjiSource, make_service_config


def _results(tmp_path: Path, quiet_logger, *, deck_sha: str | None = None, jamdict=True):  # type: ignore[no-untyped-def]
    config = make_service_config(tmp_path)
    if deck_sha is not None:
        config = dataclasses.replace(
            config, app=dataclasses.replace(config.app, deck_sha256=deck_sha)
        )
    ctx = Context(
        config=config.app,
        logger=quiet_logger,
        kanji_source=FakeKanjiSource() if jamdict else None,  # type: ignore[arg-type]
    )
    return config, {r.name: r for r in run_config_checks(config, ctx)}


def test_missing_deck_fails_both_deck_checks(tmp_path: Path, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    _config, results = _results(tmp_path, quiet_logger)
    assert not results["deck_present"].ok
    assert not results["deck_checksum"].ok


def test_deck_with_the_wrong_checksum(tmp_path: Path, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    config = make_service_config(tmp_path)
    (tmp_path / "resources").mkdir()
    build_apkg(config.app.deck_path, [note("日", "にち")])
    _config, results = _results(tmp_path, quiet_logger)
    assert results["deck_present"].ok
    assert not results["deck_checksum"].ok


def test_deck_with_the_pinned_checksum(tmp_path: Path, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    config = make_service_config(tmp_path)
    (tmp_path / "resources").mkdir()
    sha = build_apkg(config.app.deck_path, [note("日", "にち")])
    _config, results = _results(tmp_path, quiet_logger, deck_sha=sha)
    assert results["deck_checksum"].ok


def test_data_dir_and_jamdict_checks(tmp_path: Path, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    _config, results = _results(tmp_path, quiet_logger)
    assert results["data_dir_writable"].ok
    assert results["jamdict_available"].ok
    _config, results = _results(tmp_path, quiet_logger, jamdict=False)
    assert not results["jamdict_available"].ok


def test_data_dir_that_is_a_file_is_not_writable(tmp_path: Path, quiet_logger) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "data").write_text("in the way")
    _config, results = _results(tmp_path, quiet_logger)
    assert not results["data_dir_writable"].ok
