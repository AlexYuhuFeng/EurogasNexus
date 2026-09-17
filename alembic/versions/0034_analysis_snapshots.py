"""Add the Analysis Snapshot descriptor table (Architecture V2 Wave 4).

Revision ID: 0034_analysis_snapshots
Revises: 0033_market_obs_order_indexes
Create Date: 2026-09-16

Backward compatibility
----------------------
Expand-only and non-destructive. This revision creates the new
``analysis_snapshots`` table and three read indexes on it. It:

- alters no existing table, column, constraint or index;
- drops no column and rewrites no row;
- requires no backfill and no application coordination, so the previous
  application version keeps running unchanged against the migrated schema and
  an older database upgraded to this revision serves every pre-existing
  endpoint exactly as before;
- is safe to apply while the application is serving traffic.

A writer that has never recorded a snapshot simply has no rows. Downgrade
drops only the table this revision created; it never touches data owned by an
earlier revision.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0034_analysis_snapshots"
down_revision: str | None = "0033_market_obs_order_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the Analysis Snapshot descriptor table and its read indexes."""

    op.create_table(
        "analysis_snapshots",
        sa.Column("snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("as_of_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gas_day", sa.String(length=10), nullable=False),
        sa.Column("gas_day_calendar", sa.String(length=32), nullable=False),
        sa.Column("time_basis", sa.String(length=32), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("active_context_json", sa.JSON(), nullable=True),
        sa.Column("market_data_versions_json", sa.JSON(), nullable=True),
        sa.Column("network_capacity_version_json", sa.JSON(), nullable=True),
        sa.Column("portfolio_version_json", sa.JSON(), nullable=True),
        sa.Column("contract_resource_versions_json", sa.JSON(), nullable=True),
        sa.Column("tariff_fx_json", sa.JSON(), nullable=True),
        sa.Column("weather_demand_assumptions_json", sa.JSON(), nullable=True),
        sa.Column("manual_assumptions_json", sa.JSON(), nullable=True),
        sa.Column("model_calculation_versions_json", sa.JSON(), nullable=True),
        sa.Column("entitlement_context_json", sa.JSON(), nullable=True),
        sa.Column("field_availability_json", sa.JSON(), nullable=True),
        sa.Column("source_refs", sa.JSON(), nullable=True),
        sa.Column("warnings", sa.JSON(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "research_only",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "human_review_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.PrimaryKeyConstraint("snapshot_id"),
    )
    op.create_index(
        "ix_analysis_snapshots_created_at",
        "analysis_snapshots",
        ["created_at_utc"],
    )
    op.create_index(
        "ix_analysis_snapshots_gas_day",
        "analysis_snapshots",
        ["gas_day"],
    )
    op.create_index(
        "ix_analysis_snapshots_created_by",
        "analysis_snapshots",
        ["created_by"],
    )


def downgrade() -> None:
    """Drop the Analysis Snapshot table; no earlier revision data is touched."""

    op.drop_index("ix_analysis_snapshots_created_by", table_name="analysis_snapshots")
    op.drop_index("ix_analysis_snapshots_gas_day", table_name="analysis_snapshots")
    op.drop_index("ix_analysis_snapshots_created_at", table_name="analysis_snapshots")
    op.drop_table("analysis_snapshots")
