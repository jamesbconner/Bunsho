"""Initial progress.db schema: card_state, review_log, app_setting.

Revision ID: 0001
Revises:
Create Date: 2026-09-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the initial tables."""
    op.create_table(
        "card_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.String(length=255), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("state", sa.Integer(), server_default="0", nullable=False),
        sa.Column("step", sa.Integer(), nullable=True),
        sa.Column("stability", sa.Float(), nullable=True),
        sa.Column("difficulty", sa.Float(), nullable=True),
        sa.Column("due", sa.String(length=32), nullable=False),
        sa.Column("last_review", sa.String(length=32), nullable=True),
        sa.Column("reps", sa.Integer(), server_default="0", nullable=False),
        sa.Column("lapses", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_id", "direction", name="uq_card_state_item_direction"),
    )
    op.create_index("ix_card_state_due", "card_state", ["due"])
    op.create_table(
        "review_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.String(length=255), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("grade", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=32), server_default="flip", nullable=False),
        sa.Column("reviewed_at", sa.String(length=32), nullable=False),
        sa.Column("state_before", sa.Integer(), nullable=True),
        sa.Column("stability_before", sa.Float(), nullable=True),
        sa.Column("difficulty_before", sa.Float(), nullable=True),
        sa.Column("elapsed_days", sa.Float(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_log_card", "review_log", ["item_id", "direction"])
    op.create_index("ix_review_log_reviewed_at", "review_log", ["reviewed_at"])
    op.create_table(
        "app_setting",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    """Drop the initial tables."""
    op.drop_table("app_setting")
    op.drop_index("ix_review_log_reviewed_at", table_name="review_log")
    op.drop_index("ix_review_log_card", table_name="review_log")
    op.drop_table("review_log")
    op.drop_index("ix_card_state_due", table_name="card_state")
    op.drop_table("card_state")
