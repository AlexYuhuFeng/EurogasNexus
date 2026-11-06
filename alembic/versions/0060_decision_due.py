"""Decision deadline on a decision case (#58): nullable, legacy cases keep none."""

import sqlalchemy as sa

from alembic import op

revision = "0060_decision_due"
down_revision = "0059_functional_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "decision_cases",
        sa.Column("decision_due_at_utc", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("decision_cases", "decision_due_at_utc")
