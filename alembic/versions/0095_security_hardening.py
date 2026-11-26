"""Security hardening (review 2026-11): audit hash chain, dual control, second factor.

- ``audit_chain``: one link per audit row (sequence, previous hash, row hash), inserted when
  the writing transaction commits; ``audit_chain_anchors``: prune anchors and checkpoints (H5).
- ``privileged_changes``: security-relevant changes awaiting a second administrator (H7).
- ``identity_mfa``: a local account's TOTP secret (encrypted) and recovery-code hashes (H6).
- PostgreSQL only: triggers that refuse any UPDATE of ``audit_events`` and ``audit_chain``,
  and any DELETE unless the transaction set ``eurogas.audit_prune = 'approved'`` (the
  dual-controlled prune). The application role's grants are in
  ``docs/security/DATABASE_ROLES.md``.

Expand-only; the downgrade drops only what this revision adds.
"""

import sqlalchemy as sa

from alembic import op

revision = "0095_security_hardening"
down_revision = "0094_option_settlements"
branch_labels = None
depends_on = None
# Reversibility, printed by the gated upgrade (scripts/ops/upgrade_database.py). The downgrade
# drops the audit chain links and anchors with the tables: the audit rows themselves stay.
reversibility = "reversible"

_GUARD_FUNCTION = """
CREATE OR REPLACE FUNCTION eurogas_audit_guard() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'audit rows are append-only (%.%)', TG_TABLE_SCHEMA, TG_TABLE_NAME
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF TG_OP = 'DELETE' AND coalesce(current_setting('eurogas.audit_prune', true), '')
            <> 'approved' THEN
        RAISE EXCEPTION 'audit rows are deleted only by an approved prune'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""


def upgrade() -> None:
    op.create_table(
        "audit_chain",
        sa.Column("chain_seq", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("event_id", sa.String(64), nullable=False, unique=True),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("sealed_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "audit_chain_anchors",
        sa.Column("anchor_id", sa.String(40), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("chain_seq", sa.BigInteger(), nullable=False),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("signature", sa.String(80), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("detail", sa.String(500), nullable=False, server_default=""),
    )
    op.create_table(
        "privileged_changes",
        sa.Column("change_id", sa.String(40), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("method", sa.String(8), nullable=False),
        sa.Column("path", sa.String(200), nullable=False),
        sa.Column("body_sha256", sa.String(64), nullable=False),
        sa.Column("body_json", sa.JSON(), nullable=True),
        sa.Column("summary", sa.String(300), nullable=False, server_default=""),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("requested_by", sa.String(80), nullable=False),
        sa.Column("requested_by_name", sa.String(80), nullable=False),
        sa.Column("requested_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by", sa.String(80), nullable=True),
        sa.Column("decided_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.String(500), nullable=True),
        sa.Column("applied_at_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_privileged_changes_state", "privileged_changes", ["state", "requested_at_utc"]
    )
    op.create_table(
        "identity_mfa",
        sa.Column(
            "principal_id",
            sa.String(80),
            sa.ForeignKey("identity_principals.principal_id"),
            primary_key=True,
        ),
        sa.Column("secret_encrypted", sa.String(400), nullable=False),
        sa.Column("confirmed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_step", sa.BigInteger(), nullable=True),
        sa.Column("recovery_code_hashes", sa.JSON(), nullable=True),
        sa.Column("challenge_hash", sa.String(64), nullable=True),
        sa.Column("challenge_expires_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("challenge_client_type", sa.String(32), nullable=True),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(_GUARD_FUNCTION)
        for table in ("audit_events", "audit_chain"):
            op.execute(
                f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION eurogas_audit_guard()"
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in ("audit_events", "audit_chain"):
            op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
        op.execute("DROP FUNCTION IF EXISTS eurogas_audit_guard()")
    op.drop_table("identity_mfa")
    op.drop_index("ix_privileged_changes_state", table_name="privileged_changes")
    op.drop_table("privileged_changes")
    op.drop_table("audit_chain_anchors")
    op.drop_table("audit_chain")
