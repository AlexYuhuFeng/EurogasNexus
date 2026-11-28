"""Publisher consents: an administrator's withdrawal of a written consent, and polite fetching.

- ``publisher_consent_states``: one row per publisher whose shipped consent record
  (``reference_data/publisher_consents.toml``) an administrator withdrew or restored: when, by
  whom and why. No row means the shipped record is in force.
- ``watched_publications``: three more states (``consent_withdrawn``, ``not_implemented``,
  ``site_refuses``), the count of failed checks in a row and the time before which the next
  check waits (back-off on errors, a publisher's ``Retry-After``).

Expand-only; the downgrade drops the table and the two columns. It leaves the widened state
check in place (no row is rewritten in a migration); code of the earlier version never writes
the three new states. Chained after ``0101_regas_auction_cases``.
"""

import sqlalchemy as sa

from alembic import op

revision = "0102_publisher_consents"
down_revision = "0101_regas_auction_cases"
branch_labels = None
depends_on = None
# Reversibility, printed by the gated upgrade (scripts/ops/upgrade_database.py).
reversibility = "reversible"
reversibility_note = (
    "The downgrade forgets which consents an administrator withdrew (the audit log keeps the "
    "withdrawal) and the failure count of each watched publication; consented publications "
    "would be fetched again after a downgrade, so withdraw them again or switch the watch off "
    "(EUROGAS_NEXUS_PUBLICATION_WATCH=off) first."
)

_EARLIER_STATES = ("'current', 'needs_confirmation', 'unreachable', 'never_fetched', "
                   "'hand_maintained', 'link_only'")
_NEW_STATES = _EARLIER_STATES + ", 'consent_withdrawn', 'not_implemented', 'site_refuses'"


def upgrade() -> None:
    op.create_table(
        "publisher_consent_states",
        sa.Column("publisher_id", sa.String(64), primary_key=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("withdrawn_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_by", sa.String(128), nullable=True),
        sa.Column("reason", sa.String(500), nullable=False, server_default=""),
        sa.Column("restored_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("restored_by", sa.String(128), nullable=True),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("state IN ('withdrawn', 'in_force')",
                           name="ck_publisher_consent_states_state"),
    )
    with op.batch_alter_table("watched_publications") as batch:
        batch.drop_constraint("ck_watched_publications_state", type_="check")
        batch.create_check_constraint("ck_watched_publications_state", f"state IN ({_NEW_STATES})")
        batch.add_column(sa.Column("consecutive_failures", sa.Integer(), nullable=False,
                                   server_default="0"))
        batch.add_column(sa.Column("next_check_at_utc", sa.DateTime(timezone=True),
                                   nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("watched_publications") as batch:
        batch.drop_column("next_check_at_utc")
        batch.drop_column("consecutive_failures")
    op.drop_table("publisher_consent_states")
