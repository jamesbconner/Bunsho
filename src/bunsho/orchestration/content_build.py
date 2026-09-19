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
from bunsho.services.protocols import (
    ContentWriting,
    DeckImporter,
    KanaProvider,
    KanjiCatalog,
    KanjiInfoSource,
)

_NO_FREQUENCY = 10**9
_NO_GRADE = 99


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
    """Summary of a build (or a dry run).

    ``kanji_count`` is every stored kanji row (leveled and unleveled), while
    ``kanji_by_level`` counts only the leveled ones; ``unleveled_kanji_count`` is the rest.
    """

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
    unleveled_kanji_count: int = 0


def _ignore(_: BuildProgress) -> None:
    return None


@dataclass(frozen=True, slots=True)
class _KanjiBuild:
    """Kanji rows in study order plus the counters the report needs."""

    kanji: list[Kanji]
    unleveled_count: int
    without_details: int


def _study_key(kanji: Kanji) -> tuple[int, int, int, str]:
    """Sort key: leveled kanji (hardest level last) before unleveled (by grade)."""
    frequency = kanji.frequency if kanji.frequency is not None else _NO_FREQUENCY
    if kanji.level is None:
        grade = kanji.grade if kanji.grade is not None else _NO_GRADE
        return (1, grade, frequency, kanji.char)
    return (0, -int(kanji.level), frequency, kanji.char)


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
        *,
        kanji_catalog: KanjiCatalog | None = None,
    ) -> None:
        """Wire the collaborators (all behind Protocols).

        Args:
            importer: Reads the vocabulary deck.
            kana_provider: Supplies the kana study set.
            kanji_source: Looks up dictionary facts about each kanji.
            writer: Persists the finished build.
            logger: Logger for build events.
            kanji_catalog: When given, graded kanji that the deck does not use are stored
                too, as unleveled rows. ``None`` stores deck kanji only.
        """
        self._importer = importer
        self._kana = kana_provider
        self._kanji_source = kanji_source
        self._writer = writer
        self._logger = logger
        self._catalog = kanji_catalog

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
            dry_run: Validate and plan only; write nothing. The dictionary is still queried
                for every kanji (including unleveled candidates, roughly 10 ms each), so a
                dry run takes about as long as a real build.
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

        built = self._build_kanji(derive_kanji_levels(deck.vocab), notify)
        kanji = built.kanji
        kana = self._kana.all_kana()
        sentence_count = sum(1 for item in deck.vocab if item.sentence is not None)

        if dry_run:
            self._logger.info(
                "content_build dry_run=true target=%s kana=%d kanji=%d unleveled_kanji=%d vocab=%d",
                target,
                len(kana),
                len(kanji),
                built.unleveled_count,
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
                "unleveled_kanji": str(built.unleveled_count),
                "vocab": str(len(deck.vocab)),
            }
            notify(BuildProgress("write", 0, 1))
            self._writer.write(target, kana=kana, kanji=kanji, vocab=deck.vocab, meta=meta)
            notify(BuildProgress("write", 1, 1))
            self._logger.info(
                "content_build dry_run=false target=%s kana=%d kanji=%d "
                "unleveled_kanji=%d vocab=%d",
                target,
                len(kana),
                len(kanji),
                built.unleveled_count,
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
            kanji_without_details=built.without_details,
            duration_seconds=time.perf_counter() - started,
            unleveled_kanji_count=built.unleveled_count,
        )

    def _build_kanji(self, levels: dict[str, JlptLevel], notify: ProgressCallback) -> _KanjiBuild:
        leveled = sorted(levels.items(), key=lambda item: (-int(item[1]), item[0]))
        candidates = self._unleveled_candidates(levels)
        total = len(leveled) + len(candidates)
        built: list[Kanji] = []
        without_details = 0
        for index, (char, level) in enumerate(leveled, start=1):
            details = self._kanji_source.get_kanji(char)
            if details is None:
                without_details += 1
                details = KanjiDetails()
            built.append(_make_kanji(char, level, details))
            notify(BuildProgress("enrich_kanji", index, total))
        if without_details:
            self._logger.warning("kanji_without_details count=%d", without_details)

        unleveled = 0
        skipped = 0
        for index, char in enumerate(candidates, start=len(leveled) + 1):
            details = self._kanji_source.get_kanji(char)
            if details is None:
                skipped += 1
            else:
                built.append(_make_kanji(char, None, details))
                unleveled += 1
            notify(BuildProgress("enrich_kanji", index, total))
        if skipped:
            self._logger.warning("unleveled_kanji_skipped count=%d", skipped)

        built.sort(key=_study_key)
        return _KanjiBuild(built, unleveled, without_details)

    def _unleveled_candidates(self, levels: dict[str, JlptLevel]) -> list[str]:
        """Graded kanji the deck does not use, de-duplicated, in code point order."""
        if self._catalog is None:
            return []
        return sorted(set(self._catalog.graded_kanji()) - levels.keys())


def _make_kanji(char: str, level: JlptLevel | None, details: KanjiDetails) -> Kanji:
    return Kanji.model_validate(
        {"id": kanji_id(char), "char": char, "level": level, **details.model_dump()}
    )
