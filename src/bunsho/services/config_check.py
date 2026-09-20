"""Environment suitability checks (what a config-check endpoint reports)."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass

from bunsho.config.service import ServiceConfig
from bunsho.context import Context
from bunsho.services.anki_importer import sha256_of


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Outcome of one check."""

    name: str
    ok: bool
    detail: str


def run_config_checks(config: ServiceConfig, ctx: Context) -> list[CheckResult]:
    """Check the deck, its checksum, the data directory and jamdict.

    Args:
        config: The loaded service configuration.
        ctx: The application context (for the jamdict handle).

    Returns:
        One result per check, in a stable order.
    """
    deck = config.app.deck_path
    present = deck.is_file()
    results = [CheckResult("deck_present", present, str(deck) if present else f"missing: {deck}")]
    if present:
        actual = sha256_of(deck)
        matches = actual == config.app.deck_sha256
        detail = (
            "checksum matches" if matches else f"expected {config.app.deck_sha256}, got {actual}"
        )
        results.append(CheckResult("deck_checksum", matches, detail))
    else:
        results.append(CheckResult("deck_checksum", False, "deck file missing"))
    try:
        config.app.data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=config.app.data_dir):
            pass
        results.append(CheckResult("data_dir_writable", True, str(config.app.data_dir)))
    except OSError as exc:
        results.append(CheckResult("data_dir_writable", False, f"{config.app.data_dir}: {exc}"))
    jamdict_ok = ctx.kanji_source is not None
    results.append(
        CheckResult(
            "jamdict_available",
            jamdict_ok,
            "ready" if jamdict_ok else "jamdict database unavailable; builds are disabled",
        )
    )
    return results
