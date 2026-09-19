import logging
from pathlib import Path

import pytest

from bunsho.models.content import ImportedDeck, JlptLevel, Vocab
from bunsho.orchestration.content_build import BuildProgress, ContentBuildOrchestrator
from bunsho.services.anki_importer import DeckImportError
from bunsho.services.content_repository import ContentRepository, ContentWriter
from bunsho.services.kana_source import KanaSource
from tests.base import FakeKanjiCatalog, FakeKanjiSource, make_kanji_details, make_vocab


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
    importer: object,
    source: FakeKanjiSource | None = None,
    catalog: FakeKanjiCatalog | None = None,
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
        kanji_catalog=catalog,
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


def _unleveled_source() -> FakeKanjiSource:
    return FakeKanjiSource(
        {
            "日": make_kanji_details(frequency=1),
            "本": make_kanji_details(frequency=5),
            "曜": make_kanji_details(frequency=900),
            "犬": make_kanji_details(grade=1, frequency=10),
            "猫": make_kanji_details(grade=8, frequency=None),
            # 龘 has no dictionary entry
        }
    )


def _with_catalog(literals: list[str]) -> ContentBuildOrchestrator:
    return _orchestrator(_FakeImporter(VOCAB), _unleveled_source(), FakeKanjiCatalog(literals))


def test_unleveled_kanji_follow_the_leveled_ones(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    target = tmp_path / "content.db"
    with caplog.at_level(logging.WARNING, logger="bunsho.tests"):
        report = _with_catalog(["日", "犬", "猫", "龘"]).build(tmp_path / "deck.apkg", target)
    repo = ContentRepository(target)
    assert [(k.char, k.level) for k in repo.list_kanji()] == [
        ("日", JlptLevel.N5),
        ("本", JlptLevel.N5),
        ("無", JlptLevel.N5),
        ("曜", JlptLevel.N4),
        ("犬", None),
        ("猫", None),
    ]
    assert [k.char for k in repo.list_kanji(unleveled=True)] == ["犬", "猫"]
    assert report.kanji_count == 6
    assert report.unleveled_kanji_count == 2
    assert report.kanji_by_level == {"N5": 3, "N4": 1}
    assert report.kanji_without_details == 1  # 無 only; the skipped 龘 is not counted
    assert "unleveled_kanji_skipped count=1" in caplog.text
    meta = repo.meta()
    assert (meta["kanji"], meta["unleveled_kanji"]) == ("6", "2")
    repo.verify_schema()


def test_deck_kanji_are_not_duplicated_or_downgraded_by_the_catalog(tmp_path: Path) -> None:
    source = _unleveled_source()
    report = _orchestrator(
        _FakeImporter(VOCAB), source, FakeKanjiCatalog(["日", "日", "本", "犬", "犬"])
    ).build(tmp_path / "deck.apkg", tmp_path / "c.db")
    repo = ContentRepository(tmp_path / "c.db")
    assert [k.char for k in repo.list_kanji()] == ["日", "本", "無", "曜", "犬"]
    nichi = repo.get_kanji("kanji:日")
    assert nichi is not None
    assert nichi.level is JlptLevel.N5
    assert report.unleveled_kanji_count == 1
    assert source.calls.count("日") == 1  # no second lookup for a deck kanji
    assert source.calls.count("犬") == 1  # duplicates in the catalog are looked up once


def test_unleveled_kanji_are_ordered_by_grade_then_frequency_then_char(tmp_path: Path) -> None:
    source = FakeKanjiSource(
        {
            "犬": make_kanji_details(grade=2, frequency=None),
            "猫": make_kanji_details(grade=2, frequency=5),
            "鼠": make_kanji_details(grade=None, frequency=1),
            "馬": make_kanji_details(grade=1, frequency=900),
            "牛": make_kanji_details(grade=2, frequency=None),
        }
    )
    _orchestrator(
        _FakeImporter([]), source, FakeKanjiCatalog(["鼠", "犬", "猫", "馬", "牛"])
    ).build(tmp_path / "deck.apkg", tmp_path / "c.db")
    chars = [k.char for k in ContentRepository(tmp_path / "c.db").list_kanji(unleveled=True)]
    assert chars == ["馬", "猫", "牛", "犬", "鼠"]


def test_progress_total_includes_unleveled_candidates(tmp_path: Path) -> None:
    events: list[BuildProgress] = []
    _with_catalog(["日", "犬", "猫", "龘"]).build(
        tmp_path / "deck.apkg", tmp_path / "c.db", on_progress=events.append
    )
    enrich = [e for e in events if e.stage == "enrich_kanji"]
    assert [e.current for e in enrich] == [1, 2, 3, 4, 5, 6, 7]  # 4 leveled + 3 candidates
    assert all(e.total == 7 for e in enrich)


def test_dry_run_with_catalog_reports_the_same_counts_and_writes_nothing(tmp_path: Path) -> None:
    target = tmp_path / "content.db"
    dry = _with_catalog(["日", "犬", "猫", "龘"]).build(
        tmp_path / "deck.apkg", target, dry_run=True
    )
    assert not target.exists()
    real = _with_catalog(["日", "犬", "猫", "龘"]).build(tmp_path / "deck.apkg", target)
    assert dry.dry_run is True
    assert (dry.kanji_count, dry.unleveled_kanji_count) == (6, 2)
    assert dry.kanji_by_level == real.kanji_by_level
    assert dry.kanji_without_details == real.kanji_without_details


def test_without_a_catalog_no_unleveled_rows_are_produced(tmp_path: Path) -> None:
    report = _orchestrator(_FakeImporter(VOCAB)).build(tmp_path / "deck.apkg", tmp_path / "c.db")
    assert report.unleveled_kanji_count == 0
    assert report.kanji_count == 4
    assert ContentRepository(tmp_path / "c.db").meta()["unleveled_kanji"] == "0"
    assert ContentRepository(tmp_path / "c.db").list_kanji(unleveled=True) == []


class _FailingWriter:
    def write(self, target, *, kana, kanji, vocab, meta):  # type: ignore[no-untyped-def]
        raise RuntimeError("disk full")


def test_writer_failure_is_logged_and_propagates(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    logger = logging.getLogger("bunsho.test_build_failure")
    events: list[BuildProgress] = []
    orchestrator = ContentBuildOrchestrator(
        importer=_FakeImporter(VOCAB),  # type: ignore[arg-type]
        kana_provider=KanaSource(),
        kanji_source=FakeKanjiSource(),  # type: ignore[arg-type]
        writer=_FailingWriter(),  # type: ignore[arg-type]
        logger=logger,
    )
    with (
        caplog.at_level(logging.ERROR, logger=logger.name),
        pytest.raises(RuntimeError, match="disk full"),
    ):
        orchestrator.build(tmp_path / "deck.apkg", tmp_path / "c.db", on_progress=events.append)
    assert "content_build_failed stage=write" in caplog.text
    assert events[-1] == BuildProgress("write", 0, 1)
