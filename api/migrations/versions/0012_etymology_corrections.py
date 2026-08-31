"""Readers correcting what a name means.

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "etymology_corrections",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "place_id",
            sa.BigInteger,
            sa.ForeignKey("places.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("normalized_text", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        # One person, one claim per place. Filing it twice is a double-click,
        # not a second opinion.
        sa.UniqueConstraint(
            "place_id", "user_id", "normalized_text", name="uq_correction_per_person"
        ),
    )


def downgrade() -> None:
    op.drop_table("etymology_corrections")
