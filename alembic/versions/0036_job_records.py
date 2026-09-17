"""Add the unified job table (Architecture V2 Wave 8).

Revision ID: 0036_job_records
Revises: 0035_decision_cases
Create Date: 2026-09-16

Backward compatibility
----------------------
Expand-only and non-destructive. This revision creates the ``job_records`` table
and three read indexes on it. It:

- alters no existing table, column, constraint or index;
- drops no column and rewrites no row;
- requires no backfill and no application coordination, so the previous
  application version keeps running unchanged against the migrated schema and an
  older database upgraded to this revision serves every pre-existing endpoint
  exactly as before;
- is safe to apply while the application is serving traffic.

A deployment that never tracks a job simply has no rows. Downgrade drops only the
table this revision created; it never touches data owned by an earlier revision.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0036_job_records"
down_revision: str | None = "0035_decision_cases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the unified job table and its read indexes."""

    op.create_table(
        "job_records",
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("job_version", sa.String(length=16), nullable=False, server_default="job/v1"),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("principal", sa.String(length=64), nullable=False),
        sa.Column("scope_refs_json", sa.JSON(), nullable=False),
        sa.Column("snapshot_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("input_hash", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("output_refs_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cancellable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("job_id"),
    )
    op.create_index("ix_job_records_created_at", "job_records", ["created_at_utc"])
    op.create_index("ix_job_records_status", "job_records", ["status"])
    op.create_index("ix_job_records_kind", "job_records", ["kind"])
    op.create_index("ix_job_records_principal", "job_records", ["principal"])


def downgrade() -> None:
    """Drop the job table; no earlier revision data is touched."""

    op.drop_index("ix_job_records_principal", table_name="job_records")
    op.drop_index("ix_job_records_kind", table_name="job_records")
    op.drop_index("ix_job_records_status", table_name="job_records")
    op.drop_index("ix_job_records_created_at", table_name="job_records")
    op.drop_table("job_records")
