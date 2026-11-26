"""Milestone 2 baseline revision (no-op)."""

revision = "0001_m2_baseline"
down_revision = None
branch_labels = None
depends_on = None
# Reversibility, printed by the gated upgrade (scripts/ops/upgrade_database.py).
reversibility = "no-op"
reversibility_note = 'Empty baseline: there is no schema below it to return to.'


def upgrade() -> None:
    """Apply schema changes for baseline."""


def downgrade() -> None:
    """Revert baseline schema changes."""
