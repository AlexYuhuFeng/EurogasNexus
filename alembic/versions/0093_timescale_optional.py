"""Optional TimescaleDB Community Edition for the high-volume time-series tables (ADR 39).

Does nothing unless ``EUROGAS_NEXUS_TIMESCALE`` is ``auto`` or ``require`` and the server is
PostgreSQL with the ``timescaledb`` extension available, preloaded, 2.13 or later, and the
Community Edition loaded (``timescaledb.license = timescale``). Then it creates the extension
and makes ``raw_payload_archives``, ``market_quotes`` and ``market_trades`` hypertables with
compression policies, widening each primary key from ``(id)`` to ``(id, time)``. The
observation tables, the outbox and the audit log stay plain tables; the reasons are in
``eurogas_nexus.db.timescale.SKIPPED_TABLES``. The default ``off``, SQLite and PostgreSQL
without the extension leave the schema unchanged.

The logic is ``eurogas_nexus.db.timescale.apply``, idempotent, so an operator who installs
the extension after this revision has run converts with ``scripts/ops/timescale.py apply``.

Downgrade: a no-op. Where nothing was converted there is nothing to undo. Where tables were
converted they stay hypertables: turning a hypertable back into a plain table means copying
every row into a new table, which is an operator's maintenance task, not a migration step
(docs/deployment/TIMESCALEDB.md). Downgrading further, past revisions that created or
altered these three tables, has not been tried on a hypertable.
"""

from alembic import context, op

revision = "0093_timescale_optional"
down_revision = "0092_lng_berth_rules"
branch_labels = None
depends_on = None
# Reversibility, printed by the gated upgrade (scripts/ops/upgrade_database.py).
reversibility = "no-op"
reversibility_note = (
    'Converted hypertables stay hypertables; returning them to plain tables is an operator '
    'task (docs/deployment/TIMESCALEDB.md), not a migration step.'
)


def upgrade() -> None:
    from eurogas_nexus.db.timescale import apply, mode_from_env

    mode = mode_from_env()
    if mode == "off":
        return
    try:
        offline = context.is_offline_mode()
    except Exception:  # noqa: BLE001 - outside an Alembic run (tests drive op directly)
        offline = False
    if offline:
        # Offline SQL cannot read the catalogue the decision rests on.
        return
    apply(op.get_bind(), mode=mode)


def downgrade() -> None:
    """Deliberately nothing: see the module docstring."""
