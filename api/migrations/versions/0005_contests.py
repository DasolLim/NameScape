"""Create contests, proposals and votes.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "contests",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("place_id", sa.BigInteger, sa.ForeignKey("places.id"), nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("winner_proposal_id", sa.BigInteger, nullable=True),
        sa.Column("winning_score", sa.Integer, nullable=True),
        sa.Column("term_ends_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "proposals",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("contest_id", sa.BigInteger, sa.ForeignKey("contests.id"), nullable=True),
        sa.Column("place_id", sa.BigInteger, sa.ForeignKey("places.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("normalized_text", sa.Text, nullable=False),
        sa.Column("agree", sa.Integer, nullable=False, server_default="0"),
        sa.Column("disagree", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_incumbent", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_proposals_contest_agree", "proposals", ["contest_id", sa.text("agree DESC")]
    )
    # Near-duplicate detection compares normalised proposal text per place.
    op.execute(
        "CREATE INDEX ix_proposals_normalized_trgm "
        "ON proposals USING gin (normalized_text gin_trgm_ops)"
    )
    op.create_table(
        "votes",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            primary_key=True,
        ),
        sa.Column("proposal_id", sa.BigInteger, sa.ForeignKey("proposals.id"), primary_key=True),
        sa.Column("value", sa.SmallInteger, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("votes")
    op.drop_table("proposals")
    op.drop_table("contests")
