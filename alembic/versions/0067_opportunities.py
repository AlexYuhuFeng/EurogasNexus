"""The opportunity store (commercial design basis 2, CP-08).

- ``opportunities``: one current record per dedupe key (type, legs, delivery period, books)
  with its lifecycle (state, version, consecutive evaluations seen and missed, surfaced,
  expiry, the snapshot it was valued on, the case it was converted to).
- ``opportunity_versions``: the frozen object per version (a case points at one).
- ``opportunity_legs``, ``opportunity_checks``: the current version's arithmetic and checks.
- ``opportunity_dependencies``: the input keys each record read (outbox seam, design J.2).
- ``opportunity_user_states``: a person's dismissal (with reason) or follow, per key.
- ``opportunity_evaluations``: evaluation runs and each evaluator's status.
- ``opportunity_settings``: the organisation's thresholds (decision L5).

Expand-only; SQLite and PostgreSQL. The downgrade drops only what this revision added.
"""

import sqlalchemy as sa

from alembic import op

revision = "0067_opportunities"
down_revision = "0066_commercial_assumptions"
branch_labels = None
depends_on = None

_DECIMAL = sa.Numeric(28, 10)


def upgrade() -> None:
    op.create_table(
        "opportunities",
        sa.Column("opportunity_id", sa.String(64), primary_key=True),
        sa.Column("opp_key", sa.String(40), nullable=False, unique=True),
        sa.Column("type", sa.String(24), nullable=False),
        sa.Column("lane", sa.String(16), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("assessed_state", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("version_basis", _DECIMAL, nullable=True),
        sa.Column("claim_key", sa.String(64), nullable=False),
        sa.Column("claim_fields", sa.JSON(), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("headline_value", _DECIMAL, nullable=False),
        sa.Column("headline_unit", sa.String(32), nullable=False),
        sa.Column("value_amount", _DECIMAL, nullable=True),
        sa.Column("value_currency", sa.String(8), nullable=True),
        sa.Column("reporting_value", _DECIMAL, nullable=True),
        sa.Column("reporting_currency", sa.String(8), nullable=True),
        sa.Column("volume_value", _DECIMAL, nullable=True),
        sa.Column("volume_unit", sa.String(16), nullable=True),
        sa.Column("period_label", sa.String(16), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("quality_class", sa.String(16), nullable=False),
        sa.Column("simulated", sa.Boolean(), nullable=False),
        sa.Column("book_ids", sa.JSON(), nullable=False),
        sa.Column("source_families", sa.JSON(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("blocker_json", sa.JSON(), nullable=True),
        sa.Column("first_seen_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_evaluated_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_changed_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consecutive_seen", sa.Integer(), nullable=False),
        sa.Column("consecutive_missed", sa.Integer(), nullable=False),
        sa.Column("surfaced", sa.Boolean(), nullable=False),
        sa.Column("expires_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_reason", sa.String(32), nullable=True),
        sa.Column("snapshot_id", sa.String(64), nullable=False),
        sa.Column("evaluation_id", sa.String(64), nullable=False),
        sa.Column("evaluator", sa.String(64), nullable=False),
        sa.Column("evaluator_version", sa.String(16), nullable=False),
        sa.Column("case_id", sa.String(64), nullable=True),
        sa.Column("converted_by", sa.String(64), nullable=True),
        sa.Column("converted_at_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_opportunities_expires", "opportunities", ["expires_at_utc"])
    op.create_index("ix_opportunities_state_lane", "opportunities", ["state", "lane"])
    op.create_table(
        "opportunity_versions",
        sa.Column(
            "opportunity_id",
            sa.String(64),
            sa.ForeignKey("opportunities.opportunity_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("snapshot_id", sa.String(64), nullable=False),
        sa.Column("recorded_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
    )
    op.create_table(
        "opportunity_legs",
        sa.Column(
            "opportunity_id",
            sa.String(64),
            sa.ForeignKey("opportunities.opportunity_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("seq", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("label_key", sa.String(64), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("quantity_value", _DECIMAL, nullable=True),
        sa.Column("quantity_unit", sa.String(32), nullable=True),
        sa.Column("rate_value", _DECIMAL, nullable=True),
        sa.Column("rate_unit", sa.String(32), nullable=True),
        sa.Column("fx_value", _DECIMAL, nullable=True),
        sa.Column("fx_unit", sa.String(32), nullable=True),
        sa.Column("contribution_value", _DECIMAL, nullable=True),
        sa.Column("subtotal_value", _DECIMAL, nullable=True),
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("input_class", sa.String(16), nullable=True),
        sa.Column("source_family", sa.String(64), nullable=True),
        sa.Column("source_ref", sa.String(200), nullable=False),
        sa.Column("as_of_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "opportunity_checks",
        sa.Column(
            "opportunity_id",
            sa.String(64),
            sa.ForeignKey("opportunities.opportunity_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("seq", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("figure", sa.Text(), nullable=False),
        sa.Column("reference", sa.String(200), nullable=False),
    )
    op.create_table(
        "opportunity_dependencies",
        sa.Column(
            "opportunity_id",
            sa.String(64),
            sa.ForeignKey("opportunities.opportunity_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("input_key", sa.String(160), primary_key=True),
    )
    op.create_index(
        "ix_opportunity_dependencies_input_key", "opportunity_dependencies", ["input_key"]
    )
    op.create_table(
        "opportunity_user_states",
        sa.Column("principal_id", sa.String(64), primary_key=True),
        sa.Column("opp_key", sa.String(40), primary_key=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("reason_code", sa.String(32), nullable=True),
        sa.Column("note", sa.String(400), nullable=False),
        sa.Column("at_version", sa.Integer(), nullable=False),
        sa.Column("opportunity_type", sa.String(24), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_opportunity_user_states_key", "opportunity_user_states", ["opp_key"])
    op.create_table(
        "opportunity_evaluations",
        sa.Column("evaluation_id", sa.String(64), primary_key=True),
        sa.Column("trigger", sa.String(16), nullable=False),
        sa.Column("triggered_by", sa.String(64), nullable=False),
        sa.Column("as_of_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("snapshot_id", sa.String(64), nullable=True),
        sa.Column("demo_desk", sa.Boolean(), nullable=False),
        sa.Column("evaluators_json", sa.JSON(), nullable=False),
        sa.Column("counts_json", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_opportunity_evaluations_started", "opportunity_evaluations", ["started_at_utc"]
    )
    op.create_table(
        "opportunity_settings",
        sa.Column("setting_key", sa.String(64), primary_key=True),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("opportunity_settings")
    op.drop_index("ix_opportunity_evaluations_started", table_name="opportunity_evaluations")
    op.drop_table("opportunity_evaluations")
    op.drop_index("ix_opportunity_user_states_key", table_name="opportunity_user_states")
    op.drop_table("opportunity_user_states")
    op.drop_index("ix_opportunity_dependencies_input_key", table_name="opportunity_dependencies")
    op.drop_table("opportunity_dependencies")
    op.drop_table("opportunity_checks")
    op.drop_table("opportunity_legs")
    op.drop_table("opportunity_versions")
    op.drop_index("ix_opportunities_expires", table_name="opportunities")
    op.drop_index("ix_opportunities_state_lane", table_name="opportunities")
    op.drop_table("opportunities")
