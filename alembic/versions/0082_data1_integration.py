"""DATA-1 data integration: a change feed that never skips a committed event; ERP references.

``market_events.writer_txid`` (BIGINT, nullable): the id of the transaction that wrote the
row. On PostgreSQL it defaults to ``pg_current_xact_id()``, so no writer has to set it. The
change feed (``GET /api/market/changes``) orders by (``writer_txid``, ``seq``) and serves
only rows whose writer transaction is older than the oldest transaction still open
(``pg_snapshot_xmin``): every such row is committed or gone for good, so a later read never
finds a new row before a cursor it already handed out. Ordering by ``seq`` alone would skip
an event whose transaction took its ``seq`` first and committed last. Rows written before
this migration keep ``NULL`` and sort first, by ``seq``. On SQLite (tests, one writer) the
column stays ``NULL`` and the order is ``seq``.

Index ``ix_market_events_feed`` (``writer_txid``, ``seq``) serves the feed's keyset paging.

``erp_references`` (ADR Decision 33): counterparty and invoice references imported from the
firm's ERP through the ``erp.counterparties.v1`` and ``erp.invoices.v1`` contracts, one row per
(system, kind, external id), for reconciliation only (nothing posts or pays).

Expand-only: a nullable column, an index and a new table; the downgrade drops only those.
"""

import sqlalchemy as sa

from alembic import op

revision = "0082_data1_integration"
# P-17 adds 0081 in parallel; the integrator re-points this onto it.
down_revision = "0081_change_requests"
branch_labels = None
depends_on = None
# Reversibility, printed by the gated upgrade (scripts/ops/upgrade_database.py).
reversibility = "reversible"

_DEFAULT = "(pg_current_xact_id()::text::bigint)"


def upgrade() -> None:
    with op.batch_alter_table("market_events") as batch:
        batch.add_column(sa.Column("writer_txid", sa.BigInteger(), nullable=True))
    if op.get_bind().dialect.name == "postgresql":
        # Set after the column exists, so the rows already held keep NULL (no rewrite).
        op.execute(f"ALTER TABLE market_events ALTER COLUMN writer_txid SET DEFAULT {_DEFAULT}")
    op.create_index("ix_market_events_feed", "market_events", ["writer_txid", "seq"])
    op.create_table(
        "erp_references",
        sa.Column("reference_id", sa.String(200), primary_key=True),
        sa.Column("system", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("external_id", sa.String(96), nullable=False),
        sa.Column("counterparty_id", sa.String(64), nullable=True),
        sa.Column("counterparty_external_id", sa.String(96), nullable=True),
        sa.Column("trade_ref", sa.String(128), nullable=True),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("source_reference", sa.String(256), nullable=False),
        sa.Column("first_imported_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_changed_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_erp_references_system_kind", "erp_references", ["system", "kind"])
    op.create_index("ix_erp_references_counterparty", "erp_references", ["counterparty_id"])


def downgrade() -> None:
    op.drop_index("ix_erp_references_counterparty", table_name="erp_references")
    op.drop_index("ix_erp_references_system_kind", table_name="erp_references")
    op.drop_table("erp_references")
    op.drop_index("ix_market_events_feed", table_name="market_events")
    with op.batch_alter_table("market_events") as batch:
        batch.drop_column("writer_txid")
