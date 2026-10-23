"""Bind newly tracked jobs to stable identities; legacy jobs remain quarantined."""

import sqlalchemy as sa

from alembic import op

revision = "0041_job_owner_identity"
down_revision = "0040_strategy_owner_sharing"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("job_records") as batch:
        batch.add_column(sa.Column("owner_principal_id", sa.String(80), nullable=True))
        batch.create_foreign_key(
            "fk_job_owner_identity",
            "identity_principals",
            ["owner_principal_id"],
            ["principal_id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_job_records_owner_principal_id", ["owner_principal_id"])


def downgrade():
    with op.batch_alter_table("job_records") as batch:
        batch.drop_index("ix_job_records_owner_principal_id")
        batch.drop_constraint("fk_job_owner_identity", type_="foreignkey")
        batch.drop_column("owner_principal_id")
