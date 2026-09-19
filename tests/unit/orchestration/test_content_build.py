import logging
from pathlib import Path

import pytest

from bunsho.models.content import ImportedDeck, JlptLevel, Vocab
from bunsho.orchestration.content_build import BuildProgress, ContentBuildOrchestrator
from bunsho.services.anki_importer import DeckImportError
from bunsho.services.content_repository import ContentRepository, ContentWriter
from bunsho.services.kana_source import KanaSource
from tests.base import FakeKanjiSource, make_kanji_details, make_vocab


class _FakeImporter:
    def __init__(self, vocab: list[Vocab]) -> None:
        self._vocab = vocab

    def import_vocab(self, deck_path: Path) -> ImportedDeck:
        return ImportedDeck(vocab=self._vocab, sha256="a" * 64)


class _FailingImporter:
    def import_vocab(self, deck_path: Path) -> ImportedDeck:
        raise DeckImportError("boom")


VOCAB = [
    make_vocab("日本", "にほん", JlptLevel.N5),
    make_vocab("日曜日", "にちようび", JlptLevel.N4),
    make_vocab("無", "む", JlptLevel.N5),
]


def _orchestrator(
    importer: object, source: FakeKanjiSource | None = None
) -> ContentBuildOrchestrator:
    source = source or FakeKanjiSource(
        {
            "日": make_kanji_details(frequency=1),
            "本": make_kanji_details(frequency=5),
            "曜": make_kanji_details(frequency=900),
        }
    )
    return ContentBuildOrchestrator(
        importer=importer,  # type: ignore[arg-type]
        kana_provider=KanaSource(),
        kanji_source=source,
        writer=ContentWriter(),
        logger=logging.getLogger("bunsho.tests"),
    )


def test_build_writes_content_and_reports(tmp_path: Path) -> None:
    target = tmp_path / "content.db"
    report = _orchestrator(_FakeImporter(VOCAB)).build(tmp_path / "deck.apkg", target)
    assert report.dry_run is False
    assert (report.kana_count, report.kanji_count, report.vocab_count) == (208, 4, 3)
    assert report.sentence_count == 0
    assert report.vocab_by_level == {"N5": 2, "N4": 1}
    assert report.kanji_by_level == {"N5": 3, "N4": 1}
    assert report.kanji_without_details == 1  # 無 has no dictionary entry
    assert report.deck_sha256 == "a" * 64
    repo = ContentRepository(target)
    assert [k.char for k in repo.list_kanji()] == ["日", "本", "無", "曜"]
    assert repo.meta()["deck_sha256"] == "a" * 64
    assert repo.meta()["vocab"] == "3"
    repo.verify_schema()  # the orchestrator stamps the repository's schema version
    assert repo.get_kanji("kanji:無") is not None  # stored even without details


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    target = tmp_path / "content.db"
    stages: list[str] = []
    report = _orchestrator(_FakeImporter(VOCAB)).build(
        tmp_path / "deck.apkg", target, dry_run=True, on_progress=lambda p: stages.append(p.stage)
    )
    assert report.dry_run is True
    assert report.kanji_count == 4
    assert not target.exists()
    assert "write" not in stages


def test_progress_reports_every_stage_in_order(tmp_path: Path) -> None:
    events: list[BuildProgress] = []
    _orchestrator(_FakeImporter(VOCAB)).build(
        tmp_path / "deck.apkg", tmp_path / "c.db", on_progress=events.append
    )
    assert events[0] == BuildProgress("import_deck", 0, 1)
    assert events[1] == BuildProgress("import_deck", 1, 1)
    enrich = [e for e in events if e.stage == "enrich_kanji"]
    assert [e.current for e in enrich] == [1, 2, 3, 4]
    assert all(e.total == 4 for e in enrich)
    assert events[-2:] == [BuildProgress("write", 0, 1), BuildProgress("write", 1, 1)]


def test_failed_import_leaves_existing_database_untouched(tmp_path: Path) -> None:
    target = tmp_path / "content.db"
    _orchestrator(_FakeImporter(VOCAB)).build(tmp_path / "deck.apkg", target)
    with pytest.raises(DeckImportError):
        _orchestrator(_FailingImporter()).build(tmp_path / "deck.apkg", target)
    assert ContentRepository(target).counts().vocab == 3
