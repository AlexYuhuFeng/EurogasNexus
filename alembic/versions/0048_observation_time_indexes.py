"""Index the physical observation tables by source and observation time.

Freshness, "latest run" and source-health reads filter ENTSOG flows and capacities, AGSI
storage and ALSI LNG by ``source_system`` and order by ``observed_at_utc``. Entity/period
indexes exist since 0010 and 0012; nothing served the source/time path, so those reads
scanned the table as history grew.

The indexes are built inside the migration transaction (``env.py`` runs each migration in
one), which briefly blocks writes to these four tables; run the upgrade in a maintenance
window or between ingestion cycles on a large installation.
"""

import sqlalchemy as sa

from alembic import op

revision = "0048_observation_time_indexes"
down_revision = "0047_user_preferences"
branch_labels = None
depends_on = None

TABLES = ("flow_observations", "capacity_observations", "storage_observations", "lng_observations")


def upgrade() -> None:
    for table in TABLES:
        op.create_index(
            f"ix_{table}_source_observed",
            table,
            ["source_system", sa.text("observed_at_utc DESC")],
        )


def downgrade() -> None:
    for table in TABLES:
        op.drop_index(f"ix_{table}_source_observed", table_name=table)
