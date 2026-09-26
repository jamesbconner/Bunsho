from pathlib import Path

import pytest

from bunsho.config.normalizer import ConfigError, ConfigNormalizer
from bunsho.config.settings import (
    DEFAULT_DECK_FILENAME,
    DEFAULT_DECK_SHA256,
    load_app_config,
    validate_config,
)


def test_defaults_are_valid() -> None:
    config = load_app_config(ConfigNormalizer())
    assert config.deck_filename == DEFAULT_DECK_FILENAME
    assert config.deck_sha256 == DEFAULT_DECK_SHA256
    assert config.jamdict_db is None
    assert config.log_level == "INFO"
    assert config.content_db_path == Path("data") / "content.db"
    assert config.progress_db_path == Path("data") / "progress.db"
    assert config.deck_path == Path("resources") / DEFAULT_DECK_FILENAME


def test_all_validation_errors_are_reported_together(tmp_path: Path) -> None:
    cfg = ConfigNormalizer(
        {
            "logging": {"level": "loud"},
            "paths": {
                "deck_sha256": "abc",
                "deck_filename": "../evil.apkg",
                "jamdict_db": str(tmp_path / "missing.db"),
            },
        }
    )
    errors = validate_config(cfg)
    assert len(errors) == 4
    with pytest.raises(ConfigError) as info:
        load_app_config(cfg)
    assert str(info.value).count("\n  - ") == 4


@pytest.mark.parametrize(
    "name", ["", ".", "..", "a/b.apkg", "a\\b.apkg", "C:evil.apkg", "/abs.apkg"]
)
def test_deck_filename_must_be_bare(name: str) -> None:
    assert validate_config(ConfigNormalizer({"paths": {"deck_filename": name}}))


def test_existing_jamdict_db_is_accepted(tmp_path: Path) -> None:
    db = tmp_path / "jamdict.db"
    db.write_bytes(b"")
    config = load_app_config(ConfigNormalizer({"paths": {"jamdict_db": str(db)}}))
    assert config.jamdict_db == db


def test_data_dir_must_not_be_a_file(tmp_path: Path) -> None:
    blocker = tmp_path / "data"
    blocker.write_text("not a directory")
    errors = validate_config(ConfigNormalizer({"paths": {"data_dir": str(blocker)}}))
    assert any("data_dir" in e for e in errors)


def test_frontend_dir_is_unset_by_default() -> None:
    assert load_app_config(ConfigNormalizer()).frontend_dir is None


def test_frontend_dir_is_read_from_the_paths_section(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    config = load_app_config(ConfigNormalizer({"paths": {"frontend_dir": str(dist)}}))
    assert config.frontend_dir == dist


def test_frontend_dir_must_be_a_directory(tmp_path: Path) -> None:
    errors = validate_config(ConfigNormalizer({"paths": {"frontend_dir": str(tmp_path / "nope")}}))
    assert any("frontend_dir" in error and "not a directory" in error for error in errors)


def test_a_frontend_build_without_the_nonce_placeholder_is_reported(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>old build</body></html>", encoding="utf-8")
    errors = validate_config(ConfigNormalizer({"paths": {"frontend_dir": str(dist)}}))
    assert any("frontend_dir" in e and "npm run build" in e for e in errors)


def test_a_current_frontend_build_is_accepted(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text('<meta content="__CSP_NONCE__">', encoding="utf-8")
    errors = validate_config(ConfigNormalizer({"paths": {"frontend_dir": str(dist)}}))
    assert not any("frontend_dir" in e for e in errors)


def test_a_frontend_folder_without_an_index_is_not_reported(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()  # the existing behaviour: only "is a directory" is checked
    errors = validate_config(ConfigNormalizer({"paths": {"frontend_dir": str(dist)}}))
    assert not any("frontend_dir" in e for e in errors)
