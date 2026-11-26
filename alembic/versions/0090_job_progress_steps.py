"""Background jobs: step progress, heartbeat and runner on ``job_records``.

Long-running work (dataset builds, research runs) now runs after the request returns, so the
job row is what the user follows. It gains:

- ``progress_step`` / ``progress_total`` / ``progress_label``: "step 3 of 6, reading prices",
  written as the work advances (the label is a stable step code the client translates);
- ``runner_id``: the server process running the job (host, pid and boot token);
- ``heartbeat_at_utc``: refreshed while that process works on it, so a job whose process died
  (restart, crash, deploy) is failed with a reason instead of showing RUNNING for ever.

All nullable; existing rows and jobs tracked inside a request keep them empty. Expand-only; the
downgrade drops only what this revision adds.
"""

import sqlalchemy as sa

from alembic import op

revision = "0090_job_progress_steps"
down_revision = "0089_alert_reader_state"
branch_labels = None
depends_on = None
# Reversibility, printed by the gated upgrade (scripts/ops/upgrade_database.py).
reversibility = "reversible"


def upgrade() -> None:
    with op.batch_alter_table("job_records") as batch:
        batch.add_column(sa.Column("progress_step", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("progress_total", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("progress_label", sa.String(64), nullable=True))
        batch.add_column(sa.Column("runner_id", sa.String(128), nullable=True))
        batch.add_column(
            sa.Column("heartbeat_at_utc", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("job_records") as batch:
        batch.drop_column("heartbeat_at_utc")
        batch.drop_column("runner_id")
        batch.drop_column("progress_label")
        batch.drop_column("progress_total")
        batch.drop_column("progress_step")
