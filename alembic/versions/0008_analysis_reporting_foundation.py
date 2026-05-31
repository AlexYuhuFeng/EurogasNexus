"""Add analysis and reporting persistence tables."""

import sqlalchemy as sa

from alembic import op

revision = "0008_analysis_reporting_foundation"
down_revision = "0007_strategy_lab_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analysis_runs",
        sa.Column("analysis_id", sa.String(128), nullable=False),
        sa.Column("task", sa.String(64), nullable=False),
        sa.Column("provider_id", sa.String(64), nullable=False),
        sa.Column("provider_status", sa.String(64), nullable=False),
        sa.Column("prompt_snapshot", sa.JSON(), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("output_snapshot", sa.JSON(), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.Column("human_review_required", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("analysis_id"),
    )
    op.create_table(
        "generated_reports",
        sa.Column("report_id", sa.String(128), nullable=False),
        sa.Column("report_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("duration_start_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_end_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.Column("human_review_required", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("report_id"),
    )
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


def downgrade() -> None:
    op.drop_table("business_ontology_terms")
    op.drop_table("generated_reports")
    op.drop_table("analysis_runs")
