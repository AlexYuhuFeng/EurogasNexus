"""Ontology slot columns (flow kind, capacity product/scope) and optimization runs."""

import sqlalchemy as sa

from alembic import op

revision = "0019_ontology_slots_optimization"
down_revision = "0018_provider_certifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # FlowObservation.kind — the ontology requires the nature tag as a column.
    op.add_column(
        "flow_observations",
        sa.Column("kind", sa.String(32), nullable=False, server_default="actual"),
    )
    # CapacityProfile product/scope — CAM capacity product duration + scope.
    op.add_column(
        "capacity_profiles",
        sa.Column("capacity_product", sa.String(32), nullable=True),
    )
    op.add_column(
        "capacity_profiles",
        sa.Column("capacity_scope", sa.String(32), nullable=True),
    )
    # Optimization run evidence trail (Gate 3).
    op.create_table(
        "optimization_runs",
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("optimization_type", sa.String(32), nullable=False),
        sa.Column("decision_context", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("output_snapshot", sa.JSON(), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.Column("human_review_required", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("run_id"),
    )


def downgrade() -> None:
    op.drop_table("optimization_runs")
    op.drop_column("capacity_profiles", "capacity_scope")
    op.drop_column("capacity_profiles", "capacity_product")
    op.drop_column("flow_observations", "kind")
