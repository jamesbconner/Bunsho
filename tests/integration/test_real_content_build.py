from pathlib import Path

import pytest

from bunsho.config.settings import DEFAULT_DECK_FILENAME, DEFAULT_DECK_SHA256, AppConfig
from bunsho.factories import create_content_build_orchestrator, create_context
from bunsho.models.content import JlptLevel, kanji_id
from bunsho.orchestration.content_build import BuildReport
from bunsho.services.content_repository import ContentRepository

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[BuildReport, ContentRepository]:
    config = AppConfig(
        data_dir=tmp_path_factory.mktemp("data"),
        resources_dir=REPO_ROOT / "resources",
        deck_filename=DEFAULT_DECK_FILENAME,
        deck_sha256=DEFAULT_DECK_SHA256,
        jamdict_db=None,
        log_level="INFO",
    )
    if not config.deck_path.is_file():
        pytest.skip(f"deck not present: {config.deck_path}")
    ctx = create_context(config)
    if ctx.kanji_source is None:
        pytest.skip("jamdict-data-fix database unavailable")
    report = create_content_build_orchestrator(ctx).build(config.deck_path, config.content_db_path)
    return report, ContentRepository(config.content_db_path)


@pytest.mark.integration
def test_counts_match_the_pinned_deck(built: tuple[BuildReport, ContentRepository]) -> None:
    report, repo = built
    assert report.vocab_count == 7734
    assert report.vocab_by_level == {"N5": 667, "N4": 630, "N3": 1647, "N2": 1737, "N1": 3053}
    assert report.kanji_count == 2109
    assert report.kanji_by_level == {"N5": 480, "N4": 352, "N3": 544, "N2": 357, "N1": 376}
    assert report.kana_count == 208
    assert report.sentence_count == 6775
    counts = repo.counts()
    assert (counts.kana, counts.kanji, counts.vocab) == (208, 2109, 7734)
    assert repo.meta()["deck_sha256"] == DEFAULT_DECK_SHA256


@pytest.mark.integration
def test_well_known_kanji_are_n5_with_dictionary_details(
    built: tuple[BuildReport, ContentRepository],
) -> None:
    _, repo = built
    for char in "日本人大学水食":
        kanji = repo.get_kanji(kanji_id(char))
        assert kanji is not None
        assert kanji.level is JlptLevel.N5
        assert kanji.meanings
        assert kanji.on_readings + kanji.kun_readings
    nichi = repo.get_kanji(kanji_id("日"))
    assert nichi is not None
    assert nichi.stroke_count == 4


@pytest.mark.integration
def test_few_kanji_lack_dictionary_details(built: tuple[BuildReport, ContentRepository]) -> None:
    report, _ = built
    # If this fails, read the kanji_without_details warning before loosening the bound.
    assert report.kanji_without_details <= report.kanji_count * 0.02
