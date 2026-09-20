import pytest
from pydantic import ValidationError

from bunsho.models.content import JlptLevel
from bunsho.models.review import ItemType
from bunsho.models.review_settings import NewCardPolicyName, NewLimits, ReviewSettings


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
