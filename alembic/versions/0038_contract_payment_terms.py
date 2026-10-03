"""Add the declared payment-terms carrier to upstream contracts (S2b).

Revision ID: 0038_contract_payment_terms
Revises: 0037_contract_revisions
Create Date: 2026-10-04

Backward compatibility
----------------------
Expand-only and non-destructive. This revision adds one nullable column,
``upstream_resource_contracts.payment_terms_json``. It:

- alters no existing column, constraint or index and rewrites no row;
- performs no backfill: every existing row keeps ``NULL`` meaning "not
  stated", and no past declaration is fabricated;
- needs no application code change at apply time: the previous application
  version ignores an extra nullable column and keeps serving every endpoint
  exactly as before.

Deployment notes: adding a nullable column with no default is metadata-only on
PostgreSQL (no table rewrite), but it still takes a brief ``ACCESS EXCLUSIVE``
lock on ``upstream_resource_contracts``, so a long-running reader or writer can
delay it. Roll it out with a bounded ``lock_timeout`` plus an explicit retry
procedure, exactly like ``0037_contract_revisions``. Downgrading drops the
column and permanently destroys any stored payment-terms declaration, so
downgrade is gated: back up the column or confirm it is empty first, and never
run it merely to roll back an application deployment.

The column stores only the strict canonical JSON of a
``contract-payment-terms/v1`` declaration; validation happens in the
application write path, never in this migration, so applying the migration can
never execute evolving payload/serialization behaviour.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0038_contract_payment_terms"
down_revision: str | None = "0037_contract_revisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable declared payment-terms text column; no backfill."""

    op.add_column(
        "upstream_resource_contracts",
        sa.Column("payment_terms_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Drop the declared payment-terms carrier and any stored declaration."""

    op.drop_column("upstream_resource_contracts", "payment_terms_json")
