"""Contract tests for stored-value widths against declared column lengths.

Why this exists
---------------
``identity_api_keys.key_hash`` was declared ``String(64)`` while
``hash_key_secret`` returns ``"hmac:" + sha256_hex`` (69 characters) once
``EUROGAS_NEXUS_SECRET_KEY`` is set. PostgreSQL rejects the insert with ``22001
value too long for type character varying(64)``, so minting any API key failed on
a deployment that configured the credential-encryption key. The unit suite runs
on SQLite, which ignores a declared ``VARCHAR`` length, so nothing caught it; the
PostgreSQL integration tests that would have skip without a live server.

A declared width is a contract between the model and every writer, and the only
way it stays true is for a test to compare the two. These tests are deliberately
narrow: they cover values this codebase computes into a column, not user input.
"""

from __future__ import annotations

import pytest
from sqlalchemy import String

from eurogas_nexus.db.models.identity import IdentityApiKeyRecord
from eurogas_nexus.security.identity import hash_key_secret


def _declared_length(model, attribute: str) -> int:
    column_type = model.__table__.columns[attribute].type
    assert isinstance(column_type, String), (
        f"{model.__tablename__}.{attribute} is {type(column_type).__name__}, "
        "not a String column"
    )
    assert column_type.length is not None, (
        f"{model.__tablename__}.{attribute} declares no length"
    )
    return int(column_type.length)


def test_keyed_key_hash_fits_the_declared_column(monkeypatch: pytest.MonkeyPatch) -> None:
    """The hmac: digest must fit identity_api_keys.key_hash."""

    monkeypatch.setenv("EUROGAS_NEXUS_SECRET_KEY", "a-configured-credential-key")
    digest = hash_key_secret("the-key-secret")
    assert digest.startswith("hmac:"), digest

    declared = _declared_length(IdentityApiKeyRecord, "key_hash")
    assert len(digest) <= declared, (
        f"hash_key_secret returns {len(digest)} characters ({digest[:12]}...) but "
        f"identity_api_keys.key_hash is declared String({declared}). PostgreSQL "
        "enforces this and refuses the insert with error 22001, so every attempt "
        "to mint an API key fails on a deployment that sets "
        "EUROGAS_NEXUS_SECRET_KEY. Widen the column in a migration and here."
    )


def test_legacy_key_hash_fits_the_declared_column(monkeypatch: pytest.MonkeyPatch) -> None:
    """The unkeyed SHA-256 digest must fit too, since both formats verify."""

    monkeypatch.delenv("EUROGAS_NEXUS_SECRET_KEY", raising=False)
    digest = hash_key_secret("the-key-secret")
    assert not digest.startswith("hmac:")
    assert len(digest) <= _declared_length(IdentityApiKeyRecord, "key_hash")


def test_key_hash_column_admits_both_stored_formats() -> None:
    """The widest format the writer can produce must fit with margin.

    ``hmac:`` plus a SHA-256 hex digest is 69 characters today. A width of exactly
    69 would leave no room for a changed digest, so the assertion is that the
    column is at least that wide, not that it is exactly that wide.
    """

    widest_today = len("hmac:") + 64
    declared = _declared_length(IdentityApiKeyRecord, "key_hash")
    assert declared >= widest_today, (
        f"key_hash is String({declared}) but the keyed digest needs "
        f"{widest_today} characters"
    )


def test_the_widening_migration_declares_the_width_the_model_expects() -> None:
    """The model and the migration that widens the column must agree.

    On the deployed stack the column comes from the migrations, not from the model,
    so a model-only widening would not change the real column. That is how the
    original defect survived review: the model and the creating migration both said
    ``String(64)``, and nothing compared either of them with the value the code
    writes.

    The migration expresses its width through a named constant, so this reads that
    constant rather than guessing at the call's shape. The compiled DDL is exercised
    for real by ``.dnx-out/pg_verify.py``; this test is the cheap in-suite guard that
    the two declarations have not diverged.
    """

    import re as _re
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    widening = root / "alembic" / "versions" / "0039_identity_api_key_hash_width.py"
    assert widening.is_file(), (
        "the revision that widens identity_api_keys.key_hash is missing; without it "
        "the deployed VARCHAR(64) rejects the 69-character keyed digest"
    )

    text = widening.read_text(encoding="utf-8")
    constants = {
        match.group(1): int(match.group(2))
        for match in _re.finditer(r"^([A-Z_]+)\s*=\s*(\d+)\s*$", text, _re.M)
    }
    upgrade_body = text.split("def upgrade()", 1)[-1].split("def downgrade()", 1)[0]

    resolved = _re.search(r"type_=sa\.String\(([A-Za-z_0-9]+)\)", upgrade_body)
    assert resolved, (
        "the widening revision does not pass a String(...) type to alter_column in "
        "its upgrade(), so the column is not actually widened"
    )
    token = resolved.group(1)
    migration_width = int(token) if token.isdigit() else constants.get(token)
    assert migration_width is not None, (
        f"the widening revision's width {token!r} is neither a literal nor a "
        f"numeric constant declared in the file (found {sorted(constants)})"
    )

    modelled = _declared_length(IdentityApiKeyRecord, "key_hash")
    assert modelled == migration_width, (
        f"the model declares String({modelled}) but the widening migration sets "
        f"String({migration_width}). The deployed column comes from the migration, "
        "so these must agree."
    )
