"""What an LNG cargo's ETA rests on (LNG-2, lesson P3 "estimates say they are estimates").

Adds to ``lng_cargoes``, all nullable:

- ``eta_basis``: what the ETA is, as the source states it (``master_notice``,
  ``ais_declared``, ``feed_estimate``, ``schedule``, ``manual``); ``NULL`` is "not stated".
- ``eta_confidence``: ``high``, ``medium`` or ``low`` as the source states it.
- ``eta_source``: the system whose file last supplied the ETA.
- ``eta_recorded_at_utc``: when that file was stored, so a message can say how old the ETA is.

Expand-only; the downgrade drops only these columns.
"""

import sqlalchemy as sa

from alembic import op

revision = "0080_lng_eta_basis"
down_revision = "0079_licensed_data_use"
branch_labels = None
depends_on = None
# Reversibility, printed by the gated upgrade (scripts/ops/upgrade_database.py).
reversibility = "reversible"

_COLUMNS = (
    ("eta_basis", sa.String(24)),
    ("eta_confidence", sa.String(8)),
    ("eta_source", sa.String(32)),
    ("eta_recorded_at_utc", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    with op.batch_alter_table("lng_cargoes") as batch:
        for name, kind in _COLUMNS:
            batch.add_column(sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("lng_cargoes") as batch:
        for name, _kind in reversed(_COLUMNS):
            batch.drop_column(name)
