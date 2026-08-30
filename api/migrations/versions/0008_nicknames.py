"""Create nicknames and nickname_history.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "nicknames",
        # One nickname per place: single-winner is what the PRD assumes.
        sa.Column("place_id", sa.BigInteger, sa.ForeignKey("places.id"), primary_key=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("proposal_id", sa.BigInteger, sa.ForeignKey("proposals.id"), nullable=False),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("term_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "nickname_history",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("place_id", sa.BigInteger, sa.ForeignKey("places.id"), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("held_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("held_until", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_nickname_history_place", "nickname_history", ["place_id"])


def downgrade() -> None:
    op.drop_table("nickname_history")
    op.drop_table("nicknames")
