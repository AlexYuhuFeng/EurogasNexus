"""Assumption sets, firm marks and valuation snapshots (commercial design basis 2, CP-07).

- ``assumption_sets``, ``assumption_set_versions``, ``assumption_values``: the firm's named,
  versioned inputs; a version is read by valuations only once approved by a second person.
- ``firm_marks``: the customer's own marks per hub and delivery period (append-only; class
  is always "firm mark", so there is no class column).
- ``valuation_snapshots``, ``valuation_snapshot_inputs``: every input one evaluation read,
  with class, source and as-of, so the evaluation replays to identical figures.

Expand-only; SQLite and PostgreSQL. The downgrade drops only what this revision added.
"""

import sqlalchemy as sa

from alembic import op

revision = "0066_commercial_assumptions"
down_revision = "0065_local_accounts"
branch_labels = None
depends_on = None

_DECIMAL = sa.Numeric(28, 10)


def upgrade() -> None:
    op.create_table(
        "assumption_sets",
        sa.Column("set_id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=True),
        sa.Column("description", sa.String(400), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", "book_id", name="uq_assumption_sets_name_book"),
    )
    op.create_table(
        "assumption_set_versions",
        sa.Column("version_id", sa.String(64), primary_key=True),
        sa.Column(
            "set_id",
            sa.String(64),
            sa.ForeignKey("assumption_sets.set_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("review_state", sa.String(16), nullable=False),
        sa.Column("note", sa.String(400), nullable=False),
        sa.Column("values_sha256", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_by", sa.String(64), nullable=True),
        sa.Column("approved_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("set_id", "version", name="uq_assumption_set_versions_set_version"),
    )
    op.create_table(
        "assumption_values",
        sa.Column(
            "version_id",
            sa.String(64),
            sa.ForeignKey("assumption_set_versions.version_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", _DECIMAL, nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("range_low", _DECIMAL, nullable=True),
        sa.Column("range_high", _DECIMAL, nullable=True),
        sa.Column("note", sa.String(400), nullable=False),
    )
    op.create_table(
        "firm_marks",
        sa.Column("mark_id", sa.String(64), primary_key=True),
        sa.Column("hub", sa.String(16), nullable=False),
        sa.Column("period_label", sa.String(16), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("value", _DECIMAL, nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("note", sa.String(200), nullable=False),
        sa.Column("entered_by", sa.String(64), nullable=False),
        sa.Column("entered_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_firm_marks_hub_period", "firm_marks", ["hub", "period_label", "entered_at_utc"]
    )
    op.create_table(
        "valuation_snapshots",
        sa.Column("snapshot_id", sa.String(64), primary_key=True),
        sa.Column("as_of_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("demo_desk", sa.Boolean(), nullable=False),
        sa.Column("simulated", sa.Boolean(), nullable=False),
        sa.Column("quality_class", sa.String(16), nullable=False),
        sa.Column("fx_method", sa.String(16), nullable=False),
        sa.Column("assumption_version_id", sa.String(64), nullable=True),
        sa.Column("curve_as_of_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fx_as_of_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rates_as_of_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("book_as_of_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tariff_documents", sa.JSON(), nullable=False),
        sa.Column("input_count", sa.Integer(), nullable=False),
        sa.Column("inputs_sha256", sa.String(64), nullable=False),
    )
    op.create_table(
        "valuation_snapshot_inputs",
        sa.Column(
            "snapshot_id",
            sa.String(64),
            sa.ForeignKey("valuation_snapshots.snapshot_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("input_key", sa.String(160), primary_key=True),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("input_class", sa.String(16), nullable=False),
        sa.Column("value_text", sa.String(48), nullable=True),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("as_of_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_family", sa.String(64), nullable=True),
        sa.Column("source_ref", sa.String(200), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("detail_json", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("valuation_snapshot_inputs")
    op.drop_table("valuation_snapshots")
    op.drop_index("ix_firm_marks_hub_period", table_name="firm_marks")
    op.drop_table("firm_marks")
    op.drop_table("assumption_values")
    op.drop_table("assumption_set_versions")
    op.drop_table("assumption_sets")
