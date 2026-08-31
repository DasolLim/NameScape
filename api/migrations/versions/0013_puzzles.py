"""The daily puzzle, generated in batches and approved by a person.

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "puzzles",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        # Unique: one puzzle per day, identical for every player worldwide.
        # This constraint is what makes "the same date never generates twice"
        # true under a batch run that is interrupted and started again.
        sa.Column("puzzle_date", sa.Date, nullable=False, unique=True),
        sa.Column(
            "place_id",
            sa.BigInteger,
            sa.ForeignKey("places.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Ordered array of clue strings, revealed one per wrong guess.
        sa.Column("clues", postgresql.JSONB, nullable=False),
        # draft -> approved -> live -> archived. Never written as anything but
        # draft: a person approves, ninety days ahead of anyone playing it.
        sa.Column("status", sa.Text, nullable=False, server_default="draft"),
        sa.Column("generated_by", sa.Text, nullable=False),
        sa.Column("approved_by", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # A place should not be the answer twice.
    op.create_index("ix_puzzles_place", "puzzles", ["place_id"], unique=True)
    op.create_index("ix_puzzles_status_date", "puzzles", ["status", "puzzle_date"])


def downgrade() -> None:
    op.drop_index("ix_puzzles_status_date", table_name="puzzles")
    op.drop_index("ix_puzzles_place", table_name="puzzles")
    op.drop_table("puzzles")
