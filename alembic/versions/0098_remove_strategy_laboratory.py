"""Remove the strategy laboratory, its decision-time backtests and the shadow runtime.

The owner approved removing the strategy registry, evaluation and tracks, the
decision-time "backtest" and the scheduled shadow runtime: profit is fixed at the
moment of decision, so there is no outcome for the "backtest" to prove, and the
laboratory duplicated the spread laboratory. Export any stored runs that must be
kept before applying this revision (``docs/operations/DATABASE_UPGRADE.md``,
"Data-dropping migrations"); the pre-upgrade backup also holds them.

The downgrade cannot recreate the dropped rows, so it refuses; going back means
restoring the pre-upgrade backup. The identity groups the sharing feature used
(``identity_groups`` / ``identity_group_members``) are identity infrastructure and
stay; only their strategy-share link table goes.

Dropped, in dependency order: ``strategy_group_shares``, ``strategy_track_events``,
``strategy_tracks``, the eight ``strategy_shadow_*`` tables, ``backtest_attribution``,
``backtest_series``, ``backtest_decision_events``, ``strategy_runs``,
``backtest_experiments``, ``strategy_allocation_targets``, ``strategy_alerts``,
``strategy_data_snapshots``, ``strategy_versions``, ``strategies`` and
``strategy_definitions``.
"""

import sqlalchemy as sa  # noqa: F401  (kept for the migration template's import shape)

from alembic import op

revision = "0098_remove_strategy_laboratory"
down_revision = "0097_deal_capture"
branch_labels = None
depends_on = None
# Reversibility, printed by the gated upgrade (scripts/ops/upgrade_database.py).
reversibility = "irreversible"
reversibility_note = (
    "Dropping the strategy laboratory's tables deletes its stored runs, evaluations and "
    "track history; the downgrade refuses and going back means restoring the pre-upgrade "
    "backup."
)

#: Child tables first: each drop is independent of the revision's transaction order.
_DROPPED_TABLES = (
    "strategy_group_shares",
    "strategy_track_events",
    "strategy_tracks",
    "strategy_shadow_outcomes",
    "strategy_shadow_risk_checks",
    "strategy_shadow_candidates",
    "strategy_shadow_alerts",
    "strategy_shadow_drift_snapshots",
    "strategy_shadow_evaluations",
    "strategy_shadow_monitors",
    "strategy_shadow_scheduler_heartbeat",
    "backtest_attribution",
    "backtest_series",
    "backtest_decision_events",
    "strategy_runs",
    "backtest_experiments",
    "strategy_allocation_targets",
    "strategy_alerts",
    "strategy_data_snapshots",
    "strategy_versions",
    "strategies",
    "strategy_definitions",
)


def upgrade() -> None:
    """Drop every table the removed laboratory owned."""

    for table in _DROPPED_TABLES:
        op.drop_table(table)


def downgrade() -> None:
    """Refuse: the dropped rows cannot be recreated."""

    raise RuntimeError(
        "the strategy laboratory's tables cannot be recreated; restore the pre-upgrade backup"
    )
