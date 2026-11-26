"""Rules every migration follows, and the helper that keeps the index rule easy to follow.

Plan section 3.10 (change discipline): migrations are a gated step, run with
``lock_timeout`` and ``statement_timeout`` (``alembic/env.py``), each declares whether it
can be undone (``reversibility``, see ``scripts/dev/declare_migration_reversibility.py``),
and an index on a large table is built without blocking writes. The contract test
``tests/contract/test_migration_reversibility.py`` enforces all of it on every migration
after ``RULES_FROM_REVISION``.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
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


DEFAULT_LOCK_TIMEOUT = "10s"
DEFAULT_STATEMENT_TIMEOUT = "1h"
_DURATION = re.compile(r"^\d{1,7}(ms|s|min|h)?$")


def migration_timeouts(attributes: Mapping[str, Any] | None = None) -> tuple[str, str]:
    """``(lock_timeout, statement_timeout)`` for a migration session on PostgreSQL.

    From the gated upgrade's options (``attributes``), else
    ``EUROGAS_NEXUS_MIGRATION_LOCK_TIMEOUT`` / ``EUROGAS_NEXUS_MIGRATION_STATEMENT_TIMEOUT``,
    else 10 s and 1 h. A value is a PostgreSQL duration (``500ms``, ``10s``, ``5min``,
    ``2h``); anything else is refused rather than interpolated into SQL.
    """

    attributes = attributes or {}
    lock = str(
        attributes.get("lock_timeout")
        or os.environ.get("EUROGAS_NEXUS_MIGRATION_LOCK_TIMEOUT")
        or DEFAULT_LOCK_TIMEOUT
    ).strip()
    statement = str(
        attributes.get("statement_timeout")
        or os.environ.get("EUROGAS_NEXUS_MIGRATION_STATEMENT_TIMEOUT")
        or DEFAULT_STATEMENT_TIMEOUT
    ).strip()
    for name, value in (("lock_timeout", lock), ("statement_timeout", statement)):
        if not _DURATION.match(value):
            raise ValueError(
                f"{name} must be a duration such as 10s, 500ms, 5min or 2h (got {value!r})"
            )
    return lock, statement


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
        # The autocommit connection: the one taken before the block would open a transaction
        # again, and CREATE INDEX CONCURRENTLY refuses to run inside one.
        autocommit = op.get_bind()
        _end_leftover_transaction(autocommit)
        invalid = autocommit.execute(
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
        _end_leftover_transaction(op.get_bind())
        op.drop_index(name, table_name=table, postgresql_concurrently=True, if_exists=True)


def _end_leftover_transaction(connection: Any) -> None:
    """End the server transaction Alembic's autocommit block leaves open with pg8000.

    Entering the block, Alembic commits and then reads the isolation level; pg8000 runs that
    query in a new transaction (it is not yet in autocommit mode), and switching to
    autocommit afterwards does not end it, so ``CREATE INDEX CONCURRENTLY`` would fail with
    "cannot run inside a transaction block". A ``COMMIT`` here ends it; with no transaction
    open PostgreSQL only notes a warning.
    """

    connection.exec_driver_sql("COMMIT")


__all__ = [
    "DEFAULT_LOCK_TIMEOUT",
    "DEFAULT_STATEMENT_TIMEOUT",
    "LARGE_TABLES",
    "REVERSIBILITY_VALUES",
    "RULES_FROM_REVISION",
    "create_index_nonblocking",
    "drop_index_nonblocking",
    "migration_timeouts",
]
