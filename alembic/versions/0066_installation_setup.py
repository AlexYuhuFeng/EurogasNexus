"""First-run setup: one row per installation recording the welcome flow's progress.

- ``installation_setup``: the state of the first administrator's setup flow (not started,
  in progress, completed or dismissed), the step last shown, the steps visited, and who
  configured it (an administrator, the demo profile, or the environment for a headless
  install). Keys entered in the flow are not here: they go to the existing encrypted
  provider-credential store.

Expand-only; SQLite and PostgreSQL. The downgrade drops only this table.
"""

import sqlalchemy as sa

from alembic import op

revision = "0066_installation_setup"
down_revision = "0065_local_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "installation_setup",
        sa.Column("setup_id", sa.String(32), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("current_step", sa.String(32), nullable=True),
        sa.Column("steps_visited", sa.JSON(), nullable=False),
        sa.Column("configured_by", sa.String(32), nullable=False),
        sa.Column("updated_by", sa.String(80), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('not_started', 'in_progress', 'completed', 'dismissed')",
            name="ck_installation_setup_status",
        ),
    )


def downgrade() -> None:
    op.drop_table("installation_setup")
