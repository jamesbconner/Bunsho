from collections import Counter

import pytest

from bunsho.config.settings import DEFAULT_DECK_SHA256
from bunsho.models.content import JlptLevel, kanji_id
from bunsho.orchestration.content_build import BuildReport
from bunsho.services.content_repository import ContentRepository
from bunsho.text import is_kanji


@pytest.fixture(scope="module")
def built(
    real_content: tuple[BuildReport, ContentRepository],
) -> tuple[BuildReport, ContentRepository]:
    return real_content


@pytest.mark.integration
def test_counts_match_the_pinned_deck(built: tuple[BuildReport, ContentRepository]) -> None:
    report, repo = built
    assert report.vocab_count == 7734
    assert report.vocab_by_level == {"N5": 667, "N4": 630, "N3": 1647, "N2": 1737, "N1": 3053}
    assert report.kanji_count == 3088
    assert report.unleveled_kanji_count == 979
    assert report.kanji_by_level == {"N5": 480, "N4": 352, "N3": 544, "N2": 357, "N1": 376}
    assert report.kana_count == 208
    assert report.sentence_count == 6775
    counts = repo.counts()
    assert (counts.kana, counts.kanji, counts.vocab) == (208, 3088, 7734)
    meta = repo.meta()
    assert meta["deck_sha256"] == DEFAULT_DECK_SHA256
    assert (meta["kanji"], meta["unleveled_kanji"]) == ("3088", "979")


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


@pytest.mark.integration
def test_unleveled_kanji_come_from_the_graded_dictionary_entries(
    built: tuple[BuildReport, ContentRepository],
) -> None:
    _, repo = built
    unleveled = repo.list_kanji(unleveled=True)
    assert len(unleveled) == 979
    assert Counter(k.grade for k in unleveled) == {3: 1, 4: 15, 6: 6, 8: 277, 9: 520, 10: 160}
    assert all(k.level is None for k in unleveled)


@pytest.mark.integration
def test_leveled_and_unleveled_kanji_are_disjoint_and_ordered(
    built: tuple[BuildReport, ContentRepository],
) -> None:
    _, repo = built
    leveled_total = sum(len(repo.list_kanji(level)) for level in JlptLevel)
    assert leveled_total == 2109
    everything = repo.list_kanji()
    assert len(everything) == 3088
    assert all(is_kanji(k.char) for k in everything)
    assert len({k.char for k in everything}) == 3088
    unleveled_chars = {k.char for k in repo.list_kanji(unleveled=True)}
    assert not unleveled_chars & {k.char for k in everything if k.level is not None}
    first_unleveled = next(i for i, k in enumerate(everything) if k.level is None)
    assert all(k.level is not None for k in everything[:first_unleveled])
    assert all(k.level is None for k in everything[first_unleveled:])
    assert first_unleveled == 2109  # the last leveled kanji precedes the first unleveled one


@pytest.mark.integration
def test_built_database_passes_the_schema_check(
    built: tuple[BuildReport, ContentRepository],
) -> None:
    _, repo = built
    repo.verify_schema()
