"""Revision history for power, and the re-split reason for ENTSOG capacity ranges.

Two checks on ``observation_revisions`` are widened and one nullable column is added:

- ``reason`` also takes ``range_resplit``: ENTSOG re-publishes a capacity validity range
  that a later-received overlapping range had covered; the range's receipt moves forward
  and the version it had is kept (docs/operations/DATA_REVISIONS.md);
- ``observation_table`` also takes ``power_observations``: ENTSO-E and Elexon revise
  actual load and generation, and the replaced value is now kept;
- ``power_observations.revised_at_utc``: when the current value was received if it
  replaced an earlier one (``published_at_utc`` stays the first version's availability).

Expand-only. The downgrade refuses while any history row uses what it would take away.
"""

import sqlalchemy as sa

from alembic import op

revision = "0063_resplit_power_revisions"
down_revision = "0062_observation_revisions"
branch_labels = None
depends_on = None

_REASON = "ck_observation_revisions_reason"
_TABLE = "ck_observation_revisions_table"
_GAS_TABLES = (
    "'flow_observations', 'capacity_observations', 'storage_observations', 'lng_observations'"
)


def upgrade() -> None:
    with op.batch_alter_table("observation_revisions", recreate="auto") as batch:
        batch.drop_constraint(_REASON, type_="check")
        batch.drop_constraint(_TABLE, type_="check")
        batch.create_check_constraint(
            _REASON, "reason IN ('value_changed', 'period_closed', 'range_resplit')"
        )
        batch.create_check_constraint(
            _TABLE, f"observation_table IN ({_GAS_TABLES}, 'power_observations')"
        )
    op.add_column(
        "power_observations",
        sa.Column("revised_at_utc", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    count = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM observation_revisions WHERE reason = 'range_resplit' "
            "OR observation_table = 'power_observations'"
        )
    ).scalar()
    if count:
        raise RuntimeError(
            f"observation_revisions holds {count} power or re-split records; export them "
            "before downgrading below 0063_resplit_power_revisions."
        )
    with op.batch_alter_table("power_observations") as batch:
        batch.drop_column("revised_at_utc")
    with op.batch_alter_table("observation_revisions", recreate="auto") as batch:
        batch.drop_constraint(_REASON, type_="check")
        batch.drop_constraint(_TABLE, type_="check")
        batch.create_check_constraint(_REASON, "reason IN ('value_changed', 'period_closed')")
        batch.create_check_constraint(_TABLE, f"observation_table IN ({_GAS_TABLES})")
