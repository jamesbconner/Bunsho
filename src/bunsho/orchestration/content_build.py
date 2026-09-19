"""Build ``content.db`` from the vocabulary deck, kana tables and jamdict."""

from __future__ import annotations

import logging
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from bunsho.models.content import JlptLevel, Kanji, KanjiDetails, kanji_id
from bunsho.services.content_repository import CONTENT_SCHEMA_VERSION
from bunsho.services.kanji_levels import derive_kanji_levels
from bunsho.services.protocols import ContentWriting, DeckImporter, KanaProvider, KanjiInfoSource

_NO_FREQUENCY = 10**9


class ContentBuildError(RuntimeError):
    """The content build cannot run (for example a required service is unavailable)."""


@dataclass(frozen=True, slots=True)
class BuildProgress:
    """One progress notification."""

    stage: str
    current: int
    total: int


ProgressCallback = Callable[[BuildProgress], None]


@dataclass(frozen=True, slots=True)
class BuildReport:
    """Summary of a build (or a dry run)."""

    dry_run: bool
    target: Path
    deck_sha256: str
    kana_count: int
    kanji_count: int
    vocab_count: int
    sentence_count: int
    vocab_by_level: dict[str, int]
    kanji_by_level: dict[str, int]
    kanji_without_details: int
    duration_seconds: float


def _ignore(_: BuildProgress) -> None:
    return None


def _by_level(levels: list[JlptLevel]) -> dict[str, int]:
    counts = Counter(levels)
    return {level.label: counts[level] for level in JlptLevel.study_order() if counts[level]}


class ContentBuildOrchestrator:
    """Coordinates deck import, kanji derivation, dictionary enrichment and persistence."""

    def __init__(
        self,
        importer: DeckImporter,
        kana_provider: KanaProvider,
        kanji_source: KanjiInfoSource,
        writer: ContentWriting,
        logger: logging.Logger,
    ) -> None:
        """Wire the collaborators (all behind Protocols)."""
        self._importer = importer
        self._kana = kana_provider
        self._kanji_source = kanji_source
        self._writer = writer
        self._logger = logger

    def build(
        self,
        deck_path: Path,
        target: Path,
        *,
        dry_run: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> BuildReport:
        """Run the full build.

        Args:
            deck_path: The pinned vocabulary ``.apkg``.
            target: Where ``content.db`` should be written.
            dry_run: Validate and plan only; write nothing.
            on_progress: Optional callback invoked after each step. It must not raise: an
                exception from the callback propagates and aborts the build, so callers
                (for example a WebSocket sender) must guard it.

        Returns:
            A report of what was (or would be) written.

        Raises:
            DeckImportError: The deck is missing, altered or malformed.
            sqlite3.Error: Writing failed; any existing ``target`` is left untouched.
        """
        started = time.perf_counter()
        notify = on_progress or _ignore
        notify(BuildProgress("import_deck", 0, 1))
        deck = self._importer.import_vocab(deck_path)
        notify(BuildProgress("import_deck", 1, 1))

        kanji, without_details = self._build_kanji(derive_kanji_levels(deck.vocab), notify)
        kana = self._kana.all_kana()
        sentence_count = sum(1 for item in deck.vocab if item.sentence is not None)

        if dry_run:
            self._logger.info(
                "content_build dry_run=true target=%s kana=%d kanji=%d vocab=%d",
                target,
                len(kana),
                len(kanji),
                len(deck.vocab),
            )
        else:
            meta = {
                "schema_version": CONTENT_SCHEMA_VERSION,
                "built_at": datetime.now(UTC).isoformat(),
                "deck_sha256": deck.sha256,
                "deck_filename": deck_path.name,
                "kana": str(len(kana)),
                "kanji": str(len(kanji)),
                "vocab": str(len(deck.vocab)),
            }
            notify(BuildProgress("write", 0, 1))
            self._writer.write(target, kana=kana, kanji=kanji, vocab=deck.vocab, meta=meta)
            notify(BuildProgress("write", 1, 1))
            self._logger.info(
                "content_build dry_run=false target=%s kana=%d kanji=%d vocab=%d",
                target,
                len(kana),
                len(kanji),
                len(deck.vocab),
            )
        return BuildReport(
            dry_run=dry_run,
            target=target,
            deck_sha256=deck.sha256,
            kana_count=len(kana),
            kanji_count=len(kanji),
            vocab_count=len(deck.vocab),
            sentence_count=sentence_count,
            vocab_by_level=_by_level([item.level for item in deck.vocab]),
            kanji_by_level=_by_level([k.level for k in kanji if k.level is not None]),
            kanji_without_details=without_details,
            duration_seconds=time.perf_counter() - started,
        )

    def _build_kanji(
        self, levels: dict[str, JlptLevel], notify: ProgressCallback
    ) -> tuple[list[Kanji], int]:
        ordered = sorted(levels.items(), key=lambda item: (-int(item[1]), item[0]))
        total = len(ordered)
        built: list[Kanji] = []
        without_details = 0
        for index, (char, level) in enumerate(ordered, start=1):
            details = self._kanji_source.get_kanji(char)
            if details is None:
                without_details += 1
                details = KanjiDetails()
            built.append(
                Kanji.model_validate(
                    {"id": kanji_id(char), "char": char, "level": level, **details.model_dump()}
                )
            )
            notify(BuildProgress("enrich_kanji", index, total))
        if without_details:
            self._logger.warning("kanji_without_details count=%d", without_details)
        built.sort(
            key=lambda k: (
                -int(k.level or 0),
                k.frequency if k.frequency is not None else _NO_FREQUENCY,
                k.char,
            )
        )
        return built, without_details
