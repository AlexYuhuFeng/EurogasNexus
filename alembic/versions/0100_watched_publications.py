"""Watched publications: what the product last found at each public publication it watches.

- ``watched_publications``: one row per publication of ``domain/publications/registry``: its
  state (current, needs confirmation, unreachable, never fetched, hand-maintained, link only),
  when it was last checked, fetched and changed, the digest of the document held, a changed
  document awaiting a person's confirmation, the parsed record and the one before it.

Expand-only; the downgrade drops the table. Chained after ``0098_deal_position_source``; a
sibling branch adds ``0099_remove_strategy_laboratory`` from the same parent, so the integrator
re-chains this revision after it (one line, ``down_revision``) when both land.
"""

import sqlalchemy as sa

from alembic import op

revision = "0100_watched_publications"
down_revision = "0098_deal_position_source"
branch_labels = None
depends_on = None
# Reversibility, printed by the gated upgrade (scripts/ops/upgrade_database.py).
reversibility = "reversible"
reversibility_note = (
    "The downgrade drops what the product last found at each watched publication; the next "
    "check fetches the permitted publications again and rebuilds it. The capacity notices it "
    "recorded stay in capacity_notices."
)


def upgrade() -> None:
    op.create_table(
        "watched_publications",
        sa.Column("publication_id", sa.String(64), primary_key=True),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("detail", sa.String(500), nullable=False),
        sa.Column("last_checked_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_fetched_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_changed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("document_url", sa.String(1000), nullable=True),
        sa.Column("content_sha256", sa.String(64), nullable=True),
        sa.Column("pending_sha256", sa.String(64), nullable=True),
        sa.Column("pending_url", sa.String(1000), nullable=True),
        sa.Column("pending_since_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("record", sa.JSON(), nullable=True),
        sa.Column("record_fetched_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("previous_record", sa.JSON(), nullable=True),
        sa.Column("previous_fetched_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by", sa.String(128), nullable=True),
        sa.Column("confirmed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("etag", sa.String(200), nullable=True),
        sa.Column("last_modified", sa.String(64), nullable=True),
        sa.CheckConstraint(
            "state IN ('current', 'needs_confirmation', 'unreachable', 'never_fetched', "
            "'hand_maintained', 'link_only')",
            name="ck_watched_publications_state",
        ),
    )


def downgrade() -> None:
    op.drop_table("watched_publications")
