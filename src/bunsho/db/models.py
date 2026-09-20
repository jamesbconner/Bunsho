"""SQLAlchemy models for ``progress.db`` (the irreplaceable study history)."""

from __future__ import annotations

from sqlalchemy import Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for every ``progress.db`` table."""


class CardState(Base):
    """Scheduling state of one card (an item plus a direction)."""

    __tablename__ = "card_state"
    __table_args__ = (
        UniqueConstraint("item_id", "direction", name="uq_card_state_item_direction"),
        Index("ix_card_state_due", "due"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[str] = mapped_column(String(255))
    direction: Mapped[str] = mapped_column(String(32))
    state: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    step: Mapped[int | None] = mapped_column(Integer)
    stability: Mapped[float | None] = mapped_column(Float)
    difficulty: Mapped[float | None] = mapped_column(Float)
    due: Mapped[str] = mapped_column(String(32))
    last_review: Mapped[str | None] = mapped_column(String(32))
    reps: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    lapses: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class ReviewLog(Base):
    """Append-only history of every review."""

    __tablename__ = "review_log"
    __table_args__ = (
        Index("ix_review_log_card", "item_id", "direction"),
        Index("ix_review_log_reviewed_at", "reviewed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[str] = mapped_column(String(255))
    direction: Mapped[str] = mapped_column(String(32))
    grade: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(32), default="flip", server_default="flip")
    reviewed_at: Mapped[str] = mapped_column(String(32))
    state_before: Mapped[int | None] = mapped_column(Integer)
    stability_before: Mapped[float | None] = mapped_column(Float)
    difficulty_before: Mapped[float | None] = mapped_column(Float)
    elapsed_days: Mapped[float | None] = mapped_column(Float)
    duration_ms: Mapped[int | None] = mapped_column(Integer)


class AppSetting(Base):
    """A small key/value store for user settings."""

    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(String)
