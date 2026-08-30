"""Add an indexed search column covering names and alternate names.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.add_column(
        "places",
        sa.Column("search_text", sa.Text, nullable=False, server_default=""),
    )
    op.execute(
        "UPDATE places SET search_text = "
        "lower(name || ' ' || coalesce(array_to_string(alternate_names, ' '), ''))"
    )
    # Trigram GIN over names and alternate names together, so fuzzy matching is
    # one indexed predicate instead of an unnest subquery per row.
    op.execute(
        "CREATE INDEX ix_places_search_text_trgm ON places USING gin (search_text gin_trgm_ops)"
    )
    # text_pattern_ops makes LIKE 'query%' an index range scan, which is what
    # nearly every autocomplete keystroke actually needs.
    op.execute("CREATE INDEX ix_places_name_prefix ON places (name_normalized text_pattern_ops)")
    op.execute("CREATE INDEX ix_places_population ON places (population DESC)")


def downgrade() -> None:
    op.drop_index("ix_places_population", table_name="places")
    op.drop_index("ix_places_name_prefix", table_name="places")
    op.drop_index("ix_places_search_text_trgm", table_name="places")
    op.drop_column("places", "search_text")
