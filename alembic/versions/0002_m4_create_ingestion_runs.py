"""Create ingestion_runs table."""

import sqlalchemy as sa

from alembic import op

revision = "0002_m4_create_ingestion_runs"
down_revision = "0001_m2_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create ingestion run metadata table."""

    op.create_table(
        "ingestion_runs",
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("source_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("run_id"),
    )


def downgrade() -> None:
    """Drop ingestion run metadata table."""

    op.drop_table("ingestion_runs")
