"""Add the Decision Case tables (Architecture V2 Wave 6).

Revision ID: 0035_decision_cases
Revises: 0034_analysis_snapshots
Create Date: 2026-09-16

Backward compatibility
----------------------
Expand-only and non-destructive. This revision creates two new tables,
``decision_cases`` and ``decision_case_records``, plus read indexes on them. It:

- alters no existing table, column, constraint or index;
- drops no column and rewrites no row;
- requires no backfill and no application coordination, so the previous
  application version keeps running unchanged against the migrated schema and
  an older database upgraded to this revision serves every pre-existing
  endpoint exactly as before;
- is safe to apply while the application is serving traffic.

A deployment that never opens a decision case simply has no rows. Downgrade drops
only the tables this revision created; it never touches data owned by an earlier
revision.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0035_decision_cases"
down_revision: str | None = "0034_analysis_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the decision case container and its decision-record table."""

    op.create_table(
        "decision_cases",
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gas_day", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("delivery_product", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("hub_id", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("portfolio_ref", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("snapshot_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("assumptions_json", sa.JSON(), nullable=False),
        sa.Column("alternatives_json", sa.JSON(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("ai_findings_json", sa.JSON(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("case_id"),
    )
    op.create_index("ix_decision_cases_status", "decision_cases", ["status"])
    op.create_index("ix_decision_cases_updated_at", "decision_cases", ["updated_at_utc"])
    op.create_index("ix_decision_cases_gas_day", "decision_cases", ["gas_day"])
    op.create_index("ix_decision_cases_created_by", "decision_cases", ["created_by"])

    op.create_table(
        "decision_case_records",
        sa.Column("record_id", sa.String(length=64), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("evidence_refs_json", sa.JSON(), nullable=False),
        sa.Column("recorded_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["decision_cases.case_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("record_id"),
    )
    op.create_index("ix_decision_case_records_case_id", "decision_case_records", ["case_id"])
    op.create_index(
        "ix_decision_case_records_recorded_at",
        "decision_case_records",
        ["recorded_at_utc"],
    )


def downgrade() -> None:
    """Drop the decision case tables; no earlier revision data is touched."""

    op.drop_index("ix_decision_case_records_recorded_at", table_name="decision_case_records")
    op.drop_index("ix_decision_case_records_case_id", table_name="decision_case_records")
    op.drop_table("decision_case_records")
    op.drop_index("ix_decision_cases_created_by", table_name="decision_cases")
    op.drop_index("ix_decision_cases_gas_day", table_name="decision_cases")
    op.drop_index("ix_decision_cases_updated_at", table_name="decision_cases")
    op.drop_index("ix_decision_cases_status", table_name="decision_cases")
    op.drop_table("decision_cases")
