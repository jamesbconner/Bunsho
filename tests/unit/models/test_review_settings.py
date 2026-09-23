import pytest
from pydantic import ValidationError

from bunsho.models.content import JlptLevel
from bunsho.models.review import ItemType
from bunsho.models.review_settings import (
    KanaGate,
    NewCardPolicyName,
    NewLimits,
    ReviewModeName,
    ReviewSettings,
    TypeEnabled,
)


def test_defaults_match_the_spec() -> None:
    settings = ReviewSettings()
    assert settings.new_card_policy is NewCardPolicyName.STRICT_ORDER
    assert (settings.new_limits.kana, settings.new_limits.kanji, settings.new_limits.vocab) == (
        20,
        15,
        20,
    )
    assert settings.target_retention == 0.90
    assert settings.rollover_hour == 4
    assert settings.active_levels == ["N5"]
    assert settings.mastery_threshold == 0.80


def test_limits_are_looked_up_by_item_type() -> None:
    limits = NewLimits(kana=1, kanji=2, vocab=3)
    assert [limits.for_type(t) for t in ItemType] == [1, 2, 3]


def test_active_levels_map_to_jlpt_levels() -> None:
    assert ReviewSettings(active_levels=["N5", "N3"]).levels() == {JlptLevel.N5, JlptLevel.N3}


def test_review_modes_default_to_flip() -> None:
    settings = ReviewSettings()
    assert settings.kana_mode is ReviewModeName.FLIP
    assert settings.kanji_mode is ReviewModeName.FLIP
    assert settings.vocab_mode is ReviewModeName.FLIP


def test_review_modes_are_looked_up_by_item_type() -> None:
    settings = ReviewSettings(
        kana_mode=ReviewModeName.TYPED,
        kanji_mode=ReviewModeName.MULTIPLE_CHOICE,
        vocab_mode=ReviewModeName.FLIP,
    )
    assert [settings.mode_for(t) for t in ItemType] == [
        ReviewModeName.TYPED,
        ReviewModeName.MULTIPLE_CHOICE,
        ReviewModeName.FLIP,
    ]


@pytest.mark.parametrize(
    "bad",
    [
        {"target_retention": 0.69},
        {"target_retention": 1.0},
        {"rollover_hour": -1},
        {"rollover_hour": 24},
        {"mastery_threshold": -0.1},
        {"mastery_threshold": 1.1},
        {"new_limits": {"kana": -1}},
        {"active_levels": []},
        {"active_levels": ["N6"]},
        {"new_card_policy": "random"},
        {"unknown_field": 1},
        {"new_limits": {"kana": 1, "extra": 1}},
        {"kana_mode": "loud"},
    ],
)
def test_invalid_settings_are_rejected(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ReviewSettings.model_validate(bad)


@pytest.mark.parametrize(
    "good",
    [
        {"target_retention": 0.70},
        {"target_retention": 0.99},
        {"rollover_hour": 0},
        {"rollover_hour": 23},
        {"mastery_threshold": 0},
        {"mastery_threshold": 1},
        {"new_limits": {"kana": 0}},
    ],
)
def test_boundary_values_are_accepted(good: dict[str, object]) -> None:
    ReviewSettings.model_validate(good)


def test_settings_round_trip_through_json() -> None:
    settings = ReviewSettings(
        new_card_policy=NewCardPolicyName.PINNED_LEVELS, active_levels=["N4", "N5"]
    )
    assert ReviewSettings.model_validate_json(settings.model_dump_json()) == settings


def test_type_switches_and_the_kana_gate_default_to_todays_behaviour() -> None:
    settings = ReviewSettings()
    assert settings.type_enabled == TypeEnabled(kana=True, kanji=True, vocab=True)
    assert settings.kana_gate == KanaGate(kanji=False, vocab=False, threshold=0.80)


def test_type_switches_are_looked_up_by_item_type() -> None:
    enabled = TypeEnabled(kana=True, kanji=False, vocab=True)
    assert [enabled.for_type(t) for t in ItemType] == [True, False, True]


def test_only_kanji_and_vocab_can_be_gated() -> None:
    gate = KanaGate(kanji=True, vocab=False)
    assert [gate.gates(t) for t in ItemType] == [False, True, False]
    assert [KanaGate().gates(t) for t in ItemType] == [False, False, False]


@pytest.mark.parametrize("threshold", [0.0, 0.5, 1.0])
def test_the_gate_threshold_accepts_a_fraction(threshold: float) -> None:
    assert KanaGate(threshold=threshold).threshold == threshold


@pytest.mark.parametrize("threshold", [-0.01, 1.01])
def test_the_gate_threshold_rejects_anything_else(threshold: float) -> None:
    with pytest.raises(ValidationError):
        KanaGate(threshold=threshold)


@pytest.mark.parametrize("gate", [{"kanji": True}, {"vocab": True}, {"kanji": True, "vocab": True}])
def test_a_gate_needs_kana_to_be_enabled(gate: dict[str, bool]) -> None:
    with pytest.raises(ValidationError, match="Turn kana on") as caught:
        ReviewSettings(type_enabled=TypeEnabled(kana=False), kana_gate=KanaGate(**gate))
    assert [error["loc"] for error in caught.value.errors()] == [("kana_gate",)]
    assert caught.value.errors()[0]["type"] == "kana_gate_needs_kana"


def test_kana_can_be_off_while_no_gate_is_on_and_every_type_can_be_off() -> None:
    assert ReviewSettings(type_enabled=TypeEnabled(kana=False)).type_enabled.kana is False
    nothing = TypeEnabled(kana=False, kanji=False, vocab=False)
    assert ReviewSettings(type_enabled=nothing).type_enabled == nothing


def test_the_gate_check_is_skipped_when_the_switches_are_themselves_invalid() -> None:
    with pytest.raises(ValidationError) as caught:
        ReviewSettings.model_validate(
            {"type_enabled": {"kana": "maybe"}, "kana_gate": {"kanji": True}}
        )
    assert [error["loc"] for error in caught.value.errors()] == [("type_enabled", "kana")]


def test_unknown_keys_in_the_new_objects_are_rejected() -> None:
    with pytest.raises(ValidationError):
        TypeEnabled.model_validate({"kana": True, "surprise": True})
    with pytest.raises(ValidationError):
        KanaGate.model_validate({"surprise": True})
