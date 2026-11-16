"""Market reports: the immutable record of each generated report, and licence redistribution.

- ``market_reports``: one row per generated market report (daily, weekly, monthly,
  situation, asked): the validated plan, audience, data snapshot and its hash, the rendered
  HTML and its hash, template version, who generated it under which data scopes, the source
  systems, licensed families and books behind it, and the model use with checker verdicts.
  Written once; nothing updates it.
- ``market_data_licences.redistribution_allowed``: whether a licence permits derived figures
  outside the firm. Unknown reads as no, so a report with a licensed source stays internal.

Expand-only; SQLite and PostgreSQL. The downgrade drops only what this revision added.
"""

import sqlalchemy as sa

from alembic import op

revision = "0064_market_reports"
down_revision = "0063_resplit_power_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_reports",
        sa.Column("report_id", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("variant", sa.String(16), nullable=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("audience", sa.String(16), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("plan_json", sa.JSON(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("as_of_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("html", sa.Text(), nullable=False),
        sa.Column("html_sha256", sa.String(64), nullable=False),
        sa.Column("template_version", sa.String(32), nullable=False),
        sa.Column("generated_by", sa.String(128), nullable=False),
        sa.Column("generated_by_type", sa.String(16), nullable=False),
        sa.Column("data_scopes", sa.JSON(), nullable=False),
        sa.Column("source_systems", sa.JSON(), nullable=False),
        sa.Column("licensed_families", sa.JSON(), nullable=False),
        sa.Column("book_ids", sa.JSON(), nullable=False),
        sa.Column("simulated", sa.Boolean(), nullable=False),
        sa.Column("model_use", sa.JSON(), nullable=False),
        sa.Column("trigger_json", sa.JSON(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('daily', 'weekly', 'monthly', 'situation', 'ask')",
            name="ck_market_reports_kind",
        ),
        sa.CheckConstraint(
            "audience IN ('internal', 'shareable')", name="ck_market_reports_audience"
        ),
    )
    op.create_index(
        "ix_market_reports_kind_created", "market_reports", ["kind", "created_at_utc"]
    )
    op.create_index(
        "ix_market_reports_generated_by", "market_reports", ["generated_by", "created_at_utc"]
    )
    with op.batch_alter_table("market_data_licences") as batch:
        batch.add_column(
            sa.Column(
                "redistribution_allowed",
                sa.Boolean(),
                nullable=True,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("market_data_licences") as batch:
        batch.drop_column("redistribution_allowed")
    op.drop_index("ix_market_reports_generated_by", table_name="market_reports")
    op.drop_index("ix_market_reports_kind_created", table_name="market_reports")
    op.drop_table("market_reports")
