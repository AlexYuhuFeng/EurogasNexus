"""Store personal preferences per principal and organisation defaults on the server.

Preferences were browser-local, so a trader's language, theme and landing views did not
follow them between the web and desktop clients or between offices, and there was no
organisation-wide default. Both tables are additive.
"""

import sqlalchemy as sa

from alembic import op

revision = "0047_user_preferences"
down_revision = "0046_principal_job_functions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "principal_preferences",
        sa.Column("principal_id", sa.String(64), primary_key=True),
        sa.Column("preferences_json", sa.JSON(), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "organisation_settings",
        sa.Column("setting_key", sa.String(64), primary_key=True),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("organisation_settings")
    op.drop_table("principal_preferences")
