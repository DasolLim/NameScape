"""Create discoveries, one per place forever.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "discoveries",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        # Unique: a place can be discovered exactly once, ever. This constraint
        # is what makes first-finder credit meaningful under concurrency.
        sa.Column(
            "place_id",
            sa.BigInteger,
            sa.ForeignKey("places.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("caption", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_discoveries_user_created", "discoveries", ["user_id", sa.text("created_at DESC")]
    )


def downgrade() -> None:
    op.drop_table("discoveries")
