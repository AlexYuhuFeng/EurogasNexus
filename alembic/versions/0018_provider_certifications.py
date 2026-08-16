"""Add provider_certifications for the simulated-to-live certification gate."""

import sqlalchemy as sa

from alembic import op

revision = "0018_provider_certifications"
down_revision = "0017_review_decisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_certifications",
        sa.Column("certification_id", sa.String(64), nullable=False),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("checks", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("evaluated_by", sa.String(64), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("evaluated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("certification_id"),
        sa.UniqueConstraint("source_system", name="uq_provider_certifications_source_system"),
    )


def downgrade() -> None:
    op.drop_table("provider_certifications")
