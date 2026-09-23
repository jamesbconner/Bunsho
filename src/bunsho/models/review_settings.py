"""User-adjustable review settings, validated as one document."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

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


class ReviewModeName(StrEnum):
    """How a card is answered."""

    FLIP = "flip"
    TYPED = "typed"
    MULTIPLE_CHOICE = "multiple_choice"


class NewLimits(BaseModel):
    """Daily new-card limits per item type, counted in cards. ``0`` means unlimited."""

    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)

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


class TypeEnabled(BaseModel):
    """Which item types may introduce new cards. Cards already introduced stay due either way."""

    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)

    kana: bool = True
    kanji: bool = True
    vocab: bool = True

    def for_type(self, item_type: ItemType) -> bool:
        """Return whether ``item_type`` may introduce new cards."""
        match item_type:
            case ItemType.KANA:
                return self.kana
            case ItemType.KANJI:
                return self.kanji
            case ItemType.VOCAB:
                return self.vocab


class KanaGate(BaseModel):
    """Hold new kanji and/or vocabulary back until enough kana is learned.

    Kana is one stage: the share counts every kana card (both directions, hiragana and
    katakana together) that is in the FSRS Review state. ``threshold`` is a fraction from 0 to 1.
    """

    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)

    kanji: bool = False
    vocab: bool = False
    threshold: float = Field(default=0.80, ge=0.0, le=1.0)

    def gates(self, item_type: ItemType) -> bool:
        """Return whether ``item_type`` waits for kana. Kana itself is never gated."""
        match item_type:
            case ItemType.KANA:
                return False
            case ItemType.KANJI:
                return self.kanji
            case ItemType.VOCAB:
                return self.vocab


class ReviewSettings(BaseModel):
    """Every review setting. ``PUT /settings`` replaces the whole document."""

    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)

    new_card_policy: NewCardPolicyName = NewCardPolicyName.STRICT_ORDER
    new_limits: NewLimits = Field(default_factory=NewLimits)
    type_enabled: TypeEnabled = Field(default_factory=TypeEnabled)
    kana_gate: KanaGate = Field(default_factory=KanaGate)
    target_retention: float = Field(default=0.90, ge=0.70, le=0.99)
    rollover_hour: int = Field(default=4, ge=0, le=23)
    active_levels: list[LevelLabel] = Field(default_factory=_default_active_levels, min_length=1)
    mastery_threshold: float = Field(default=0.80, ge=0.0, le=1.0)
    kana_mode: ReviewModeName = ReviewModeName.FLIP
    kanji_mode: ReviewModeName = ReviewModeName.FLIP
    vocab_mode: ReviewModeName = ReviewModeName.FLIP

    def levels(self) -> frozenset[JlptLevel]:
        """The active levels as ``JlptLevel`` members (used by ``pinned_levels``)."""
        return frozenset(JlptLevel[label] for label in self.active_levels)

    def mode_for(self, item_type: ItemType) -> ReviewModeName:
        """Return the configured review mode for ``item_type``."""
        match item_type:
            case ItemType.KANA:
                return self.kana_mode
            case ItemType.KANJI:
                return self.kanji_mode
            case ItemType.VOCAB:
                return self.vocab_mode

    @field_validator("kana_gate")
    @classmethod
    def _gates_need_kana(cls, gate: KanaGate, info: ValidationInfo) -> KanaGate:
        """Reject a gate that could never open because kana is never introduced.

        Runs after ``type_enabled`` (declared first); if that field itself failed it is absent
        from ``info.data`` and this check is skipped, since its error is already reported.
        """
        enabled = info.data.get("type_enabled")
        if isinstance(enabled, TypeEnabled) and not enabled.kana and (gate.kanji or gate.vocab):
            raise PydanticCustomError(
                "kana_gate_needs_kana",
                "Turn kana on, or turn off the kana gate: kanji and vocabulary cannot wait "
                "for kana that is never introduced.",
            )
        return gate
