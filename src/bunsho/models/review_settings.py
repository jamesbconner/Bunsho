"""User-adjustable review settings, validated as one document."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from bunsho.models.content import JlptLevel
from bunsho.models.review import ItemType

LevelLabel = Literal["N1", "N2", "N3", "N4", "N5"]


def _default_active_levels() -> list[LevelLabel]:
    return ["N5"]


class NewCardPolicyName(StrEnum):
    """How new cards are chosen each day."""

    STRICT_ORDER = "strict_order"
    MASTERY_UNLOCK = "mastery_unlock"
    PINNED_LEVELS = "pinned_levels"


class NewLimits(BaseModel):
    """Daily new-card limits per item type, counted in cards. ``0`` means unlimited."""

    model_config = ConfigDict(extra="forbid")

    kana: int = Field(default=20, ge=0, le=10_000)
    kanji: int = Field(default=15, ge=0, le=10_000)
    vocab: int = Field(default=20, ge=0, le=10_000)

    def for_type(self, item_type: ItemType) -> int:
        """Return the limit for ``item_type``."""
        match item_type:
            case ItemType.KANA:
                return self.kana
            case ItemType.KANJI:
                return self.kanji
            case ItemType.VOCAB:
                return self.vocab


class ReviewSettings(BaseModel):
    """Every review setting. ``PUT /settings`` replaces the whole document."""

    model_config = ConfigDict(extra="forbid")

    new_card_policy: NewCardPolicyName = NewCardPolicyName.STRICT_ORDER
    new_limits: NewLimits = Field(default_factory=NewLimits)
    target_retention: float = Field(default=0.90, ge=0.70, le=0.99)
    rollover_hour: int = Field(default=4, ge=0, le=23)
    active_levels: list[LevelLabel] = Field(default_factory=_default_active_levels, min_length=1)
    mastery_threshold: float = Field(default=0.80, ge=0.0, le=1.0)

    def levels(self) -> frozenset[JlptLevel]:
        """The active levels as ``JlptLevel`` members (used by ``pinned_levels``)."""
        return frozenset(JlptLevel[label] for label in self.active_levels)
