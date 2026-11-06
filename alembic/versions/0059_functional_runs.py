"""Frozen functional runs and research model versions, sharing the Job lifecycle."""

import sqlalchemy as sa

from alembic import op

revision = "0059_functional_runs"
down_revision = "0058_contract_financing_tranches"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "functional_runs",
        sa.Column("run_id", sa.String(64), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(80),
            sa.ForeignKey("identity_principals.principal_id"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            sa.String(64),
            sa.ForeignKey("job_records.job_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(80), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("source_scopes", sa.JSON(), nullable=False),
        sa.Column("deadline_seconds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_functional_owner_key"),
    )
    op.create_index("ix_functional_runs_owner_id", "functional_runs", ["owner_id"])
    op.create_table(
        "functional_models",
        sa.Column("model_id", sa.String(64), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(80),
            sa.ForeignKey("identity_principals.principal_id"),
            nullable=False,
        ),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("functional_runs.run_id"), nullable=False),
        sa.Column("target", sa.String(80), nullable=False),
        sa.Column("version_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("review", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "owner_id", "target", "version_hash", name="uq_functional_model_version"
        ),
    )
    op.create_index("ix_functional_models_owner_id", "functional_models", ["owner_id"])
    op.create_table(
        "functional_dependencies",
        sa.Column(
            "run_id", sa.String(64), sa.ForeignKey("functional_runs.run_id"), primary_key=True
        ),
        sa.Column("reference", sa.String(256), primary_key=True),
        sa.Column("version_hash", sa.String(128), nullable=False),
        sa.Column("latest_hash", sa.String(128), nullable=False),
        sa.Column("stale", sa.Boolean(), nullable=False),
    )
    op.create_index(
        "ix_functional_dependencies_reference", "functional_dependencies", ["reference"]
    )


def downgrade():
    op.drop_table("functional_dependencies")
    op.drop_table("functional_models")
    op.drop_table("functional_runs")
