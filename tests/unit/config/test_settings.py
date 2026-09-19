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


@pytest.mark.parametrize("name", ["", ".", "..", "a/b.apkg", "a\\b.apkg"])
def test_deck_filename_must_be_bare(name: str) -> None:
    assert validate_config(ConfigNormalizer({"paths": {"deck_filename": name}}))


def test_existing_jamdict_db_is_accepted(tmp_path: Path) -> None:
    db = tmp_path / "jamdict.db"
    db.write_bytes(b"")
    config = load_app_config(ConfigNormalizer({"paths": {"jamdict_db": str(db)}}))
    assert config.jamdict_db == db
