"""Glossary concept ids and hub effective-period/supersession columns."""

import sqlalchemy as sa

from alembic import op

revision = "0020_concept_ids_hub_periods"
down_revision = "0019_ontology_slots_optimization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Stable ontology concept id per glossary term (Gate 2: glossary terms are
    # annotations of ontology concepts, not free text).
    op.add_column(
        "glossary_terms",
        sa.Column("concept_id", sa.String(64), nullable=True),
    )
    # reference_market_hubs becomes an effective-dated DB reference master:
    # validity window, market-area binding, and supersession (THE replaces
    # NCG/GASPOOL) are stored instead of hard-coded.
    op.add_column(
        "reference_market_hubs",
        sa.Column("valid_from_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "reference_market_hubs",
        sa.Column("valid_to_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "reference_market_hubs",
        sa.Column("superseded_by_hub_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "reference_market_hubs",
        sa.Column("market_area", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    for column in ("market_area", "superseded_by_hub_id", "valid_to_utc", "valid_from_utc"):
        op.drop_column("reference_market_hubs", column)
    op.drop_column("glossary_terms", "concept_id")
