"""SCHED-1: a nomination status says whom it is against, which way and under which codes.

``gas_day_nomination_events`` gains six nullable columns, filled by the ``etrm.nominations.v1``
import where the scheduling system or the TSO's matching response gives them (optional
columns within the version, ``docs/integration/ETRM_ERP_IMPORT_CONTRACTS.md``):

- ``counterparty``: the counterparty the line is nominated against;
- ``direction``: ``in`` (the firm receives) or ``out``;
- ``point``: the interconnection or trading point (NULL: the hub's virtual trading point);
- ``shipper_code``: the firm's own shipper code used;
- ``counterparty_shipper_code``: the counterparty's shipper code nominated against;
- ``counterparty_quantity_mwh``: the counterparty's own nominated quantity, as the TSO's
  matching reports it (the lesser rule).

Without them the reconciliation (``application/gas_day_reconciliation``) could not tell a
counterparty, direction or shipper-code break from a quantity one. Rows already held keep
NULL and read as "not held". No table is added.

Expand-only; the downgrade drops only these columns. It follows TAR-1's 0083.
"""

import sqlalchemy as sa

from alembic import op

revision = "0085_sched1_nomination_matching"
down_revision = "0083_tar1_tariff_book"
branch_labels = None
depends_on = None
# Reversibility, printed by the gated upgrade (scripts/ops/upgrade_database.py).
reversibility = "reversible"

_COLUMNS = (
    ("counterparty", sa.String(160)),
    ("direction", sa.String(8)),
    ("point", sa.String(160)),
    ("shipper_code", sa.String(64)),
    ("counterparty_shipper_code", sa.String(64)),
    ("counterparty_quantity_mwh", sa.Float()),
)


def upgrade() -> None:
    with op.batch_alter_table("gas_day_nomination_events") as batch:
        for name, kind in _COLUMNS:
            batch.add_column(sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("gas_day_nomination_events") as batch:
        for name, _kind in reversed(_COLUMNS):
            batch.drop_column(name)
