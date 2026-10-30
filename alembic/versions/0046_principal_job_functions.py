"""Add declared job functions and home office to identity principals.

Additive and nullable: existing principals keep capability-derived functions until an
administrator declares theirs. Job functions shape the experience only; they grant no
permission (roles and data scopes remain the only grants).
"""

import sqlalchemy as sa

from alembic import op

revision = "0046_principal_job_functions"
down_revision = "0045_interest_rate_observations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("identity_principals", sa.Column("job_functions", sa.JSON(), nullable=True))
    op.add_column("identity_principals", sa.Column("office", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("identity_principals", "office")
    op.drop_column("identity_principals", "job_functions")
