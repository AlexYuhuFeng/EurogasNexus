"""Add the upstream contract revision table (S1b).

Revision ID: 0037_contract_revisions
Revises: 0036_job_records
Create Date: 2026-10-01

Backward compatibility
----------------------
Expand-only and non-destructive. This revision creates one new table,
``upstream_contract_revisions``, plus one read index and its constraints. It:

- alters no existing table, column, constraint or index;
- drops no column and rewrites no row;
- performs no backfill and imports no domain code, so applying it can never
  execute evolving payload/serialization behavior or invent historic validity;
- needs no application code change: the previous application version keeps
  running unchanged against the migrated schema and an older database upgraded
  to this revision serves every pre-existing endpoint exactly as before.

Deployment notes: this is *not* a zero-impact change while the application is
serving traffic. Creating the foreign key takes a table-level lock on the
referenced ``upstream_resource_contracts`` (PostgreSQL: ``SHARE ROW
EXCLUSIVE``, which conflicts with concurrent row writes), so the migration can
block contract writers until it commits. Roll it out with a bounded
``lock_timeout`` plus an explicit retry procedure, and rehearse the timed
migration against a production-like database before the release; a migration
that cannot take the lock must abort and be retried rather than queue behind
live writers. Downgrading drops ``upstream_contract_revisions`` and
permanently destroys the captured revision evidence it holds, so downgrade is
gated: back up the table or confirm it is empty first, and never run it merely
to roll back an application deployment.

A deployment that never explicitly captures a contract revision simply has no
rows here; the legacy contract upsert keeps writing
``upstream_resource_contracts`` exactly as before. Downgrade drops only the
table this revision created; aside from the captured evidence above it never
touches data owned by an earlier revision.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0037_contract_revisions"
down_revision: str | None = "0036_job_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the immutable captured contract-revision table and its read index."""

    op.create_table(
        "upstream_contract_revisions",
        sa.Column("contract_revision_id", sa.String(length=64), nullable=False),
        sa.Column("contract_id", sa.String(length=128), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("capture_origin", sa.String(length=32), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("display_metadata_json", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("recorded_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["upstream_resource_contracts.contract_id"],
            name="fk_upstream_contract_revision_contract",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("contract_revision_id"),
        sa.UniqueConstraint(
            "contract_id", "revision_number", name="uq_upstream_contract_revision_number"
        ),
    )
    op.create_index(
        "ix_upstream_contract_revisions_contract",
        "upstream_contract_revisions",
        ["contract_id"],
    )


def downgrade() -> None:
    """Drop the captured-revision table; no earlier revision data is touched."""

    op.drop_index(
        "ix_upstream_contract_revisions_contract",
        table_name="upstream_contract_revisions",
    )
    op.drop_table("upstream_contract_revisions")
