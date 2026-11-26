"""Rules every migration follows, and the helper that keeps the index rule easy to follow.

Plan section 3.10 (change discipline): migrations are a gated step, run with
``lock_timeout`` and ``statement_timeout`` (``alembic/env.py``), each declares whether it
can be undone (``reversibility``, see ``scripts/dev/declare_migration_reversibility.py``),
and an index on a large table is built without blocking writes. The contract test
``tests/contract/test_migration_reversibility.py`` enforces all of it on every migration
after ``RULES_FROM_REVISION``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

#: The rules apply to migrations after this one; older migrations are not rewritten, and
#: the ones that built an index on a large table inside the transaction are listed, with
#: what that meant for an operator, in the contract test.
RULES_FROM_REVISION = "0094_option_settlements"

REVERSIBILITY_VALUES = ("reversible", "conditional", "no-op", "irreversible")

#: Tables that grow with time (observations, quotes, revisions, raw pages, events, audit).
#: ``CREATE INDEX`` on one of them holds a lock that blocks every write for as long as the
#: build takes (minutes on a year of history), so ingestion and the desk stall. On
#: PostgreSQL they are indexed ``CONCURRENTLY``, outside the migration's transaction.
LARGE_TABLES = frozenset(
    {
        "audit_events",
        "capacity_observations",
        "cost_observations",
        "flow_observations",
        "forecast_observations",
        "fx_observations",
        "interest_rate_observations",
        "lng_observations",
        "market_event_deliveries",
        "market_events",
        "market_observations",
        "market_quotes",
        "market_trades",
        "observation_revisions",
        "power_observations",
        "raw_payload_archives",
        "screen_order_observations",
        "storage_inventory_observations",
        "storage_observations",
    }
)


def create_index_nonblocking(
    name: str,
    table: str,
    columns: Sequence[Any],
    *,
    unique: bool = False,
    **kwargs: Any,
) -> None:
    """Create an index without blocking writes on PostgreSQL; a plain index elsewhere.

    On PostgreSQL the build runs ``CREATE INDEX CONCURRENTLY IF NOT EXISTS`` in an
    autocommit block (it cannot run inside a transaction). If it fails part-way it leaves an
    invalid index behind; ``IF NOT EXISTS`` would then skip it, so a failed build is dropped
    first on the next attempt. Call it from a migration's ``upgrade()``.
    """

    from alembic import op

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        op.create_index(name, table, list(columns), unique=unique, **kwargs)
        return
    import sqlalchemy as sa

    with op.get_context().autocommit_block():
        invalid = bind.execute(
            sa.text(
                "SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
                "WHERE c.relname = :name AND NOT i.indisvalid"
            ),
            {"name": name},
        ).first()
        if invalid is not None:
            op.execute(sa.text(f'DROP INDEX CONCURRENTLY IF EXISTS "{name}"'))
        op.create_index(
            name,
            table,
            list(columns),
            unique=unique,
            postgresql_concurrently=True,
            if_not_exists=True,
            **kwargs,
        )


def drop_index_nonblocking(name: str, table: str) -> None:
    """The matching downgrade: ``DROP INDEX CONCURRENTLY`` on PostgreSQL."""

    from alembic import op

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        op.drop_index(name, table_name=table)
        return
    with op.get_context().autocommit_block():
        op.drop_index(name, table_name=table, postgresql_concurrently=True, if_exists=True)


__all__ = [
    "LARGE_TABLES",
    "REVERSIBILITY_VALUES",
    "RULES_FROM_REVISION",
    "create_index_nonblocking",
    "drop_index_nonblocking",
]
