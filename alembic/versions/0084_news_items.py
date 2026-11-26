"""NEWS-1 news, policy and geopolitical events: items and source poll state (ADR Decision 35).

``news_items``: one row per item a registered source published (a public feed entry, or a REMIT
message the platform already holds), with source, link, publisher, published and retrieved
times, language, licence note, content SHA-256, deterministic tags, the held REMIT outage it
is linked to and a revision. ``news_source_polls``: per source, when it was last polled and how.

Follows SCHED-1's ``0085_sched1_nomination_matching`` (built in parallel, merged first).
Expand-only: two new tables; the downgrade drops only those.
"""

import sqlalchemy as sa

from alembic import op

revision = "0084_news_items"
down_revision = "0085_sched1_nomination_matching"
branch_labels = None
depends_on = None
# Reversibility, printed by the gated upgrade (scripts/ops/upgrade_database.py).
reversibility = "reversible"


def upgrade() -> None:
    op.create_table(
        "news_items",
        sa.Column("item_id", sa.String(40), primary_key=True),
        sa.Column("source_id", sa.String(48), nullable=False),
        sa.Column("source_ref", sa.String(400), nullable=False),
        sa.Column("url", sa.String(1000), nullable=True),
        sa.Column("publisher", sa.String(200), nullable=False),
        sa.Column("title", sa.String(400), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("published_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("licence_note", sa.String(300), nullable=False),
        sa.Column("event_types", sa.JSON(), nullable=False),
        sa.Column("entities", sa.JSON(), nullable=False),
        sa.Column("hubs", sa.JSON(), nullable=False),
        sa.Column("countries", sa.JSON(), nullable=False),
        sa.Column("capacity_change", sa.Boolean(), nullable=False),
        sa.Column("linked_event_key", sa.String(160), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("first_seen_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_news_items_published", "news_items", ["published_at_utc"])
    op.create_index("ix_news_items_source", "news_items", ["source_id"])
    op.create_index("ix_news_items_linked_event", "news_items", ["linked_event_key"])
    op.create_table(
        "news_source_polls",
        sa.Column("source_id", sa.String(48), primary_key=True),
        sa.Column("last_polled_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(24), nullable=False),
        sa.Column("last_detail", sa.String(500), nullable=False),
        sa.Column("feed_url", sa.String(1000), nullable=True),
        sa.Column("items_seen", sa.Integer(), nullable=False),
        sa.Column("items_new", sa.Integer(), nullable=False),
        sa.Column("items_changed", sa.Integer(), nullable=False),
        sa.Column("etag", sa.String(200), nullable=True),
        sa.Column("last_modified", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("news_source_polls")
    op.drop_index("ix_news_items_linked_event", table_name="news_items")
    op.drop_index("ix_news_items_source", table_name="news_items")
    op.drop_index("ix_news_items_published", table_name="news_items")
    op.drop_table("news_items")
