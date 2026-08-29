"""Create restricted_zones and give users a UI language.

Revision ID: 0006
Revises: 0005
"""

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "restricted_zones",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "geom",
            geoalchemy2.Geography(geometry_type="POLYGON", srid=4326),
            nullable=False,
        ),
        sa.Column("rule_type", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("ui_language", sa.String(8), nullable=False, server_default="en"),
    )


def downgrade() -> None:
    op.drop_column("users", "ui_language")
    op.drop_table("restricted_zones")
