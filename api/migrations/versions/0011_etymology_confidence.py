"""Record where an etymology came from, and how much to trust it.

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    # NULL confidence means never resolved. 'unknown' means resolved and
    # nothing was found, which is what stops a fruitless lookup repeating
    # forever, and stops a model being asked again until it invents something.
    op.add_column("places", sa.Column("etymology_confidence", sa.Text, nullable=True))
    op.add_column("places", sa.Column("etymology_source", sa.Text, nullable=True))
    # Everything already resolved came from Wikidata's named-after statement.
    op.execute("UPDATE places SET etymology_confidence = 'high' WHERE etymology IS NOT NULL")


def downgrade() -> None:
    op.drop_column("places", "etymology_source")
    op.drop_column("places", "etymology_confidence")
