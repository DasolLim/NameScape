"""Guest sessions, and a discovery that can belong to one.

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: None = None
depends_on: None = None

#: Written out rather than assembled, because this constraint is the whole
#: point: a guest claim with no expiry and a user claim with one are both
#: unrepresentable, not merely discouraged in application code.
CLAIMANT_CHECK = """
    (claimant_type = 'user'  AND user_id IS NOT NULL
                             AND guest_session_id IS NULL
                             AND expires_at IS NULL)
    OR
    (claimant_type = 'guest' AND guest_session_id IS NOT NULL
                             AND user_id IS NULL
                             AND expires_at IS NOT NULL)
"""


def upgrade() -> None:
    op.create_table(
        "guest_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "merged_into",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column(
        "discoveries",
        sa.Column("claimant_type", sa.Text, nullable=False, server_default="user"),
    )
    op.add_column(
        "discoveries",
        sa.Column(
            "guest_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guest_sessions.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.add_column("discoveries", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    # Every existing row is a user claim, which is why the default above is
    # safe; user_id can only become optional after they are all labelled.
    op.alter_column("discoveries", "user_id", nullable=True)
    op.create_check_constraint("ck_discoveries_claimant", "discoveries", CLAIMANT_CHECK)
    # The expiry job scans this and nothing else.
    op.create_index(
        "ix_discoveries_expires_at",
        "discoveries",
        ["expires_at"],
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_discoveries_expires_at", table_name="discoveries")
    op.drop_constraint("ck_discoveries_claimant", "discoveries")
    op.execute("DELETE FROM discoveries WHERE claimant_type = 'guest'")
    op.alter_column("discoveries", "user_id", nullable=False)
    op.drop_column("discoveries", "expires_at")
    op.drop_column("discoveries", "guest_session_id")
    op.drop_column("discoveries", "claimant_type")
    op.drop_table("guest_sessions")
