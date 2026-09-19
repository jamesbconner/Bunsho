"""Typed application configuration and validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from bunsho.config.normalizer import ConfigError, ConfigNormalizer

DEFAULT_DECK_FILENAME = "JLPT_N5_to_N1_Japanese_Vocabulary.apkg"
DEFAULT_DECK_SHA256 = "fe5cf438a8f0f6690af00b2c2a9c61da9390feb5bd6d663ea8e6b225b17c3b4a"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Validated runtime configuration."""

    data_dir: Path
    resources_dir: Path
    deck_filename: str
    deck_sha256: str
    jamdict_db: Path | None
    log_level: str

    @property
    def content_db_path(self) -> Path:
        """Location of the rebuildable ``content.db``."""
        return self.data_dir / "content.db"

    @property
    def progress_db_path(self) -> Path:
        """Location of the irreplaceable ``progress.db``."""
        return self.data_dir / "progress.db"

    @property
    def deck_path(self) -> Path:
        """Location of the pinned vocabulary deck."""
        return self.resources_dir / self.deck_filename

    @classmethod
    def from_normalizer(cls, cfg: ConfigNormalizer) -> AppConfig:
        """Build from an already-validated normalizer (see ``validate_config``)."""
        jamdict = cfg.get_string("paths", "jamdict_db")
        return cls(
            data_dir=Path(cfg.get_string("paths", "data_dir", "data")),
            resources_dir=Path(cfg.get_string("paths", "resources_dir", "resources")),
            deck_filename=cfg.get_string("paths", "deck_filename", DEFAULT_DECK_FILENAME),
            deck_sha256=cfg.get_string("paths", "deck_sha256", DEFAULT_DECK_SHA256).lower(),
            jamdict_db=Path(jamdict) if jamdict else None,
            log_level=cfg.get_string("logging", "level", "INFO").upper(),
        )


def validate_config(cfg: ConfigNormalizer) -> list[str]:
    """Check configuration and return every problem found (empty list means valid)."""
    errors: list[str] = []
    level = cfg.get_string("logging", "level", "INFO").upper()
    if level not in _LOG_LEVELS:
        errors.append(f"[logging] level={level!r} must be one of {sorted(_LOG_LEVELS)}")
    sha = cfg.get_string("paths", "deck_sha256", DEFAULT_DECK_SHA256).lower()
    if not _SHA256.fullmatch(sha):
        errors.append("[paths] deck_sha256 must be 64 lowercase hex characters")
    name = cfg.get_string("paths", "deck_filename", DEFAULT_DECK_FILENAME)
    if not name or name in {".", ".."} or Path(name).name != name:
        errors.append("[paths] deck_filename must be a bare file name without directories")
    jamdict = cfg.get_string("paths", "jamdict_db")
    if jamdict and not Path(jamdict).is_file():
        errors.append(
            f"[paths] jamdict_db={jamdict!r} does not exist; "
            "unset it to use the database from the jamdict-data-fix package"
        )
    return errors


def load_app_config(cfg: ConfigNormalizer) -> AppConfig:
    """Validate ``cfg`` and build an ``AppConfig``.

    Raises:
        ConfigError: Listing every validation failure at once.
    """
    errors = validate_config(cfg)
    if errors:
        raise ConfigError("Invalid configuration:\n  - " + "\n  - ".join(errors))
    return AppConfig.from_normalizer(cfg)
