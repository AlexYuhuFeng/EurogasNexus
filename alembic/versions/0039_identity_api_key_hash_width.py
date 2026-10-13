"""Widen identity_api_keys.key_hash to hold the keyed digest format.

Revision ID: 0039_identity_api_key_hash_width
Revises: 0038_contract_payment_terms
Create Date: 2026-10-07

Defect
------
``hash_key_secret`` returns ``"hmac:" + sha256_hex`` when
``EUROGAS_NEXUS_SECRET_KEY`` is configured (``security/identity.py``), which is 69
characters. ``identity_api_keys.key_hash`` was declared ``VARCHAR(64)`` by
``0022_identity_api_keys``. PostgreSQL enforces the length and refuses the insert
with ``22001 value too long for type character varying(64)``, so **minting any API
key failed on a deployment that set the credential-encryption key** -- which is
exactly the configuration ``deploy/runtime/compose.yaml`` ships with.

Why it survived the suite: the unit tests run on SQLite, which ignores the
declared ``VARCHAR`` length, and the PostgreSQL integration tests that would have
exercised it skip unless ``RUNTIME_STORE_DATABASE_URL`` points at a real server.
The failure was therefore only reachable on the deployed stack.

Backward compatibility
----------------------
Expand-only and non-destructive. Widening a ``VARCHAR`` is a metadata-only change
on PostgreSQL (no table rewrite) that cannot invalidate an existing row, because
every stored value was already required to fit 64 characters. Both stored
formats verify: ``verify_key_hash`` accepts the legacy unkeyed SHA-256 digest and
the ``hmac:`` form.

The limit is set to 80 rather than exactly 69 so a future digest algorithm or
prefix change does not need another migration; the column is already indexed only
by ``principal_id``/``revoked_at_utc``, so no index is affected.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0039_identity_api_key_hash_width"
down_revision: str | None = "0038_contract_payment_terms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: ``hmac:`` (5) + SHA-256 hex (64) = 69. See the module docstring for why 80.
KEY_HASH_LENGTH = 80
#: The width this revision widens away from; used only by ``downgrade``.
PREVIOUS_KEY_HASH_LENGTH = 64


def upgrade() -> None:
    """Widen ``identity_api_keys.key_hash`` so the keyed digest fits."""

    op.alter_column(
        "identity_api_keys",
        "key_hash",
        existing_type=sa.String(PREVIOUS_KEY_HASH_LENGTH),
        type_=sa.String(KEY_HASH_LENGTH),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Restore the previous width.

    Refuses to narrow while any stored digest is longer than the old width, since
    ``ALTER`` would otherwise fail mid-way (or, on a server that truncates, lose
    the tail of every keyed digest and silently invalidate those keys).
    """

    bind = op.get_bind()
    too_long = bind.execute(
        sa.text(
            "SELECT count(*) FROM identity_api_keys "
            "WHERE char_length(key_hash) > :limit"
        ),
        {"limit": PREVIOUS_KEY_HASH_LENGTH},
    ).scalar_one()

    if too_long:
        raise RuntimeError(
            "refusing to narrow identity_api_keys.key_hash: "
            f"{too_long} row(s) hold a keyed digest longer than "
            f"{PREVIOUS_KEY_HASH_LENGTH} characters and would be invalidated. "
            "Revoke and re-mint those API keys first, or keep this revision "
            "applied."
        )

    op.alter_column(
        "identity_api_keys",
        "key_hash",
        existing_type=sa.String(KEY_HASH_LENGTH),
        type_=sa.String(PREVIOUS_KEY_HASH_LENGTH),
        existing_nullable=False,
    )
