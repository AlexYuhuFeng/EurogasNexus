"""Drop the orphaned business_ontology_terms table.

The ontology is now a typed code contract (``eurogas_nexus.domain.ontology``), so
this DB table — which never had a writer — is decommissioned.
"""

import sqlalchemy as sa

from alembic import op

revision = "0016_drop_business_ontology_terms"
down_revision = "0015_llm_monitoring_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("business_ontology_terms")


def downgrade() -> None:
    op.create_table(
        "business_ontology_terms",
        sa.Column("ontology_id", sa.String(128), nullable=False),
        sa.Column("term", sa.String(128), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("definition_en", sa.Text(), nullable=False),
        sa.Column("definition_zh_cn", sa.Text(), nullable=False),
        sa.Column("relationships", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("ontology_id"),
    )
