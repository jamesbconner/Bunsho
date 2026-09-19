from collections import Counter

from bunsho.models.content import KanaKind, KanaScript
from bunsho.services.kana_source import KanaSource


def test_counts_per_script_and_kind() -> None:
    kana = KanaSource().all_kana()
    counts = Counter((k.script, k.kind) for k in kana)
    for script in (KanaScript.HIRAGANA, KanaScript.KATAKANA):
        assert counts[(script, KanaKind.BASIC)] == 46
        assert counts[(script, KanaKind.DAKUTEN)] == 25
        assert counts[(script, KanaKind.YOUON)] == 33
    assert len(kana) == 208


def test_ids_are_unique_and_stable_format() -> None:
    kana = KanaSource().all_kana()
    assert len({k.id for k in kana}) == len(kana)
    assert kana[0].id == "kana:hira:あ"


def test_katakana_mirrors_hiragana() -> None:
    by_id = {k.id: k for k in KanaSource().all_kana()}
    assert by_id["kana:kata:ア"].romaji == "a"
    assert by_id["kana:kata:ン"].romaji == "n"
    assert by_id["kana:kata:シャ"].romaji == "sha"
    assert by_id["kana:hira:しゃ"].kind is KanaKind.YOUON
    assert by_id["kana:hira:が"].kind is KanaKind.DAKUTEN
    assert by_id["kana:hira:を"].romaji == "wo"


def test_order_is_basic_then_dakuten_then_youon() -> None:
    kinds = [k.kind for k in KanaSource().all_kana()[:104]]
    assert kinds == [KanaKind.BASIC] * 46 + [KanaKind.DAKUTEN] * 25 + [KanaKind.YOUON] * 33
