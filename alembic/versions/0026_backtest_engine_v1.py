"""Add backtest experiments, decision events, series and attribution.

Revision ID: 0026_backtest_engine_v1
Revises: 0025_strategy_registry_v1
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026_backtest_engine_v1"
down_revision: str | None = "0025_strategy_registry_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backtest_experiments",
        sa.Column("experiment_id", sa.String(128), nullable=False),
        sa.Column("strategy_id", sa.String(128), nullable=False),
        sa.Column("base_strategy_version_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("experiment_type", sa.String(32), nullable=False),
        sa.Column("evaluation_period_json", sa.JSON(), nullable=False),
        sa.Column("run_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.strategy_id"]),
        sa.ForeignKeyConstraint(
            ["base_strategy_version_id"],
            ["strategy_versions.strategy_version_id"],
        ),
        sa.PrimaryKeyConstraint("experiment_id"),
    )
    op.create_index(
        "ix_backtest_experiments_strategy_id",
        "backtest_experiments",
        ["strategy_id"],
    )
    op.create_table(
        "backtest_decision_events",
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("experiment_id", sa.String(128), nullable=True),
        sa.Column("decision_sequence", sa.Integer(), nullable=False),
        sa.Column("decision_time_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gas_day", sa.String(16), nullable=False),
        sa.Column("gas_day_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gas_day_end_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("candidate_action_for_review", sa.String(64), nullable=True),
        sa.Column("weighted_score", sa.Float(), nullable=True),
        sa.Column("day_ahead_average_gbp_mwh", sa.Float(), nullable=True),
        sa.Column("intraday_average_gbp_mwh", sa.Float(), nullable=True),
        sa.Column(
            "intraday_vs_day_ahead_spread_gbp_mwh", sa.Float(), nullable=True
        ),
        sa.Column("allocation_targets", sa.JSON(), nullable=False),
        sa.Column("gross_indicative_pnl_gbp", sa.Float(), nullable=False),
        sa.Column("modeled_costs_gbp", sa.Float(), nullable=False),
        sa.Column("net_indicative_pnl_gbp", sa.Float(), nullable=False),
        sa.Column(
            "cumulative_net_indicative_pnl_gbp", sa.Float(), nullable=False
        ),
        sa.Column("ending_exposure_mwh_per_day", sa.Float(), nullable=False),
        sa.Column("missing_inputs", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("price_evidence_refs", sa.JSON(), nullable=False),
        sa.Column("fx_evidence_refs", sa.JSON(), nullable=False),
        sa.Column("cost_evidence_refs", sa.JSON(), nullable=False),
        sa.Column("resource_evidence_refs", sa.JSON(), nullable=False),
        sa.Column("cost_trace", sa.JSON(), nullable=False),
        sa.Column("attribution", sa.JSON(), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.Column("human_review_required", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["strategy_runs.run_id"]),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint(
            "run_id", "decision_sequence", name="uq_backtest_event_seq"
        ),
    )
    op.create_index(
        "ix_backtest_events_run_id", "backtest_decision_events", ["run_id"]
    )
    op.create_index(
        "ix_backtest_events_decision_time",
        "backtest_decision_events",
        ["decision_time_utc"],
    )
    op.create_table(
        "backtest_series",
        sa.Column("series_point_id", sa.String(128), nullable=False),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("decision_sequence", sa.Integer(), nullable=False),
        sa.Column("decision_time_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gas_day", sa.String(16), nullable=False),
        sa.Column("gross_indicative_pnl_gbp", sa.Float(), nullable=False),
        sa.Column("modeled_costs_gbp", sa.Float(), nullable=False),
        sa.Column("net_indicative_pnl_gbp", sa.Float(), nullable=False),
        sa.Column(
            "cumulative_net_indicative_pnl_gbp", sa.Float(), nullable=False
        ),
        sa.Column("ending_exposure_mwh_per_day", sa.Float(), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["strategy_runs.run_id"]),
        sa.PrimaryKeyConstraint("series_point_id"),
        sa.UniqueConstraint(
            "run_id", "decision_sequence", name="uq_backtest_series_seq"
        ),
    )
    op.create_index("ix_backtest_series_run_id", "backtest_series", ["run_id"])
    op.create_table(
        "backtest_attribution",
        sa.Column("attribution_id", sa.String(128), nullable=False),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("decision_time_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dimension", sa.String(32), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("gross_indicative_pnl_gbp", sa.Float(), nullable=False),
        sa.Column("modeled_costs_gbp", sa.Float(), nullable=False),
        sa.Column("net_indicative_pnl_gbp", sa.Float(), nullable=False),
        sa.Column("quantity_mwh_per_day", sa.Float(), nullable=True),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["strategy_runs.run_id"]),
        sa.ForeignKeyConstraint(
            ["event_id"], ["backtest_decision_events.event_id"]
        ),
        sa.PrimaryKeyConstraint("attribution_id"),
    )
    op.create_index(
        "ix_backtest_attribution_run_id", "backtest_attribution", ["run_id"]
    )
    op.create_index(
        "ix_backtest_attribution_event_id", "backtest_attribution", ["event_id"]
    )
    op.add_column(
        "strategy_runs",
        sa.Column("backtest_engine_version", sa.String(64), nullable=True),
    )
    op.add_column(
        "strategy_runs",
        sa.Column("experiment_id", sa.String(128), nullable=True),
    )
    op.create_foreign_key(
        "fk_strategy_runs_experiment_id",
        "strategy_runs",
        "backtest_experiments",
        ["experiment_id"],
        ["experiment_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_strategy_runs_experiment_id", "strategy_runs", type_="foreignkey"
    )
    op.drop_column("strategy_runs", "experiment_id")
    op.drop_column("strategy_runs", "backtest_engine_version")
    op.drop_index("ix_backtest_attribution_event_id", table_name="backtest_attribution")
    op.drop_index("ix_backtest_attribution_run_id", table_name="backtest_attribution")
    op.drop_table("backtest_attribution")
    op.drop_index("ix_backtest_series_run_id", table_name="backtest_series")
    op.drop_table("backtest_series")
    op.drop_index("ix_backtest_events_decision_time", table_name="backtest_decision_events")
    op.drop_index("ix_backtest_events_run_id", table_name="backtest_decision_events")
    op.drop_table("backtest_decision_events")
    op.drop_index(
        "ix_backtest_experiments_strategy_id", table_name="backtest_experiments"
    )
    op.drop_table("backtest_experiments")
