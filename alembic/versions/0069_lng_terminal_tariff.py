"""LNG terminal tariff register: public regulated tariffs beside the firm's own terms (CP-11).

- ``lng_terminal_tariff``: one row per published figure (terminal, service, product, charge
  basis, amount, validity, slot content, use-it-or-lose-it terms, exclusions) with its source
  document (URL, SHA-256, title, retrieved) and its review state (candidate -> reviewed, four
  eyes). Versioned: a new document adds rows, nothing is overwritten.
- ``lng_terminal_operator_terms``: per terminal operator, whether the firm has recorded the
  operator's permission to reuse its published documents (who, when, reference). Without it
  no document of that operator is read.

``lng_terminal_terms`` (the firm's own terms) is unchanged. Expand-only; the downgrade drops
only these two tables.
"""

import sqlalchemy as sa

from alembic import op

revision = "0069_lng_terminal_tariff"
down_revision = "0068_installation_setup"
branch_labels = None
depends_on = None
# Reversibility, printed by the gated upgrade (scripts/ops/upgrade_database.py).
reversibility = "reversible"


def upgrade() -> None:
    op.create_table(
        "lng_terminal_tariff",
        sa.Column("tariff_id", sa.String(64), primary_key=True),
        sa.Column("terminal_id", sa.String(64), nullable=False),
        sa.Column("operator", sa.String(64), nullable=False),
        sa.Column("terminal_name", sa.String(128), nullable=False),
        sa.Column("country", sa.String(2), nullable=True),
        sa.Column("hub", sa.String(16), nullable=False),
        sa.Column("entry_point_key", sa.String(128), nullable=True),
        sa.Column("regime", sa.String(24), nullable=False),
        sa.Column("service", sa.String(32), nullable=False),
        sa.Column("product", sa.String(24), nullable=False),
        sa.Column("charge_basis", sa.String(32), nullable=False),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("by_cargo_class", sa.JSON(), nullable=True),
        sa.Column("indexation", sa.String(24), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("period_label", sa.String(64), nullable=True),
        sa.Column("slot_days", sa.Float(), nullable=True),
        sa.Column("sendout_days", sa.Float(), nullable=True),
        sa.Column("included_storage", sa.String(64), nullable=True),
        sa.Column("uioli_notice_days", sa.Integer(), nullable=True),
        sa.Column("uioli_rule", sa.String(256), nullable=True),
        sa.Column("secondary_market", sa.String(128), nullable=True),
        sa.Column("excludes", sa.JSON(), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("retrieved_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("document_title", sa.String(256), nullable=False),
        sa.Column("review_status", sa.String(16), nullable=False),
        sa.Column("recorded_by", sa.String(128), nullable=False),
        sa.Column("reviewed_by", sa.String(128), nullable=True),
        sa.Column("reviewed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "review_status IN ('CANDIDATE', 'REVIEWED')", name="ck_lng_terminal_tariff_review"
        ),
    )
    op.create_index(
        "ix_lng_terminal_tariff_terminal", "lng_terminal_tariff", ["terminal_id", "valid_from"]
    )
    op.create_index("ix_lng_terminal_tariff_source", "lng_terminal_tariff", ["source_sha256"])
    op.create_table(
        "lng_terminal_operator_terms",
        sa.Column("operator", sa.String(64), primary_key=True),
        sa.Column("permission_state", sa.String(24), nullable=False),
        sa.Column("reference", sa.String(256), nullable=True),
        sa.Column("recorded_by", sa.String(128), nullable=True),
        sa.Column("recorded_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "permission_state IN ('needs_firm_terms', 'permitted')",
            name="ck_lng_terminal_operator_terms_state",
        ),
    )


def downgrade() -> None:
    op.drop_table("lng_terminal_operator_terms")
    op.drop_index("ix_lng_terminal_tariff_source", table_name="lng_terminal_tariff")
    op.drop_index("ix_lng_terminal_tariff_terminal", table_name="lng_terminal_tariff")
    op.drop_table("lng_terminal_tariff")
