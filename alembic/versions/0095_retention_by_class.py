"""Retention by data class; each raw page stored once (decision record 2026-11-26).

- ``raw_payload_contents``: one row per distinct raw page, keyed by the SHA-256 of its exact
  bytes, gzip-compressed while hot, then offloaded to object storage (``stored_in``,
  ``object_key``). ``raw_payload_archives`` keeps one small receipt per fetch; new receipts no
  longer carry the page. Existing receipts keep their inline page until the retention job's
  deduplication step moves it here (batched, outside the migration, because the archive is
  most of the database).
- ``retention_policies``: an operator's raised setting per data class (the floors are code).
- ``retention_archives``: one verified archive file in object storage and the range it holds.
- ``retention_runs``: one pass of the retention job, dry-run or enforced.

Expand-only; the downgrade drops only what this revision adds. A downgrade after the
deduplication step has run loses the moved pages' only hot copy, so take the receipts' pages
back first (``scripts/ops/retention.py inline-raw-pages``) or restore from backup.
"""

import sqlalchemy as sa

from alembic import op

revision = "0095_retention_by_class"
down_revision = "0094_option_settlements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "raw_payload_contents",
        sa.Column("payload_sha256", sa.String(64), primary_key=True),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("compression", sa.String(16), nullable=False),
        sa.Column("payload_compressed", sa.LargeBinary(), nullable=True),
        sa.Column("stored_in", sa.String(16), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=True),
        sa.Column("first_received_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_received_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("offloaded_at_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_raw_payload_contents_offload",
        "raw_payload_contents",
        ["stored_in", "last_received_at_utc"],
    )
    op.create_table(
        "retention_policies",
        sa.Column("data_class", sa.String(64), primary_key=True),
        sa.Column("hot_days", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("hot_days IS NULL OR hot_days >= 0", name="ck_retention_hot_days"),
    )
    op.create_table(
        "retention_archives",
        sa.Column("archive_id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("data_class", sa.String(64), nullable=False),
        sa.Column("table_name", sa.String(64), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("range_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("range_end_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("object_store", sa.String(256), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("manifest_key", sa.String(512), nullable=False),
        sa.Column("row_count", sa.BigInteger(), nullable=False),
        sa.Column("rows_removed", sa.BigInteger(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("restored_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "data_class", "table_name", "range_start_utc", name="uq_retention_archive_range"
        ),
    )
    op.create_index(
        "ix_retention_archives_class_range",
        "retention_archives",
        ["data_class", "range_start_utc"],
    )
    op.create_table(
        "retention_runs",
        sa.Column("run_id", sa.String(64), primary_key=True),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("principal", sa.String(128), nullable=False),
        sa.Column("started_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=True),
    )
    op.create_index("ix_retention_runs_started", "retention_runs", ["started_at_utc"])


def downgrade() -> None:
    op.drop_index("ix_retention_runs_started", table_name="retention_runs")
    op.drop_table("retention_runs")
    op.drop_index("ix_retention_archives_class_range", table_name="retention_archives")
    op.drop_table("retention_archives")
    op.drop_table("retention_policies")
    op.drop_index("ix_raw_payload_contents_offload", table_name="raw_payload_contents")
    op.drop_table("raw_payload_contents")
