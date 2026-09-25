"""Revoked login sessions: the server-side half of logout.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``revoked_session`` table."""
    op.create_table(
        "revoked_session",
        sa.Column("sid", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("sid"),
    )


def downgrade() -> None:
    """Drop the ``revoked_session`` table."""
    op.drop_table("revoked_session")
