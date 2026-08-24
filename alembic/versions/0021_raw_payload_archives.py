"""Raw payload archive for raw -> canonical lineage (Gate 4)."""

import sqlalchemy as sa

from alembic import op

revision = "0021_raw_payload_archives"
down_revision = "0020_concept_ids_hub_periods"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "raw_payload_archives",
        sa.Column("archive_id", sa.String(64), nullable=False),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("dataset", sa.String(64), nullable=False),
        sa.Column("source_reference", sa.String(256), nullable=False),
        sa.Column("payload_text", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("received_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.Column("human_review_required", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("archive_id"),
    )


def downgrade() -> None:
    op.drop_table("raw_payload_archives")
