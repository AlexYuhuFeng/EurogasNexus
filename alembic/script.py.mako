"""${message}"""

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}
# Reversibility, printed by the gated upgrade (scripts/ops/upgrade_database.py): one of
# "reversible", "conditional" (refuses when data would be lost), "no-op" (nothing to undo)
# or "irreversible" (restore the backup). Every value but "reversible" needs a note.
reversibility = "reversible"
# reversibility_note = "..."
#
# An index on a large table (eurogas_nexus.db.migration_rules.LARGE_TABLES) is built with
# eurogas_nexus.db.migration_rules.create_index_nonblocking, never op.create_index.


def upgrade() -> None:
    """Apply schema changes."""


def downgrade() -> None:
    """Revert schema changes."""
