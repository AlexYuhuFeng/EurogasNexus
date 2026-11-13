"""Append-only revision history for flow, capacity, storage and LNG observations.

ENTSOG and GIE revise provisional values. The observation row keeps the provider's latest
value (and its first receipt in ``observed_at_utc``); the value it replaces is written to
``observation_revisions`` in the same transaction. ``revised_at_utc`` says when the current
value was received. Expand-only: one new table and one nullable column per table.
"""

import sqlalchemy as sa

from alembic import op

revision = "0062_observation_revisions"
down_revision = "0061_audit_keyset_index"
branch_labels = None
depends_on = None

_TABLES = (
    "flow_observations",
    "capacity_observations",
    "storage_observations",
    "lng_observations",
)


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("revised_at_utc", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "observation_revisions",
        sa.Column("revision_id", sa.String(64), primary_key=True),
        sa.Column("observation_table", sa.String(64), nullable=False),
        sa.Column("observation_id", sa.String(128), nullable=False),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("changed_fields", sa.JSON(), nullable=False),
        sa.Column("prior_row_json", sa.JSON(), nullable=False),
        sa.Column("prior_received_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prior_source_reference", sa.String(128), nullable=False),
        sa.Column("superseding_source_reference", sa.String(128), nullable=False),
        sa.Column("recorded_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "reason IN ('value_changed', 'period_closed')",
            name="ck_observation_revisions_reason",
        ),
        sa.CheckConstraint(
            "observation_table IN ('flow_observations', 'capacity_observations', "
            "'storage_observations', 'lng_observations')",
            name="ck_observation_revisions_table",
        ),
    )
    op.create_index(
        "ix_observation_revisions_observation",
        "observation_revisions",
        ["observation_table", "observation_id", "superseded_at_utc"],
    )
    op.create_index(
        "ix_observation_revisions_recorded",
        "observation_revisions",
        ["observation_table", "recorded_at_utc"],
    )


def downgrade() -> None:
    # Refuse to discard recorded history: a downgrade with revisions would lose the only
    # copy of the superseded values.
    bind = op.get_bind()
    count = bind.execute(sa.text("SELECT COUNT(*) FROM observation_revisions")).scalar()
    if count:
        raise RuntimeError(
            f"observation_revisions holds {count} superseded values; export them before "
            "downgrading below 0062_observation_revisions."
        )
    op.drop_index("ix_observation_revisions_recorded", table_name="observation_revisions")
    op.drop_index("ix_observation_revisions_observation", table_name="observation_revisions")
    op.drop_table("observation_revisions")
    for table in _TABLES:
        with op.batch_alter_table(table) as batch:
            batch.drop_column("revised_at_utc")
