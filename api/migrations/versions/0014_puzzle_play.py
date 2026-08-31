"""Attempts at the daily puzzle, and the streaks they build.

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "puzzle_attempts",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "puzzle_id",
            sa.BigInteger,
            sa.ForeignKey("puzzles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "guest_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guest_sessions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        # Ordered array of {place_id, distance_km, bearing}.
        sa.Column("guesses", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("solved", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("guess_count", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        # One attempt per player per puzzle. Partial, because two guests both
        # holding NULL user_id must not collide with each other.
        sa.Index(
            "uq_attempt_per_user",
            "puzzle_id",
            "user_id",
            unique=True,
            postgresql_where=sa.text("user_id IS NOT NULL"),
        ),
        sa.Index(
            "uq_attempt_per_guest",
            "puzzle_id",
            "guest_session_id",
            unique=True,
            postgresql_where=sa.text("guest_session_id IS NOT NULL"),
        ),
        # Exactly one player, the same rule discoveries follow.
        sa.CheckConstraint(
            "(user_id IS NOT NULL AND guest_session_id IS NULL)"
            " OR (user_id IS NULL AND guest_session_id IS NOT NULL)",
            name="ck_attempt_player",
        ),
    )

    # Puzzle streaks, which are not the activity streak on the passport: that
    # one counts days with a discovery or a vote and is computed live from
    # them. This one counts consecutive days a puzzle was solved, and is stored
    # because yesterday's solve cannot be recomputed from anything else.
    op.create_table(
        "streaks",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("current", sa.Integer, nullable=False, server_default="0"),
        sa.Column("longest", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_played_on", sa.Date, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("streaks")
    op.drop_table("puzzle_attempts")
