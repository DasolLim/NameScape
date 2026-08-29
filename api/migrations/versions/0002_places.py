"""Create places, the gazetteer cache.

Revision ID: 0002
Revises: 0001
"""

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "places",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("geonames_id", sa.BigInteger, nullable=False, unique=True),
        sa.Column("wof_id", sa.BigInteger, nullable=True),
        sa.Column("wikidata_id", sa.Text, nullable=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("name_normalized", sa.Text, nullable=False),
        sa.Column("alternate_names", sa.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("feature_class", sa.CHAR(1), nullable=False),
        sa.Column("feature_code", sa.Text, nullable=False),
        sa.Column("country_code", sa.CHAR(2), nullable=True),
        sa.Column("admin1", sa.Text, nullable=True),
        sa.Column(
            "centroid",
            geoalchemy2.Geography(geometry_type="POINT", srid=4326),
            nullable=False,
        ),
        sa.Column("tier", sa.SmallInteger, nullable=False),
        sa.Column("population", sa.Integer, nullable=False, server_default="0"),
        sa.Column("etymology", sa.Text, nullable=True),
    )
    op.execute(
        "CREATE INDEX ix_places_name_normalized_trgm "
        "ON places USING gin (name_normalized gin_trgm_ops)"
    )
    op.create_index("ix_places_country_code", "places", ["country_code"])


def downgrade() -> None:
    op.drop_table("places")
